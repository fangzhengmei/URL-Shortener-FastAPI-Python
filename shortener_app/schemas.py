# schemas.py
# Schema for request body and response body

from typing import List, Optional
from pydantic import BaseModel


class URLBase(BaseModel):
    target_url: str
    domain: Optional[str] = None


class URL(URLBase):
    is_active: bool
    clicks: int

    class Config:
        orm_mode = True


class URLInfo(URL):
    url: str
    admin_url: str


class URLListItem(BaseModel):
    key: str
    target_url: str
    is_active: bool
    clicks: int
    url: str
    admin_url: str

    class Config:
        orm_mode = True


class DomainStats(BaseModel):
    domain: str
    total_urls: int
    active_urls: int
    total_clicks: int


class DomainURLList(BaseModel):
    domain: str
    total: int
    urls: List[URLListItem]
