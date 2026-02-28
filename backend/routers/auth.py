"""
Auth Router – register, login, get current user.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from auth import (
    authenticate_user, create_user, create_access_token,
    get_current_user, get_user_by_email,
)
from schemas import UserRegister, TokenResponse, UserResponse
from models import User

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(payload: UserRegister, db: AsyncSession = Depends(get_db)):
    """Register a new user account."""
    user = await create_user(db, payload.email, payload.password, payload.full_name)
    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        email=user.email,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Login with email + password. Returns JWT."""
    user = await authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        email=user.email,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get the currently authenticated user."""
    return current_user


@router.put("/me", response_model=UserResponse)
async def update_me(
    github_url: str = None,
    linkedin_url: str = None,
    full_name: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update profile metadata."""
    if github_url is not None:
        current_user.github_url = github_url
    if linkedin_url is not None:
        current_user.linkedin_url = linkedin_url
    if full_name is not None:
        current_user.full_name = full_name
    db.add(current_user)
    await db.flush()
    await db.refresh(current_user)
    return current_user
