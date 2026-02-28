"""
SQLAlchemy ORM Models – Production-ready schema.
"""

from sqlalchemy import (
    Column, Integer, String, Text, Float, DateTime,
    ForeignKey, JSON, Enum as SAEnum
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from database import Base


class SourceType(str, enum.Enum):
    resume   = "resume"
    linkedin = "linkedin"
    github   = "github"


# ── Users ─────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id               = Column(Integer, primary_key=True, index=True)
    email            = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password  = Column(String(255), nullable=False)
    full_name        = Column(String(255), nullable=True)
    github_url       = Column(String(500), nullable=True)
    linkedin_url     = Column(String(500), nullable=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())
    updated_at       = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    resume           = relationship("Resume", back_populates="user",
                                    uselist=False, cascade="all, delete-orphan")
    experiences      = relationship("Experience", back_populates="user",
                                    cascade="all, delete-orphan")
    github_repos     = relationship("GitHubRepo", back_populates="user",
                                    cascade="all, delete-orphan")
    linkedin_profile = relationship("LinkedInProfile", back_populates="user",
                                    uselist=False, cascade="all, delete-orphan")
    job_applications = relationship("JobApplication", back_populates="user",
                                    cascade="all, delete-orphan")
    skills           = relationship("Skill", back_populates="user",
                                    cascade="all, delete-orphan")


# ── Resume ────────────────────────────────────────────────────────────────────

class Resume(Base):
    __tablename__ = "resumes"

    id               = Column(Integer, primary_key=True, index=True)
    user_id          = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    file_name        = Column(String(255), nullable=True)
    raw_text         = Column(Text, nullable=False)
    parsed_sections  = Column(JSON, nullable=True)   # {education:[], experience:[], skills:[]}
    chroma_indexed   = Column(Integer, default=0)    # 1 = indexed in ChromaDB
    updated_at       = Column(DateTime(timezone=True),
                               server_default=func.now(), onupdate=func.now())

    user             = relationship("User", back_populates="resume")


# ── Experience ────────────────────────────────────────────────────────────────

class Experience(Base):
    __tablename__ = "experiences"

    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False)
    source      = Column(SAEnum(SourceType), nullable=False)
    title       = Column(String(500), nullable=True)
    company     = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)
    start_date  = Column(String(50), nullable=True)
    end_date    = Column(String(50), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    user        = relationship("User", back_populates="experiences")


# ── LinkedIn Profile ───────────────────────────────────────────────────────────

class LinkedInProfile(Base):
    __tablename__ = "linkedin_profiles"

    id             = Column(Integer, primary_key=True, index=True)
    user_id        = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    about          = Column(Text, nullable=True)
    headline       = Column(String(500), nullable=True)
    experiences    = Column(JSON, nullable=True)   # list of experience dicts
    skills         = Column(JSON, nullable=True)   # list of skill strings
    certifications = Column(JSON, nullable=True)
    chroma_indexed = Column(Integer, default=0)
    updated_at     = Column(DateTime(timezone=True),
                             server_default=func.now(), onupdate=func.now())

    user           = relationship("User", back_populates="linkedin_profile")


# ── GitHub Repos ──────────────────────────────────────────────────────────────

class GitHubRepo(Base):
    __tablename__ = "github_repos"

    id             = Column(Integer, primary_key=True, index=True)
    user_id        = Column(Integer, ForeignKey("users.id"), nullable=False)
    repo_name      = Column(String(255), nullable=False)
    description    = Column(Text, nullable=True)
    language       = Column(String(100), nullable=True)
    languages_json = Column(JSON, nullable=True)   # {Python: 80, SQL: 20}
    stars          = Column(Integer, default=0)
    topics         = Column(JSON, nullable=True)   # list of strings
    readme_text    = Column(Text, nullable=True)
    html_url       = Column(String(500), nullable=True)
    pushed_at      = Column(String(50), nullable=True)
    chroma_indexed = Column(Integer, default=0)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())

    user           = relationship("User", back_populates="github_repos")


# ── Skills ────────────────────────────────────────────────────────────────────

class Skill(Base):
    __tablename__ = "skills"

    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False)
    name        = Column(String(200), nullable=False)
    category    = Column(String(100), nullable=True)   # ML, NLP, DevOps, etc.
    frequency   = Column(Integer, default=1)           # occurrences across sources
    sources     = Column(JSON, nullable=True)          # ["resume", "github"]
    updated_at  = Column(DateTime(timezone=True),
                          server_default=func.now(), onupdate=func.now())

    user        = relationship("User", back_populates="skills")


# ── Job Applications ────────────────────────────────────────────────────────────

class JobApplication(Base):
    __tablename__ = "job_applications"

    id                = Column(Integer, primary_key=True, index=True)
    user_id           = Column(Integer, ForeignKey("users.id"), nullable=False)
    job_title         = Column(String(300), nullable=True)
    company           = Column(String(300), nullable=True)
    job_url           = Column(String(500), nullable=True)
    job_description   = Column(Text, nullable=False)
    optimized_resume  = Column(Text, nullable=False)
    cover_letter      = Column(Text, nullable=False)
    reviewer_feedback = Column(Text, nullable=True)    # second model critique
    ats_score         = Column(Float, nullable=True)
    ats_breakdown     = Column(JSON, nullable=True)    # detailed score components
    missing_skills    = Column(JSON, nullable=True)    # list of strings
    matched_keywords  = Column(JSON, nullable=True)    # list of strings
    status            = Column(String(50), default="draft")  # draft/applied/rejected/interview
    notes             = Column(Text, nullable=True)
    created_at        = Column(DateTime(timezone=True), server_default=func.now())
    updated_at        = Column(DateTime(timezone=True), onupdate=func.now())

    user              = relationship("User", back_populates="job_applications")
