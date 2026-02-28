"""
Applications Router – AI-powered resume optimization + cover letter generation.
Full RAG pipeline: retrieve → augment → generate → score → store.

POST /api/applications/optimize   – main endpoint (streaming SSE)
GET  /api/applications            – list applications
GET  /api/applications/{id}       – get one
PUT  /api/applications/{id}/status
DELETE /api/applications/{id}
GET  /api/applications/{id}/download/resume/pdf
GET  /api/applications/{id}/download/cover/pdf
"""

import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import AsyncGenerator

from database import get_db
from auth import get_current_user
from models import User, JobApplication, Resume, GitHubRepo, Skill
from schemas import (
    JobOptimizeRequest, JobApplicationResponse, ApplicationStatusUpdate,
)
from services.llm_service import (
    tailor_resume_stream, generate_cover_letter_stream,
    tailor_resume, generate_cover_letter,
    review_resume, analyze_ats_llm,
)
from services.rag_service import retrieve_for_jd, compute_semantic_similarity
from services.ats_service import compute_ats_score
from services.pdf_generator import generate_pdf, generate_docx
from services.skill_extractor import get_skill_gap

router = APIRouter(prefix="/api/applications", tags=["Applications"])


# ── Main Optimization Endpoint (Streaming SSE) ────────────────────────────────

@router.post("/optimize/stream")
async def optimize_stream(
    payload: JobOptimizeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Full pipeline with Server-Sent Events streaming:
    1. RAG retrieval
    2. Stream tailored resume tokens
    3. Stream cover letter tokens
    4. Reviewer pass
    5. ATS scoring
    6. Persist to DB
    7. Stream final metadata (ATS score, app_id)
    """
    resume = await _require_resume(db, current_user.id)
    github_summary = await _build_github_summary(db, current_user.id)
    user_skills = await _get_skill_names(db, current_user.id)

    async def event_generator() -> AsyncGenerator[str, None]:
        # ── Step 1: RAG retrieval ──────────────────────────────────────────
        yield _sse("status", "Retrieving relevant context from your profile...")
        rag = retrieve_for_jd(current_user.id, payload.job_description)

        # ── Step 2: Stream tailored resume ────────────────────────────────
        yield _sse("status", "✍️ Tailoring resume with AI...")
        tailored_resume = ""
        async for token in tailor_resume_stream(
            original_resume=resume.raw_text,
            job_description=payload.job_description,
            rag_context=rag["context"],
            github_summary=github_summary,
        ):
            tailored_resume += token
            yield _sse("resume_token", token)

        yield _sse("resume_done", "")

        # ── Step 3: Stream cover letter ───────────────────────────────────
        yield _sse("status", "✉️ Writing cover letter...")
        cover_letter = ""
        async for token in generate_cover_letter_stream(
            tailored_resume=tailored_resume,
            job_description=payload.job_description,
            job_title=payload.job_title or "",
            company=payload.company or "",
            github_highlights=github_summary[:500] if github_summary else "",
        ):
            cover_letter += token
            yield _sse("cover_token", token)

        yield _sse("cover_done", "")

        # ── Step 4: Reviewer pass ─────────────────────────────────────────
        yield _sse("status", "🔍 Running reviewer analysis...")
        reviewer_feedback = await review_resume(tailored_resume, payload.job_description)
        yield _sse("reviewer_done", reviewer_feedback[:500])

        # ── Step 5: ATS Scoring ───────────────────────────────────────────
        yield _sse("status", "📊 Computing ATS score...")
        semantic_sim = compute_semantic_similarity(tailored_resume, payload.job_description)
        llm_analysis  = await analyze_ats_llm(tailored_resume, payload.job_description)
        ats_result     = compute_ats_score(
            resume_text=tailored_resume,
            job_description=payload.job_description,
            user_skills=user_skills,
            semantic_similarity=semantic_sim,
            llm_analysis=llm_analysis,
        )

        # ── Step 6: Persist ───────────────────────────────────────────────
        yield _sse("status", "💾 Saving application...")
        app = JobApplication(
            user_id=current_user.id,
            job_title=payload.job_title,
            company=payload.company,
            job_url=payload.job_url,
            job_description=payload.job_description,
            optimized_resume=tailored_resume,
            cover_letter=cover_letter,
            reviewer_feedback=reviewer_feedback,
            ats_score=ats_result["total_score"],
            ats_breakdown=ats_result,
            missing_skills=ats_result.get("missing_skills", []),
            matched_keywords=ats_result.get("matched_keywords", []),
        )
        db.add(app)
        await db.commit()
        await db.refresh(app)

        # ── Step 7: Final metadata ────────────────────────────────────────
        yield _sse("done", json.dumps({
            "app_id":       app.id,
            "ats_score":    ats_result["total_score"],
            "grade":        ats_result["grade"],
            "verdict":      ats_result["verdict"],
            "ats_breakdown": ats_result,
        }))

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/optimize", response_model=JobApplicationResponse)
async def optimize(
    payload: JobOptimizeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Non-streaming optimization endpoint.
    Runs full pipeline and returns complete application object.
    """
    resume = await _require_resume(db, current_user.id)
    github_summary = await _build_github_summary(db, current_user.id)
    user_skills = await _get_skill_names(db, current_user.id)

    # RAG retrieval
    rag = retrieve_for_jd(current_user.id, payload.job_description)

    # Generate resume + cover letter
    tailored = await tailor_resume(
        original_resume=resume.raw_text,
        job_description=payload.job_description,
        rag_context=rag["context"],
        github_summary=github_summary,
    )
    cover = await generate_cover_letter(
        tailored_resume=tailored,
        job_description=payload.job_description,
        job_title=payload.job_title or "",
        company=payload.company or "",
        github_highlights=github_summary[:500] if github_summary else "",
    )
    reviewer = await review_resume(tailored, payload.job_description)

    # ATS score
    semantic_sim = compute_semantic_similarity(tailored, payload.job_description)
    llm_analysis  = await analyze_ats_llm(tailored, payload.job_description)
    ats_result     = compute_ats_score(
        resume_text=tailored,
        job_description=payload.job_description,
        user_skills=user_skills,
        semantic_similarity=semantic_sim,
        llm_analysis=llm_analysis,
    )

    # Persist
    app = JobApplication(
        user_id=current_user.id,
        job_title=payload.job_title,
        company=payload.company,
        job_url=payload.job_url,
        job_description=payload.job_description,
        optimized_resume=tailored,
        cover_letter=cover,
        reviewer_feedback=reviewer,
        ats_score=ats_result["total_score"],
        ats_breakdown=ats_result,
        missing_skills=ats_result.get("missing_skills", []),
        matched_keywords=ats_result.get("matched_keywords", []),
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[JobApplicationResponse])
async def list_applications(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(JobApplication)
        .where(JobApplication.user_id == current_user.id)
        .order_by(JobApplication.created_at.desc())
        .limit(limit).offset(offset)
    )
    return result.scalars().all()


@router.get("/{app_id}", response_model=JobApplicationResponse)
async def get_application(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    app = await _require_app(db, app_id, current_user.id)
    return app


@router.put("/{app_id}/status")
async def update_status(
    app_id: int,
    payload: ApplicationStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    app = await _require_app(db, app_id, current_user.id)
    valid_statuses = {"draft", "applied", "interview", "rejected", "offer"}
    if payload.status not in valid_statuses:
        raise HTTPException(400, f"Status must be one of: {valid_statuses}")
    app.status = payload.status
    if payload.notes:
        app.notes = payload.notes
    db.add(app)
    await db.commit()
    return {"message": "Status updated", "status": app.status}


@router.delete("/{app_id}")
async def delete_application(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    app = await _require_app(db, app_id, current_user.id)
    await db.delete(app)
    await db.commit()
    return {"message": "Deleted"}


# ── Document Downloads ────────────────────────────────────────────────────────

@router.get("/{app_id}/download/resume/pdf")
async def download_resume_pdf(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    app = await _require_app(db, app_id, current_user.id)
    pdf = generate_pdf(app.optimized_resume, f"Resume – {app.job_title or 'Position'}")
    fname = f"resume_{(app.job_title or 'position').replace(' ','_')}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename={fname}"})


@router.get("/{app_id}/download/resume/docx")
async def download_resume_docx(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    app = await _require_app(db, app_id, current_user.id)
    docx = generate_docx(app.optimized_resume)
    fname = f"resume_{(app.job_title or 'position').replace(' ','_')}.docx"
    return Response(
        content=docx,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


@router.get("/{app_id}/download/cover/pdf")
async def download_cover_pdf(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    app = await _require_app(db, app_id, current_user.id)
    pdf = generate_pdf(app.cover_letter, f"Cover Letter – {app.job_title or 'Position'}")
    fname = f"cover_letter_{(app.job_title or 'position').replace(' ','_')}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename={fname}"})


@router.get("/{app_id}/download/cover/docx")
async def download_cover_docx(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    app = await _require_app(db, app_id, current_user.id)
    docx = generate_docx(app.cover_letter)
    fname = f"cover_letter_{(app.job_title or 'position').replace(' ','_')}.docx"
    return Response(
        content=docx,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _require_resume(db, user_id: int):
    result = await db.execute(select(Resume).where(Resume.user_id == user_id))
    resume = result.scalar_one_or_none()
    if not resume:
        raise HTTPException(400, "Upload your resume first via /api/profile/resume")
    return resume


async def _require_app(db, app_id: int, user_id: int):
    result = await db.execute(
        select(JobApplication).where(
            JobApplication.id == app_id,
            JobApplication.user_id == user_id,
        )
    )
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(404, "Application not found")
    return app


async def _build_github_summary(db, user_id: int) -> str:
    result = await db.execute(
        select(GitHubRepo).where(GitHubRepo.user_id == user_id)
        .order_by(GitHubRepo.stars.desc()).limit(10)
    )
    repos = result.scalars().all()
    if not repos:
        return ""
    lines = []
    for r in repos:
        lang = f"[{r.language}]" if r.language else ""
        desc = f" – {r.description}" if r.description else ""
        stars = f" ⭐{r.stars}" if r.stars else ""
        topics = f" | {', '.join(r.topics[:4])}" if r.topics else ""
        lines.append(f"• {r.repo_name} {lang}{stars}{desc}{topics}")
    return "\n".join(lines)


async def _get_skill_names(db, user_id: int) -> list[str]:
    result = await db.execute(select(Skill.name).where(Skill.user_id == user_id))
    return [row[0] for row in result.fetchall()]


def _sse(event_type: str, data: str) -> str:
    return f"data: {json.dumps({'type': event_type, 'content': data})}\n\n"
