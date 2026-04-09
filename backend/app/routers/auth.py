"""
Authentication API router.
"""

from datetime import datetime
from fastapi import APIRouter, HTTPException, status
from passlib.context import CryptContext
from loguru import logger

from app.db.session import SessionLocal
from app.models import User as UserModel
from app.schemas.auth import SignupRequest, LoginRequest, AuthResponse, AuthUserResponse


router = APIRouter(
    prefix="/api/v1/auth",
    tags=["auth"],
)

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def _normalize_email(email: str) -> str:
    return email.strip().lower()


@router.post(
    "/signup",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create User Account",
)
async def signup(request: SignupRequest):
    db = SessionLocal()
    try:
        email = _normalize_email(request.email)
        existing = db.query(UserModel).filter(UserModel.email == email).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "UserExists",
                    "message": "An account with this email already exists.",
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )

        user = UserModel(
            email=email,
            hashed_password=pwd_context.hash(request.password),
            role=request.role or "Service Desk User",
            full_name=request.full_name,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        return AuthResponse(
            user=AuthUserResponse(
                email=user.email,
                role=user.role,
                full_name=user.full_name,
            ),
            message="Signup successful",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Signup failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "SignupError",
                "message": f"Failed to create account: {str(e)}",
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
    finally:
        db.close()


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Authenticate User",
)
async def login(request: LoginRequest):
    db = SessionLocal()
    try:
        email = _normalize_email(request.email)
        user = db.query(UserModel).filter(UserModel.email == email).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "AccountNotFound",
                    "message": "No account found for this email. Please create a new account.",
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "AccountInactive",
                    "message": "Your account is inactive. Please contact support.",
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )

        if not pwd_context.verify(request.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": "WrongPassword",
                    "message": "Wrong password. Please try again.",
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )

        return AuthResponse(
            user=AuthUserResponse(
                email=user.email,
                role=user.role,
                full_name=user.full_name,
            ),
            message="Login successful",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "LoginError",
                "message": f"Failed to authenticate user: {str(e)}",
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
    finally:
        db.close()
