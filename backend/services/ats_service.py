"""
Hybrid ATS Scoring Engine.

Score = 40% keyword match + 30% semantic similarity + 20% skill overlap + 10% format

Returns a comprehensive breakdown with actionable feedback.
"""

import re
from collections import Counter
from typing import Optional
from config import settings


# ── ATS Score Entry Point ─────────────────────────────────────────────────────

def compute_ats_score(
    resume_text: str,
    job_description: str,
    user_skills: list[str] = None,
    semantic_similarity: float = None,
    llm_analysis: dict = None,
) -> dict:
    """
    Main ATS scoring function.

    Args:
        resume_text: Tailored resume plain text
        job_description: Target job description
        user_skills: List of known user skills from profile
        semantic_similarity: Pre-computed cosine similarity (0-1)
        llm_analysis: Optional dict from analyze_ats_llm()

    Returns full breakdown dict.
    """
    jd_lower     = job_description.lower()
    resume_lower = resume_text.lower()

    # ── Component 1: Keyword Score (40%) ──────────────────────────────────
    kw_result = _keyword_score(resume_lower, jd_lower)

    # ── Component 2: Semantic Score (30%) ─────────────────────────────────
    if semantic_similarity is not None:
        sem_score = round(semantic_similarity * 100, 1)
    elif llm_analysis:
        # Use LLM keyword match pct as proxy if cosine similarity not available
        sem_score = float(llm_analysis.get("keyword_match_pct", 65))
    else:
        sem_score = 65.0  # neutral default

    # ── Component 3: Skill Overlap Score (20%) ────────────────────────────
    skill_result = _skill_overlap_score(
        resume_lower, jd_lower, user_skills or []
    )

    # ── Component 4: Format Score (10%) ───────────────────────────────────
    fmt_result = _format_score(resume_text)

    # ── Weighted Total ────────────────────────────────────────────────────
    total = (
        kw_result["score"]    * settings.ATS_KEYWORD_WEIGHT +
        sem_score             * settings.ATS_SEMANTIC_WEIGHT +
        skill_result["score"] * settings.ATS_SKILL_WEIGHT   +
        fmt_result["score"]   * settings.ATS_FORMAT_WEIGHT
    )
    total = round(min(100.0, max(0.0, total)), 1)

    grade, verdict = _grade(total)

    # Merge LLM insights if available
    llm_strengths    = (llm_analysis or {}).get("strengths", [])
    llm_improvements = (llm_analysis or {}).get("improvements", [])
    llm_verdict      = (llm_analysis or {}).get("verdict", "")

    return {
        # Scores
        "total_score":       total,
        "keyword_score":     kw_result["score"],
        "semantic_score":    sem_score,
        "skill_score":       skill_result["score"],
        "format_score":      fmt_result["score"],
        # Grade
        "grade":             grade,
        "verdict":           llm_verdict or verdict,
        # Keywords
        "matched_keywords":  kw_result["matches"],
        "missing_keywords":  kw_result["missing"],
        # Skills
        "matched_skills":    skill_result["matched"],
        "missing_skills":    skill_result["missing"],
        # Format
        "format_issues":     fmt_result["issues"],
        # LLM
        "llm_strengths":     llm_strengths,
        "llm_improvements":  llm_improvements,
    }


# ── Keyword Scoring ───────────────────────────────────────────────────────────

def extract_jd_keywords(jd_text: str) -> list[str]:
    """
    Extract meaningful keywords from JD.
    Prioritizes tech terms, tools, methodologies.
    """
    stop_words = {
        "the","a","an","and","or","but","in","on","at","to","for","of","with",
        "is","are","was","were","be","been","have","has","had","will","would",
        "could","should","we","you","they","this","that","these","those","it",
        "its","as","by","from","about","into","each","which","all","also",
        "more","such","than","other","can","our","your","their","then","when",
        "use","using","used","must","able","well","good","work","role","team",
        "job","candidate","required","preferred","include","including","strong",
        "experience","knowledge","ability","skills","excellent","opportunity",
    }

    text = jd_text.lower()

    # Single tokens
    tokens = re.findall(r"[a-z][a-z0-9+#.\-]*", text)
    filtered = [t for t in tokens if len(t) > 2 and t not in stop_words]

    # 2-grams
    bigrams = [
        f"{filtered[i]} {filtered[i+1]}"
        for i in range(len(filtered) - 1)
        if len(filtered[i]) > 2 and len(filtered[i+1]) > 2
        and filtered[i] not in stop_words and filtered[i+1] not in stop_words
    ]

    # Always include tech terms even if frequency = 1
    tech = re.findall(
        r"\b(python|r\b|sql|pandas|numpy|scikit[-\s]?learn|tensorflow|pytorch|"
        r"keras|spark|hadoop|aws|azure|gcp|docker|kubernetes|git|linux|"
        r"machine learning|deep learning|nlp|computer vision|data science|"
        r"analytics|statistics|tableau|power ?bi|excel|matlab|java|scala|"
        r"javascript|typescript|react|node\.?js|flask|fastapi|django|"
        r"postgresql|mysql|mongodb|elasticsearch|kafka|redis|airflow|"
        r"mlops|llm|transformers|hugging ?face|langchain|rag|etl|"
        r"xgboost|lightgbm|random forest|neural network|bert|gpt|"
        r"plotly|matplotlib|seaborn|scikit|sklearn|scipy|"
        r"data engineer|data analyst|data scientist|mlflow|wandb|"
        r"neo4j|cassandra|bigquery|snowflake|dbt|looker|streamlit)\b",
        text,
    )

    freq = Counter(filtered + bigrams)
    top = [w for w, _ in freq.most_common(80)]
    all_kw = list(dict.fromkeys(top + list(set(tech))))
    return all_kw


def _keyword_score(resume_lower: str, jd_lower: str) -> dict:
    keywords = extract_jd_keywords(jd_lower)
    if not keywords:
        return {"score": 70.0, "matches": [], "missing": []}

    matches, missing = [], []
    for kw in keywords:
        if kw in resume_lower:
            matches.append(kw)
        else:
            # Partial stem match
            stem = kw.rstrip("ing").rstrip("ed").rstrip("s")
            if len(stem) > 4 and stem in resume_lower:
                matches.append(kw)
            else:
                missing.append(kw)

    ratio = len(matches) / len(keywords)
    # Slight non-linear boost
    score = min(100.0, (ratio ** 0.75) * 100)

    return {
        "score":   round(score, 1),
        "matches": matches[:30],
        "missing": missing[:20],
    }


# ── Skill Overlap Scoring ─────────────────────────────────────────────────────

def _skill_overlap_score(
    resume_lower: str,
    jd_lower: str,
    user_skills: list[str],
) -> dict:
    """Score based on how many JD-mentioned skills appear in resume + profile."""
    jd_keywords = extract_jd_keywords(jd_lower)

    # Normalize user skills
    user_skill_lower = [s.lower() for s in user_skills]
    all_candidate_text = resume_lower + " " + " ".join(user_skill_lower)

    matched, missing = [], []
    for kw in jd_keywords[:40]:  # Focus on top 40
        if kw in all_candidate_text:
            matched.append(kw)
        else:
            missing.append(kw)

    total = len(jd_keywords[:40]) or 1
    score = min(100.0, (len(matched) / total) ** 0.7 * 100)

    return {
        "score":   round(score, 1),
        "matched": matched[:20],
        "missing": missing[:15],
    }


# ── Format Scoring ────────────────────────────────────────────────────────────

_FORMAT_PENALTIES = [
    (r"\|.*\|.*\|",                      "Tables detected – ATS may misparse",         25),
    (r"[\u2600-\u26FF\u2700-\u27BF]",   "Emoji characters – ATS unfriendly",           15),
    (r"(photo|image|picture|graphic)",   "Graphic/image references – remove",           10),
    (r"<[a-z][a-z0-9]*\b[^>]*>",        "HTML tags detected",                          20),
]

_REQUIRED_SECTIONS = [
    "education", "experience", "skills", "projects", "summary"
]


def _format_score(resume_text: str) -> dict:
    score  = 100.0
    issues = []

    text_lower = resume_text.lower()

    for pattern, message, penalty in _FORMAT_PENALTIES:
        if re.search(pattern, resume_text, re.IGNORECASE):
            issues.append(message)
            score -= penalty

    # Check for excessively long lines (multi-column layout)
    long_lines = sum(1 for l in resume_text.split("\n") if len(l) > 180)
    if long_lines > 5:
        issues.append("Multi-column layout detected – use single-column for ATS")
        score -= 15

    # Missing essential sections
    missing_sections = [
        s for s in _REQUIRED_SECTIONS
        if not re.search(rf"\b{s}\b", text_lower)
    ]
    if missing_sections:
        score -= len(missing_sections) * 5
        issues.append(f"Missing sections: {', '.join(missing_sections)}")

    return {
        "score":  round(max(0.0, score), 1),
        "issues": issues,
    }


# ── Grading ───────────────────────────────────────────────────────────────────

def _grade(score: float) -> tuple[str, str]:
    if score >= 92:
        return "A+", "Exceptional – very high probability of passing ATS filters."
    if score >= 83:
        return "A",  "Strong – high probability of passing ATS and reaching a recruiter."
    if score >= 74:
        return "B",  "Good – should pass most ATS systems. Minor improvements possible."
    if score >= 63:
        return "C",  "Moderate – add more JD keywords and quantify achievements."
    if score >= 50:
        return "D",  "Weak – significant tailoring needed before applying."
    return "F",  "Poor – resume needs major revision to match this role."
