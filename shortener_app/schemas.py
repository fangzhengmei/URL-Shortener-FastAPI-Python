# schemas.py
# Schema for request body and response body

from typing import Dict, List, Optional
from pydantic import BaseModel


class URLBase(BaseModel):
    target_url: str


class URL(URLBase):
    is_active: bool
    clicks: int

    class Config:
        orm_mode = True


class URLInfo(URL):
    url: str
    admin_url: str


class DailyClick(BaseModel):
    date: str
    clicks: int


class DeviceStat(BaseModel):
    count: int
    percentage: float


class BrowserStat(BaseModel):
    count: int
    percentage: float


class OSStat(BaseModel):
    count: int
    percentage: float


class RefererStat(BaseModel):
    referer: str
    count: int
    percentage: float


class CountryStat(BaseModel):
    count: int
    percentage: float


class ClickAnalytics(BaseModel):
    total_clicks: int
    daily_clicks: List[DailyClick]
    device_stats: Dict[str, DeviceStat]
    browser_stats: Dict[str, BrowserStat]
    os_stats: Dict[str, OSStat]
    referer_stats: List[RefererStat]
    country_stats: Dict[str, CountryStat]


class URLAnalytics(BaseModel):
    url: str
    target_url: str
    clicks: int
    analytics: ClickAnalytics
