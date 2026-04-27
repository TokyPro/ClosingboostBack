from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    get_current_user,
    get_password_hash,
    verify_password,
)
from ..database import get_db
from ..models.core import User
from ..repositories.user_repository import UserRepository
from ..schemas.core import RegisterRequest, Token, UserSchema

router = APIRouter()


@router.post("/login", response_model=Token, summary="Authenticate and receive a JWT")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> Token:
    repo = UserRepository(db)
    user = await repo.get_by_email(form_data.username)
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if getattr(user, "status", "active") == "pending":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Votre compte est en attente de validation par un administrateur",
        )
    token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return Token(access_token=token, token_type="bearer")


@router.post("/register", response_model=UserSchema, status_code=status.HTTP_201_CREATED, summary="Register a new account (pending approval)")
async def register(
    data: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> UserSchema:
    repo = UserRepository(db)
    if await repo.get_by_email(data.email):
        raise HTTPException(status_code=409, detail="Un compte avec cet email existe déjà")
    user = User(
        email=data.email,
        hashed_password=get_password_hash(data.password),
        role="executive",
        status="pending",
    )
    return await repo.create(user)


@router.get("/me", response_model=UserSchema, summary="Get the current authenticated user")
async def get_me(current_user=Depends(get_current_user)) -> UserSchema:
    return current_user
