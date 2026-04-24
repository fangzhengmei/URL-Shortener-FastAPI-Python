# schemas.py
# Schema for request body and response body

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, validator

from .config import get_settings


class UserBase(BaseModel):
    username: str
    email: Optional[str] = None

    @validator('username')
    def validate_username(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError('Username cannot be empty')
        if len(v) < 2:
            raise ValueError('Username must be at least 2 characters')
        if len(v) > 50:
            raise ValueError('Username must be less than 50 characters')
        return v.strip()


class UserCreate(UserBase):
    password: str
    invite_code: Optional[str] = None

    @validator('password')
    def validate_password(cls, v):
        settings = get_settings()
        if not v or len(v.strip()) == 0:
            raise ValueError('Password cannot be empty')
        if len(v) < settings.min_password_length:
            raise ValueError(f'Password must be at least {settings.min_password_length} characters')
        if len(v) > 128:
            raise ValueError('Password must be less than 128 characters')
        return v


class UserLogin(BaseModel):
    username: str
    password: str


class User(UserBase):
    id: int
    is_active: bool
    is_admin: bool
    created_at: datetime
    last_login: Optional[datetime] = None
    last_password_change: Optional[datetime] = None
    failed_login_attempts: int = 0
    locked_until: Optional[datetime] = None

    class Config:
        orm_mode = True


class UserUpdate(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None

    @validator('password')
    def validate_password(cls, v):
        if v is None:
            return v
        settings = get_settings()
        if len(v) < settings.min_password_length:
            raise ValueError(f'Password must be at least {settings.min_password_length} characters')
        if len(v) > 128:
            raise ValueError('Password must be less than 128 characters')
        return v


class AdminUserCreate(UserBase):
    password: str
    is_admin: bool = False

    @validator('password')
    def validate_password(cls, v):
        settings = get_settings()
        if not v or len(v.strip()) == 0:
            raise ValueError('Password cannot be empty')
        if len(v) < settings.min_password_length:
            raise ValueError(f'Password must be at least {settings.min_password_length} characters')
        if len(v) > 128:
            raise ValueError('Password must be less than 128 characters')
        return v


class URLBase(BaseModel):
    target_url: str


class URL(URLBase):
    is_active: bool
    clicks: int
    created_at: datetime

    class Config:
        orm_mode = True


class URLInfo(URL):
    url: str
    admin_url: str
    user_id: Optional[int] = None


class URLList(URL):
    key: str
    secret_key: str
    url: str
    admin_url: str


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None
    jti: Optional[str] = None


class AuthSettings(BaseModel):
    allow_public_registration: bool
    invite_code_required: bool
    min_password_length: int


class LogoutResponse(BaseModel):
    detail: str = "Logged out successfully"


class AuditLog(BaseModel):
    id: int
    timestamp: datetime
    user_id: Optional[int] = None
    username: Optional[str] = None
    event_type: str
    event_description: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    success: bool
    error_message: Optional[str] = None

    class Config:
        orm_mode = True


class AuditLogList(BaseModel):
    total: int
    logs: List[AuditLog]
