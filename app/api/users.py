from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.security import get_current_user, require_admin, get_password_hash
from ..database import get_db
from ..models.core import User
from ..repositories.user_repository import UserRepository
from ..schemas.core import UserSchema, UserCreateAdmin, UserUpdate

router = APIRouter()


@router.get("/", response_model=List[UserSchema], summary="List all users (admin)")
async def list_users(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> List[UserSchema]:
    return await UserRepository(db).get_all()


@router.get("/{user_id}", response_model=UserSchema, summary="Get user by ID")
async def get_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserSchema:
    if current_user.role != "admin" and str(current_user.id) != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    user = await UserRepository(db).get_by_id(user_id)  # type: ignore[arg-type]
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/", response_model=UserSchema, status_code=status.HTTP_201_CREATED, summary="Create user (admin)")
async def create_user(
    data: UserCreateAdmin,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> UserSchema:
    repo = UserRepository(db)
    if await repo.get_by_email(data.email):
        raise HTTPException(status_code=409, detail="A user with this email already exists")
    user = User(
        email=data.email,
        hashed_password=get_password_hash(data.password),
        role=data.role,
    )
    return await repo.create(user)


@router.put("/{user_id}", response_model=UserSchema, summary="Update user")
async def update_user(
    user_id: str,
    data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserSchema:
    if current_user.role != "admin" and str(current_user.id) != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)  # type: ignore[arg-type]
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if data.email is not None:
        user.email = data.email
    if data.role is not None:
        if current_user.role != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can change roles")
        user.role = data.role
    if data.password is not None:
        user.hashed_password = get_password_hash(data.password)
    return await repo.update(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete user (admin)")
async def delete_user(
    user_id: str,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)  # type: ignore[arg-type]
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await repo.delete(user)


@router.post("/{user_id}/approve", response_model=UserSchema, summary="Approve pending user (admin)")
async def approve_user(
    user_id: str,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> UserSchema:
    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)  # type: ignore[arg-type]
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.status = "active"
    return await repo.update(user)


@router.post("/{user_id}/reject", status_code=status.HTTP_200_OK, summary="Reject and delete pending user (admin)")
async def reject_user(
    user_id: str,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)  # type: ignore[arg-type]
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await repo.delete(user)
    return {"ok": True}
