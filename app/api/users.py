from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from ..database import get_db
from ..repositories.user_repository import UserRepository
from ..models.core import User
from ..schemas.core import UserSchema, UserCreateAdmin, UserUpdate
from ..core.security import get_password_hash

router = APIRouter()


@router.get("/", response_model=List[UserSchema], summary="List all users")
async def list_users(db: AsyncSession = Depends(get_db)) -> List[UserSchema]:
    repo = UserRepository(db)
    return await repo.get_all()


@router.get("/{user_id}", response_model=UserSchema, summary="Get user by ID")
async def get_user(user_id: str, db: AsyncSession = Depends(get_db)) -> UserSchema:
    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/", response_model=UserSchema, status_code=status.HTTP_201_CREATED, summary="Create user")
async def create_user(data: UserCreateAdmin, db: AsyncSession = Depends(get_db)) -> UserSchema:
    repo = UserRepository(db)
    existing = await repo.get_by_email(data.email)
    if existing:
        raise HTTPException(status_code=409, detail="A user with this email already exists")
    user = User(
        email=data.email,
        hashed_password=get_password_hash(data.password),
        role=data.role,
    )
    return await repo.create(user)


@router.put("/{user_id}", response_model=UserSchema, summary="Update user")
async def update_user(user_id: str, data: UserUpdate, db: AsyncSession = Depends(get_db)) -> UserSchema:
    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if data.email is not None:
        user.email = data.email
    if data.role is not None:
        user.role = data.role
    if data.password is not None:
        user.hashed_password = get_password_hash(data.password)
    return await repo.update(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete user")
async def delete_user(user_id: str, db: AsyncSession = Depends(get_db)) -> None:
    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await repo.delete(user)
