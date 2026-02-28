"""
Profile Router – resume upload, LinkedIn input, GitHub fetch, skill inventory.
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
import json

from database import get_db
from auth import get_current_user
from models import User, Resume, LinkedInProfile, GitHubRepo, Skill
from schemas import (
    ResumeResponse, LinkedInInput, LinkedInResponse,
    GitHubFetchRequest, GitHubRepoResponse, SkillResponse, ProfileResponse,
)
from services.resume_parser import extract_text, validate, parse_sections
from services.github_service import fetch_github_profile
from services.skill_extractor import (
    extract_skills_from_text, merge_skills, rank_skills,
)
from services.rag_service import index_resume, index_linkedin, index_github_repos
from services.llm_service import extract_contact_info, extract_skills_llm

router = APIRouter(prefix="/api/profile", tags=["Profile"])


# ── Full Profile ──────────────────────────────────────────────────────────────

@router.get("", response_model=ProfileResponse)
async def get_profile(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get complete user profile: resume + LinkedIn + GitHub + skills."""
    resume = await _get_resume(db, current_user.id)
    linkedin = await _get_linkedin(db, current_user.id)
    repos = await _get_repos(db, current_user.id)
    skills = await _get_skills(db, current_user.id)

    from schemas import UserResponse
    from sqlalchemy import func, select
    from models import JobApplication
    app_count_result = await db.execute(
        select(func.count()).where(JobApplication.user_id == current_user.id)
    )
    app_count = app_count_result.scalar() or 0

    return ProfileResponse(
        user=current_user,
        resume=resume,
        linkedin=linkedin,
        github_repos=repos,
        skills=skills,
        total_applications=app_count,
    )


# ── Resume ────────────────────────────────────────────────────────────────────

@router.post("/resume", response_model=ResumeResponse)
async def upload_resume(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload PDF/DOCX/TXT resume. Parses, validates, indexes into ChromaDB."""
    allowed = {".pdf", ".docx", ".doc", ".txt"}
    import os
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed:
        raise HTTPException(400, f"Unsupported file type: {ext}")

    raw_bytes = await file.read()
    if len(raw_bytes) > 5 * 1024 * 1024:  # 5 MB limit
        raise HTTPException(400, "File too large (max 5 MB)")

    try:
        text = extract_text(raw_bytes, file.filename)
    except (ValueError, Exception) as exc:
        raise HTTPException(422, str(exc))
    valid, err = validate(text)
    if not valid:
        raise HTTPException(422, err)

    # Parse sections
    sections = parse_sections(text)

    # Upsert resume record
    existing = await _get_resume(db, current_user.id)
    if existing:
        # Update existing
        result = await db.execute(
            select(Resume).where(Resume.user_id == current_user.id)
        )
        resume_obj = result.scalar_one()
        resume_obj.raw_text = text
        resume_obj.file_name = file.filename
        resume_obj.parsed_sections = sections
        resume_obj.chroma_indexed = 0
    else:
        resume_obj = Resume(
            user_id=current_user.id,
            raw_text=text,
            file_name=file.filename,
            parsed_sections=sections,
        )
        db.add(resume_obj)

    await db.flush()

    # Index in ChromaDB
    n_chunks = index_resume(current_user.id, text)
    resume_obj.chroma_indexed = 1
    await db.flush()
    await db.refresh(resume_obj)

    # Auto-extract and save skills from resume
    skills = extract_skills_from_text(text, source="resume")
    await _upsert_skills(db, current_user.id, skills)

    return resume_obj


@router.get("/resume", response_model=ResumeResponse)
async def get_resume(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume = await _get_resume(db, current_user.id)
    if not resume:
        raise HTTPException(404, "No resume uploaded yet")
    return resume


@router.get("/resume/download/pdf")
async def download_resume_pdf(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Download stored resume as ATS-clean PDF."""
    from services.pdf_generator import generate_pdf
    resume = await _get_resume(db, current_user.id)
    if not resume:
        raise HTTPException(404, "No resume found")
    pdf_bytes = generate_pdf(resume.raw_text, "Resume")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=resume.pdf"},
    )


# ── LinkedIn ──────────────────────────────────────────────────────────────────

@router.post("/linkedin", response_model=LinkedInResponse)
async def save_linkedin(
    payload: LinkedInInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Save LinkedIn profile data. Parses and indexes into ChromaDB."""
    # Parse skills list
    skills_list: list[str] = []
    if payload.skills_text:
        import re
        skills_list = [
            s.strip() for s in re.split(r"[,\n;]", payload.skills_text)
            if s.strip()
        ]

    # Upsert
    result = await db.execute(
        select(LinkedInProfile).where(LinkedInProfile.user_id == current_user.id)
    )
    li = result.scalar_one_or_none()

    if li:
        li.about = payload.about
        li.headline = payload.headline
        li.skills = skills_list
        li.chroma_indexed = 0
    else:
        li = LinkedInProfile(
            user_id=current_user.id,
            about=payload.about,
            headline=payload.headline,
            skills=skills_list,
        )
        db.add(li)

    await db.flush()

    # Index in ChromaDB
    index_linkedin(
        current_user.id,
        about=payload.about or "",
        experiences_text=payload.experiences_text or "",
        skills_text=payload.skills_text or "",
    )
    li.chroma_indexed = 1
    await db.flush()
    await db.refresh(li)

    # Save skills
    skill_items = [{"name": s, "category": "Other", "source": "linkedin"}
                   for s in skills_list]
    await _upsert_skills(db, current_user.id, skill_items)

    return li


@router.get("/linkedin", response_model=LinkedInResponse)
async def get_linkedin(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    li = await _get_linkedin(db, current_user.id)
    if not li:
        raise HTTPException(404, "No LinkedIn profile saved yet")
    return li


# ── GitHub ────────────────────────────────────────────────────────────────────

@router.post("/github", response_model=list[GitHubRepoResponse])
async def fetch_and_save_github(
    payload: GitHubFetchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fetch GitHub profile, store repos, index in ChromaDB."""
    try:
        data = await fetch_github_profile(payload.github_url)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(502, f"GitHub API error: {e}")

    # Update user's GitHub URL
    current_user.github_url = data["profile_url"]
    db.add(current_user)

    # Delete old repos
    await db.execute(delete(GitHubRepo).where(GitHubRepo.user_id == current_user.id))

    # Insert new repos
    repo_objects = []
    for repo in data["repos"]:
        repo_obj = GitHubRepo(
            user_id=current_user.id,
            repo_name=repo["repo_name"],
            description=repo.get("description", ""),
            language=repo.get("language", ""),
            languages_json=repo.get("languages_json", {}),
            stars=repo.get("stars", 0),
            topics=repo.get("topics", []),
            readme_text=repo.get("readme_text"),
            html_url=repo.get("html_url", ""),
            pushed_at=repo.get("pushed_at", ""),
        )
        db.add(repo_obj)
        repo_objects.append(repo_obj)

    await db.flush()

    # Index in ChromaDB
    index_github_repos(current_user.id, data["repos"])
    for r in repo_objects:
        r.chroma_indexed = 1

    await db.flush()

    # Extract skills from GitHub
    all_text = " ".join(
        f"{r['repo_name']} {r.get('description','')} {r.get('language','')} "
        f"{' '.join(r.get('topics', []))} {r.get('readme_text','')or ''}"
        for r in data["repos"]
    )
    skills = extract_skills_from_text(all_text, source="github")
    await _upsert_skills(db, current_user.id, skills)

    return repo_objects


@router.get("/github", response_model=list[GitHubRepoResponse])
async def get_github_repos(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _get_repos(db, current_user.id)


@router.post("/github/refresh", response_model=list[GitHubRepoResponse])
async def refresh_github(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Re-fetch GitHub repos (rate-limit: use sparingly)."""
    if not current_user.github_url:
        raise HTTPException(400, "No GitHub URL set. Add it first.")
    from schemas import GitHubFetchRequest
    return await fetch_and_save_github(
        GitHubFetchRequest(github_url=current_user.github_url), db, current_user
    )


# ── Skills ────────────────────────────────────────────────────────────────────

@router.get("/skills", response_model=list[SkillResponse])
async def get_skills(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _get_skills(db, current_user.id)


# ── Internal Helpers ──────────────────────────────────────────────────────────

async def _get_resume(db, user_id):
    r = await db.execute(select(Resume).where(Resume.user_id == user_id))
    return r.scalar_one_or_none()


async def _get_linkedin(db, user_id):
    r = await db.execute(select(LinkedInProfile).where(LinkedInProfile.user_id == user_id))
    return r.scalar_one_or_none()


async def _get_repos(db, user_id):
    r = await db.execute(
        select(GitHubRepo).where(GitHubRepo.user_id == user_id)
        .order_by(GitHubRepo.stars.desc())
    )
    return r.scalars().all()


async def _get_skills(db, user_id):
    r = await db.execute(
        select(Skill).where(Skill.user_id == user_id)
        .order_by(Skill.frequency.desc())
    )
    all_skills = r.scalars().all()

    # Merge any duplicate rows (same name, case-insensitive) into one
    seen: dict[str, Skill] = {}
    to_delete: list[Skill] = []
    for skill in all_skills:
        key = skill.name.lower()
        if key not in seen:
            seen[key] = skill
        else:
            # Accumulate frequency into the first-seen row, mark this one for deletion
            seen[key].frequency += skill.frequency
            if skill.sources:
                merged_sources = list(seen[key].sources or [])
                for src in skill.sources:
                    if src not in merged_sources:
                        merged_sources.append(src)
                seen[key].sources = merged_sources
            to_delete.append(skill)

    if to_delete:
        for dup in to_delete:
            await db.delete(dup)
        await db.flush()

    return list(seen.values())


async def _upsert_skills(db, user_id: int, skills: list[dict]) -> None:
    """Insert or increment skill frequency. Safe against duplicates."""
    # Deduplicate incoming list by normalised name so we don't double-insert
    # within the same batch (e.g. "python" and "Python" → one entry)
    seen: dict[str, dict] = {}
    for skill in skills:
        name = skill.get("name", "").strip()
        if not name:
            continue
        key = name.lower()
        if key not in seen:
            seen[key] = skill
        else:
            # Merge frequencies
            seen[key]["frequency"] = seen[key].get("frequency", 1) + skill.get("frequency", 1) - 1

    for key, skill in seen.items():
        name = skill.get("name", "").strip()
        source = skill.get("source", "unknown")

        # Use scalars().all() then take first to safely handle any existing dupes in DB
        result = await db.execute(
            select(Skill).where(
                Skill.user_id == user_id,
                func.lower(Skill.name) == key,
            )
        )
        rows = result.scalars().all()

        if rows:
            existing = rows[0]
            # If somehow multiple dupes existed, delete the extras
            for extra in rows[1:]:
                await db.delete(extra)
            existing.frequency += skill.get("frequency", 1)
            if not existing.sources:
                existing.sources = []
            if source not in existing.sources:
                existing.sources = existing.sources + [source]
            db.add(existing)
        else:
            db.add(Skill(
                user_id=user_id,
                name=name,
                category=skill.get("category", "Other"),
                frequency=skill.get("frequency", 1),
                sources=[source],
            ))
    await db.flush()
