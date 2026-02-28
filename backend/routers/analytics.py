"""
Analytics Router – dashboard statistics, skill gaps, trends.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from collections import Counter

from database import get_db
from auth import get_current_user
from models import User, JobApplication, Skill
from schemas import AnalyticsSummary

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])


@router.get("/summary", response_model=AnalyticsSummary)
async def get_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Full analytics summary for dashboard."""
    apps = await _get_all_apps(db, current_user.id)

    if not apps:
        return AnalyticsSummary(
            total_applications=0,
            average_ats_score=0.0,
            highest_ats_score=0.0,
            most_common_missing_skills=[],
            applications_by_status={},
            skill_strength_ranking=[],
            recent_trend=[],
        )

    # ATS stats
    scores = [a.ats_score for a in apps if a.ats_score is not None]
    avg_ats  = round(sum(scores) / len(scores), 1) if scores else 0.0
    high_ats = round(max(scores), 1) if scores else 0.0

    # Missing skills aggregation
    missing_counter: Counter = Counter()
    for app in apps:
        for skill in (app.missing_skills or []):
            missing_counter[skill] += 1
    top_missing = [{"skill": k, "count": v}
                   for k, v in missing_counter.most_common(10)]

    # Status breakdown
    status_count: dict[str, int] = {}
    for app in apps:
        status_count[app.status] = status_count.get(app.status, 0) + 1

    # Skill strength ranking from profile
    skill_result = await db.execute(
        select(Skill.name, Skill.category, Skill.frequency)
        .where(Skill.user_id == current_user.id)
        .order_by(desc(Skill.frequency))
        .limit(20)
    )
    skill_ranking = [
        {"name": r[0], "category": r[1], "frequency": r[2]}
        for r in skill_result.fetchall()
    ]

    # Monthly trend (avg ATS score per month, last 6 months)
    monthly: dict[str, list[float]] = {}
    for app in apps:
        if app.ats_score and app.created_at:
            month_key = app.created_at.strftime("%Y-%m")
            if month_key not in monthly:
                monthly[month_key] = []
            monthly[month_key].append(app.ats_score)

    recent_trend = [
        {"month": m, "avg_ats": round(sum(v) / len(v), 1), "count": len(v)}
        for m, v in sorted(monthly.items())[-6:]
    ]

    return AnalyticsSummary(
        total_applications=len(apps),
        average_ats_score=avg_ats,
        highest_ats_score=high_ats,
        most_common_missing_skills=top_missing,
        applications_by_status=status_count,
        skill_strength_ranking=skill_ranking,
        recent_trend=recent_trend,
    )


@router.get("/ats-trend")
async def ats_trend(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return ATS scores over time for chart rendering."""
    apps = await _get_all_apps(db, current_user.id)
    return [
        {
            "id":         a.id,
            "job_title":  a.job_title or "Untitled",
            "company":    a.company or "",
            "ats_score":  a.ats_score or 0,
            "grade":      (a.ats_breakdown or {}).get("grade", "—"),
            "created_at": a.created_at.isoformat() if a.created_at else "",
            "status":     a.status,
        }
        for a in apps
    ]


@router.get("/skill-gaps")
async def skill_gaps(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Aggregate most frequent missing skills across all applications."""
    apps = await _get_all_apps(db, current_user.id)
    counter: Counter = Counter()
    for app in apps:
        for skill in (app.missing_skills or []):
            counter[skill] += 1
    return [{"skill": k, "count": v} for k, v in counter.most_common(20)]


async def _get_all_apps(db: AsyncSession, user_id: int) -> list:
    result = await db.execute(
        select(JobApplication)
        .where(JobApplication.user_id == user_id)
        .order_by(JobApplication.created_at.desc())
    )
    return result.scalars().all()
