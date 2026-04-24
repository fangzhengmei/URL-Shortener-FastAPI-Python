# schemas.py
# Schema for request body and response body

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class UserBase(BaseModel):
    username: str
    email: Optional[str] = None


class UserCreate(UserBase):
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


class User(UserBase):
    id: int
    is_active: bool
    is_admin: bool
    created_at: datetime
    last_login: Optional[datetime] = None

    class Config:
        orm_mode = True


class UserUpdate(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None


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
