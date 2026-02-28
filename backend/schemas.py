"""
Pydantic v2 schemas for request/response validation.
"""

from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
import enum


# ── Auth ──────────────────────────────────────────────────────────────────────

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    email: str


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: Optional[str]
    github_url: Optional[str]
    linkedin_url: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Resume ────────────────────────────────────────────────────────────────────

class ResumeBase(BaseModel):
    raw_text: str
    file_name: Optional[str] = None


class ResumeResponse(BaseModel):
    id: int
    user_id: int
    file_name: Optional[str]
    raw_text: str
    parsed_sections: Optional[Dict[str, Any]]
    chroma_indexed: int
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── LinkedIn ──────────────────────────────────────────────────────────────────

class LinkedInInput(BaseModel):
    about: Optional[str] = None
    headline: Optional[str] = None
    experiences_text: Optional[str] = None   # raw paste from LinkedIn
    skills_text: Optional[str] = None        # comma-sep or newline-sep skills
    certifications_text: Optional[str] = None


class LinkedInResponse(BaseModel):
    id: int
    user_id: int
    about: Optional[str]
    headline: Optional[str]
    skills: Optional[List[str]]
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── GitHub ────────────────────────────────────────────────────────────────────

class GitHubFetchRequest(BaseModel):
    github_url: str   # profile URL or username


class GitHubRepoResponse(BaseModel):
    id: int
    repo_name: str
    description: Optional[str]
    language: Optional[str]
    stars: int
    topics: Optional[List[str]]
    html_url: Optional[str]

    model_config = {"from_attributes": True}


# ── Skills ────────────────────────────────────────────────────────────────────

class SkillResponse(BaseModel):
    id: int
    name: str
    category: Optional[str]
    frequency: int
    sources: Optional[List[str]]

    model_config = {"from_attributes": True}


# ── Job Application ───────────────────────────────────────────────────────────

class JobOptimizeRequest(BaseModel):
    job_description: str
    job_title: Optional[str] = None
    company: Optional[str] = None
    job_url: Optional[str] = None


class ATSBreakdown(BaseModel):
    keyword_score: float
    semantic_score: float
    skill_score: float
    format_score: float
    total_score: float
    grade: str
    verdict: str


class JobApplicationResponse(BaseModel):
    id: int
    job_title: Optional[str]
    company: Optional[str]
    job_description: str
    optimized_resume: str
    cover_letter: str
    reviewer_feedback: Optional[str]
    ats_score: Optional[float]
    ats_breakdown: Optional[Dict[str, Any]]
    missing_skills: Optional[List[str]]
    matched_keywords: Optional[List[str]]
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ApplicationStatusUpdate(BaseModel):
    status: str
    notes: Optional[str] = None


# ── Analytics ─────────────────────────────────────────────────────────────────

class AnalyticsSummary(BaseModel):
    total_applications: int
    average_ats_score: float
    highest_ats_score: float
    most_common_missing_skills: List[Dict[str, Any]]
    applications_by_status: Dict[str, int]
    skill_strength_ranking: List[Dict[str, Any]]
    recent_trend: List[Dict[str, Any]]  # monthly avg ATS scores


# ── Profile ───────────────────────────────────────────────────────────────────

class ProfileResponse(BaseModel):
    user: UserResponse
    resume: Optional[ResumeResponse]
    linkedin: Optional[LinkedInResponse]
    github_repos: List[GitHubRepoResponse]
    skills: List[SkillResponse]
    total_applications: int


# ── Streaming / SSE ───────────────────────────────────────────────────────────

class StreamChunk(BaseModel):
    type: str       # "resume_token" | "cover_token" | "done" | "error"
    content: str
    metadata: Optional[Dict[str, Any]] = None
