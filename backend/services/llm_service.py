"""
LLM Service – Ollama interface with dual-model support.
Primary: llama3.1:8b (resume + cover letter generation)
Reviewer: llama3.1:8b (critique & improvement pass)
"""

import httpx
import json
import asyncio
from typing import AsyncGenerator, Optional
from config import settings


# ── Health Checks ─────────────────────────────────────────────────────────────

async def is_ollama_running() -> bool:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
            return r.status_code == 200
    except Exception:
        return False


async def get_available_models() -> list[str]:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
            data = r.json()
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


async def is_model_available(model: str) -> bool:
    models = await get_available_models()
    return any(model in m for m in models)


# ── Core Chat Function ────────────────────────────────────────────────────────

async def _chat_stream(
    messages: list[dict],
    model: str,
    temperature: float = None,
) -> AsyncGenerator[str, None]:
    """Stream tokens from Ollama /api/chat endpoint."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": {
            "temperature": temperature or settings.LLM_TEMPERATURE,
            "top_p": settings.LLM_TOP_P,
            "num_ctx": settings.LLM_NUM_CTX,
            "repeat_penalty": 1.1,
        },
    }
    async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT) as client:
        async with client.stream(
            "POST",
            f"{settings.OLLAMA_BASE_URL}/api/chat",
            json=payload,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        if token := chunk.get("message", {}).get("content", ""):
                            yield token
                        if chunk.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue


async def _chat(
    messages: list[dict],
    model: str,
    temperature: float = None,
) -> str:
    """Non-streaming chat – returns complete response."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature or settings.LLM_TEMPERATURE,
            "top_p": settings.LLM_TOP_P,
            "num_ctx": settings.LLM_NUM_CTX,
            "repeat_penalty": 1.1,
        },
    }
    async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT) as client:
        r = await client.post(
            f"{settings.OLLAMA_BASE_URL}/api/chat",
            json=payload,
        )
        r.raise_for_status()
        return r.json()["message"]["content"].strip()


# ── System Prompts ────────────────────────────────────────────────────────────

_SYSTEM_RESUME_EXPERT = f"""You are an elite ATS optimization specialist and professional resume writer.
{settings.STUDENT_CONTEXT}

STRICT OUTPUT RULES (never break these):
1. EXACTLY ONE PAGE — keep total word count under 650 words. Cut ruthlessly.
2. EACH SECTION APPEARS EXACTLY ONCE — never repeat SKILLS, EXPERIENCE, or any header.
3. SECTION ORDER (top to bottom, ALL CAPS headers):
   CONTACT LINE (name + email + phone + LinkedIn + GitHub, all on 2 lines)
   PROFESSIONAL SUMMARY (3 lines max, packed with JD keywords)
   SKILLS (3-4 category lines: "Category: skill1, skill2, skill3" — NO sub-sections)
   EXPERIENCE (reverse-chron; each role: Title | Company | Date on one line, then 2-3 bullets)
   PROJECTS (2-3 projects max; each: Project Name | Tech on one line, then 2 bullets)
   EDUCATION (degree | school | date, one line each)
4. BULLET FORMAT: every bullet starts with "• " (bullet + space), then action verb + achievement + metric
5. No tables, no columns, no graphics, no special chars, no horizontal lines in text
6. Use EXACT keywords from the job description — this is critical for ATS parsing
7. Never fabricate anything — only reframe real experience
"""

_SYSTEM_COVER_EXPERT = f"""You are an expert career advisor specializing in crafting compelling motivation letters.
{settings.STUDENT_CONTEXT}

Your cover letters must:
- Be 300-380 words, 4 paragraphs
- Feel 100% personal and tailored – no generic phrases
- Include exact keywords from the job description naturally
- Show genuine company/role research insights
- Follow business letter format (Date, Subject, Dear Hiring Manager,)
- Close with strong internship availability call-to-action
"""

_SYSTEM_REVIEWER = """You are a brutally honest senior tech recruiter reviewing a tailored resume.
Your job is to identify weaknesses and suggest specific improvements.
Be concise, specific, and actionable. Never be vague.
"""


# ── Resume Optimization ───────────────────────────────────────────────────────

async def tailor_resume_stream(
    original_resume: str,
    job_description: str,
    rag_context: str = "",
    github_summary: str = "",
) -> AsyncGenerator[str, None]:
    """Stream a tailored resume token by token."""
    rag_section = f"\n\n## RETRIEVED RELEVANT CONTEXT (use this):\n{rag_context}" if rag_context else ""
    gh_section  = f"\n\n## GITHUB PROJECTS (incorporate relevant ones):\n{github_summary}" if github_summary else ""

    messages = [
        {"role": "system", "content": _SYSTEM_RESUME_EXPERT},
        {"role": "user", "content": f"""
## TASK: Create a 1-page ATS-optimised resume tailored to the job description.

## STEP 1 – Extract JD keywords:
Identify: required skills, tools, frameworks, methodologies, domain terms from the JD.

## STEP 2 – Build the resume (EXACTLY this structure, EACH section ONCE):

[Candidate Full Name]
[email] | [phone] | [LinkedIn URL] | [GitHub URL]

PROFESSIONAL SUMMARY
[3 tight sentences: role match + top 2 JD-aligned achievements + EPITA MSc context]

SKILLS
[ONLY these 3-4 lines, no sub-headings:]
AI/ML: [JD-matching ML/DL/AI skills from candidate profile]
Programming & Data: [languages + data tools]
Cloud & MLOps: [deployment + infra tools]
Frameworks: [LLM/RAG/NLP frameworks]

EXPERIENCE
[Job Title] | [Company] | [Start – End]
• [Strong action verb] + [what you did with JD-keyword tech] + [quantified result]
• [Same format — 2-3 bullets per role]

[Repeat for each role, newest first]

PROJECTS
[Project Name] | [Key Tech from JD]
• [What you built, why it matters to THIS role] + [metric]
• [Second bullet with another JD keyword]

[2 projects max]

EDUCATION
MSc Data Science & Analytics | EPITA Paris | Sep 2024 – Present
[Prior degree] | [School] | [Year]

## ORIGINAL RESUME (source of truth – never invent):
{original_resume[:4000]}
{rag_section}
{gh_section}

## TARGET JOB DESCRIPTION:
{job_description[:2000]}

## FINAL CHECK before outputting:
- Did I write SKILLS exactly once? ✓ 
- Is every bullet starting with "• "? ✓
- Total word count under 650? ✓
- No section repeated? ✓

Output ONLY the resume text. No explanations, no headers like "Here is", no commentary.
"""},
    ]
    async for token in _chat_stream(messages, settings.PRIMARY_MODEL):
        yield token


async def tailor_resume(
    original_resume: str,
    job_description: str,
    rag_context: str = "",
    github_summary: str = "",
) -> str:
    result = ""
    async for token in tailor_resume_stream(
        original_resume, job_description, rag_context, github_summary
    ):
        result += token
    return result


# ── Cover Letter Generation ───────────────────────────────────────────────────

async def generate_cover_letter_stream(
    tailored_resume: str,
    job_description: str,
    job_title: str = "",
    company: str = "",
    github_highlights: str = "",
) -> AsyncGenerator[str, None]:
    """Stream a cover letter token by token."""
    messages = [
        {"role": "system", "content": _SYSTEM_COVER_EXPERT},
        {"role": "user", "content": f"""
## TASK: Write a compelling cover letter / motivation letter.

## JOB:
- Title: {job_title or "the position"}
- Company: {company or "the company"}

## STRUCTURE:
**Paragraph 1** – Powerful hook: why this company, why this role, your #1 matching strength
**Paragraph 2** – 2-3 key achievements from resume that DIRECTLY answer JD requirements (use keywords from JD)
**Paragraph 3** – Technical alignment: show mastery of their stack using JD terminology + relevant GitHub projects
**Paragraph 4** – Closing: enthusiasm, internship availability, call to action

## CONSTRAINTS:
- 300-380 words total
- Use EXACT tech keywords: {_extract_key_terms(job_description)}
- Mention EPITA MSc Data Science & Analytics naturally
- Sign as candidate from the resume
{f"- Reference relevant GitHub projects: {github_highlights}" if github_highlights else ""}

## CANDIDATE RESUME (tailored):
{tailored_resume[:3000]}

## JOB DESCRIPTION:
{job_description[:2000]}

## OUTPUT:
Cover letter only. Begin with the date line. No meta-commentary.
"""},
    ]
    async for token in _chat_stream(messages, settings.PRIMARY_MODEL):
        yield token


async def generate_cover_letter(
    tailored_resume: str,
    job_description: str,
    job_title: str = "",
    company: str = "",
    github_highlights: str = "",
) -> str:
    result = ""
    async for token in generate_cover_letter_stream(
        tailored_resume, job_description, job_title, company, github_highlights
    ):
        result += token
    return result


# ── Reviewer Pass (Second Model) ──────────────────────────────────────────────

async def review_resume(tailored_resume: str, job_description: str) -> str:
    """
    Run a second-pass critique of the tailored resume.
    Returns structured feedback (not a rewrite).
    """
    messages = [
        {"role": "system", "content": _SYSTEM_REVIEWER},
        {"role": "user", "content": f"""
Review this tailored resume against the job description.

## JOB DESCRIPTION (first 1500 chars):
{job_description[:1500]}

## TAILORED RESUME:
{tailored_resume[:3000]}

## YOUR REVIEW (be specific and numbered):
1. Top 3 strengths of this resume for this role
2. Top 3 weaknesses / missed opportunities  
3. Specific wording improvements (quote original → suggest replacement)
4. Any redundancy to remove
5. Final verdict: Pass / Borderline / Fail for ATS

Return as formatted text. Be direct.
"""},
    ]
    return await _chat(messages, settings.REVIEWER_MODEL, temperature=0.1)


# ── Utility Functions ─────────────────────────────────────────────────────────

async def extract_contact_info(resume_text: str) -> dict:
    """Extract name, email, phone from resume text."""
    messages = [
        {"role": "system", "content": "You are a resume parser. Extract contact info."},
        {"role": "user", "content": f"""Extract from this resume text:
{resume_text[:2000]}

Return ONLY this JSON (no markdown):
{{"name": "...", "email": "...", "phone": "...", "linkedin": "...", "github": "..."}}
Use empty string "" if not found."""},
    ]
    raw = await _chat(messages, settings.PRIMARY_MODEL, temperature=0.0)
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(raw)
    except Exception:
        return {"name": "", "email": "", "phone": "", "linkedin": "", "github": ""}


async def extract_skills_llm(text: str, source: str = "resume") -> list[dict]:
    """
    Use LLM to extract skills with categories from any text.
    Returns list of {name, category} dicts.
    """
    messages = [
        {"role": "system", "content": "You are a technical skills extractor. Return JSON only."},
        {"role": "user", "content": f"""Extract all technical and professional skills from this {source} text.

TEXT:
{text[:4000]}

Return ONLY a JSON array (no markdown):
[
  {{"name": "Python", "category": "Programming"}},
  {{"name": "Machine Learning", "category": "AI/ML"}},
  {{"name": "Docker", "category": "DevOps"}}
]

Categories: Programming, AI/ML, Data Engineering, DevOps, Databases, Visualization, Frameworks, Soft Skills, Languages, Other
Extract ALL skills visible in the text."""},
    ]
    raw = await _chat(messages, settings.PRIMARY_MODEL, temperature=0.0)
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(raw)
    except Exception:
        return []


async def analyze_ats_llm(resume: str, jd: str) -> dict:
    """LLM-based holistic ATS analysis returning structured JSON."""
    messages = [
        {"role": "system", "content": "You are an ATS system evaluator. Return JSON only."},
        {"role": "user", "content": f"""Evaluate this resume against the JD as an ATS system.

JD (first 1500 chars):
{jd[:1500]}

RESUME (first 2000 chars):
{resume[:2000]}

Return ONLY this JSON:
{{
  "keyword_match_pct": <0-100>,
  "relevance_score": <0-10>,
  "top_matching_keywords": ["kw1", "kw2", "kw3", "kw4", "kw5"],
  "critical_missing": ["miss1", "miss2", "miss3"],
  "strengths": ["s1", "s2", "s3"],
  "improvements": ["i1", "i2", "i3"],
  "verdict": "<one sentence>"
}}"""},
    ]
    raw = await _chat(messages, settings.PRIMARY_MODEL, temperature=0.0)
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(raw)
    except Exception:
        return {
            "keyword_match_pct": 65,
            "relevance_score": 6.5,
            "top_matching_keywords": [],
            "critical_missing": [],
            "strengths": [],
            "improvements": [],
            "verdict": "Analysis unavailable",
        }


def _extract_key_terms(text: str, n: int = 8) -> str:
    """Quick keyword extraction for prompt injection (no LLM)."""
    import re
    tech_terms = re.findall(
        r"\b(Python|R\b|SQL|pandas|numpy|scikit|TensorFlow|PyTorch|Spark|"
        r"Hadoop|AWS|Azure|GCP|Docker|Kubernetes|Git|Linux|ML|NLP|"
        r"deep learning|machine learning|data science|analytics|"
        r"statistics|Tableau|Power BI|FastAPI|Django|Flask|PostgreSQL|"
        r"MongoDB|Kafka|Airflow|MLOps|LLM|RAG|transformer|BERT|"
        r"scikit-learn|XGBoost|LightGBM|Streamlit|Plotly)\b",
        text,
        re.IGNORECASE,
    )
    unique = list(dict.fromkeys(t.lower() for t in tech_terms))[:n]
    return ", ".join(unique) if unique else "relevant technologies"
