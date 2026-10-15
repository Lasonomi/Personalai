"""Email/password registration and signed bearer-token authentication."""
import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.connection import get_db
from app.database.models.user import User
from app.schemas.user import UserResponse
from app.services.platform_link_service import CODE_TTL_SECONDS, create_user_link_code

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
TOKEN_TTL_SECONDS = 12 * 60 * 60
PASSWORD_ITERATIONS = 600_000


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    timezone: str = "Asia/Jakarta"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


def _secret() -> bytes:
    if settings.ENVIRONMENT.lower() == "production" and settings.SECRET_KEY == "change-me-in-production-please":
        raise RuntimeError("SECRET_KEY must be configured in production.")
    return settings.SECRET_KEY.encode("utf-8")


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${_b64encode(salt)}${_b64encode(derived)}"


def _verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algorithm, iterations, salt_text, digest_text = stored.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_text + "=" * (-len(salt_text) % 4))
        expected = base64.urlsafe_b64decode(digest_text + "=" * (-len(digest_text) % 4))
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iterations)
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _create_access_token(user_id: str) -> str:
    header = _b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64encode(
        json.dumps(
            {"sub": user_id, "exp": int(time.time()) + TOKEN_TTL_SECONDS},
            separators=(",", ":"),
        ).encode()
    )
    signing_input = f"{header}.{payload}".encode("ascii")
    signature = hmac.new(_secret(), signing_input, hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64encode(signature)}"


def _decode_access_token(token: str) -> UUID:
    try:
        header_text, payload_text, signature_text = token.split(".")
        signing_input = f"{header_text}.{payload_text}".encode("ascii")
        signature = base64.urlsafe_b64decode(
            signature_text + "=" * (-len(signature_text) % 4)
        )
        expected = hmac.new(_secret(), signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("Invalid signature")
        header = json.loads(
            base64.urlsafe_b64decode(header_text + "=" * (-len(header_text) % 4))
        )
        payload = json.loads(
            base64.urlsafe_b64decode(payload_text + "=" * (-len(payload_text) % 4))
        )
        if header.get("alg") != "HS256" or int(payload["exp"]) <= int(time.time()):
            raise ValueError("Expired token")
        return UUID(str(payload["sub"]))
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token tidak valid atau sudah kedaluwarsa.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    user_id = _decode_access_token(token)
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Akun untuk token ini tidak ditemukan.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    data: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        ZoneInfo(data.timezone)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise HTTPException(status_code=422, detail="Zona waktu tidak valid.") from error

    existing = await db.scalar(select(User.id).where(User.email == str(data.email).lower()))
    if existing:
        raise HTTPException(status_code=409, detail="Email sudah terdaftar.")
    user = User(
        name=data.name.strip(),
        email=str(data.email).lower(),
        password_hash=_hash_password(data.password),
        timezone=data.timezone,
        language="id",
    )
    db.add(user)
    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Email sudah terdaftar.") from error
    return TokenResponse(access_token=_create_access_token(str(user.id)), user=user, expires_in=TOKEN_TTL_SECONDS)


@router.post("/login", response_model=TokenResponse)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    email = form.username.strip().lower()
    user = await db.scalar(select(User).where(User.email == email))
    if not user or not _verify_password(form.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email atau password salah.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(access_token=_create_access_token(str(user.id)), user=user, expires_in=TOKEN_TTL_SECONDS)


@router.get("/me", response_model=UserResponse)
async def me(current_user: Annotated[User, Depends(get_current_user)]):
    return current_user


@router.post("/connect-code")
async def connect_code(current_user: Annotated[User, Depends(get_current_user)]):
    code = await create_user_link_code(str(current_user.id))
    return {
        "code": code,
        "expires_in": CODE_TTL_SECONDS,
        "instruction": "Kirim /connect <kode> ke bot Telegram atau Discord yang ingin dihubungkan.",
    }
