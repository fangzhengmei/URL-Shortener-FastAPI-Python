# crud.py
# Implement helper functions for CRUD operations on database

from datetime import datetime, timedelta
from typing import Dict, List, Optional
from sqlalchemy import func, and_
from sqlalchemy.orm import Session
from . import keygen, models, schemas
from .constants import MIN_DAYS, MAX_DAYS, DEFAULT_DAYS
from .geolocator import get_geolocation


def create_db_url(db: Session, url: schemas.URLBase) -> models.URL:
    key = keygen.create_unique_random_key(db)
    secret_key = f"{key}_{keygen.create_random_key(length=8)}"
    db_url = models.URL(
        target_url=url.target_url, key=key, secret_key=secret_key
    )
    db.add(db_url)
    db.commit()
    db.refresh(db_url)
    return db_url


def get_db_url_by_key(db: Session, url_key: str) -> models.URL:
    return (
        db.query(models.URL)
        .filter(models.URL.key == url_key, models.URL.is_active)
        .first()
    )


def get_db_url_by_secret_key(db: Session, secret_key: str) -> models.URL:
    return (
        db.query(models.URL)
        .filter(models.URL.secret_key == secret_key, models.URL.is_active)
        .first()
    )


def parse_user_agent(user_agent: str) -> Dict:
    device_type = "unknown"
    browser = "unknown"
    browser_version = "unknown"
    os = "unknown"
    os_version = "unknown"

    if user_agent:
        ua_lower = user_agent.lower()
        
        if "mobile" in ua_lower:
            device_type = "mobile"
        elif "tablet" in ua_lower:
            device_type = "tablet"
        elif "ipad" in ua_lower:
            device_type = "tablet"
        else:
            device_type = "desktop"
        
        if "chrome" in ua_lower and "chromium" not in ua_lower:
            browser = "Chrome"
            try:
                chrome_idx = ua_lower.find("chrome/")
                if chrome_idx != -1:
                    version = user_agent[chrome_idx + 7:].split()[0]
                    browser_version = version.split(".")[0]
            except:
                pass
        elif "firefox" in ua_lower:
            browser = "Firefox"
            try:
                ff_idx = ua_lower.find("firefox/")
                if ff_idx != -1:
                    version = user_agent[ff_idx + 8:].split()[0]
                    browser_version = version.split(".")[0]
            except:
                pass
        elif "safari" in ua_lower and "chrome" not in ua_lower:
            browser = "Safari"
            try:
                version_idx = ua_lower.find("version/")
                if version_idx != -1:
                    version = user_agent[version_idx + 8:].split()[0]
                    browser_version = version.split(".")[0]
            except:
                pass
        elif "edge" in ua_lower or "edg" in ua_lower:
            browser = "Edge"
        elif "msie" in ua_lower or "trident" in ua_lower:
            browser = "Internet Explorer"
        elif "opera" in ua_lower or "opr" in ua_lower:
            browser = "Opera"
        
        if "windows" in ua_lower:
            os = "Windows"
            if "windows nt 10" in ua_lower:
                os_version = "10"
            elif "windows nt 6.3" in ua_lower:
                os_version = "8.1"
            elif "windows nt 6.2" in ua_lower:
                os_version = "8"
            elif "windows nt 6.1" in ua_lower:
                os_version = "7"
        elif "mac os x" in ua_lower or "macos" in ua_lower:
            os = "macOS"
            try:
                if "mac os x" in ua_lower:
                    os_idx = ua_lower.find("mac os x")
                    if os_idx != -1:
                        version_part = user_agent[os_idx:].split()[2]
                        os_version = version_part.replace("_", ".")
            except:
                pass
        elif "android" in ua_lower:
            os = "Android"
            try:
                and_idx = ua_lower.find("android ")
                if and_idx != -1:
                    version = user_agent[and_idx + 8:].split(";")[0].strip()
                    os_version = version.split(".")[0]
            except:
                pass
        elif "iphone" in ua_lower or "ipad" in ua_lower:
            os = "iOS"
            try:
                os_idx = ua_lower.find("os ")
                if os_idx != -1:
                    version_part = user_agent[os_idx + 3:].split()[0]
                    os_version = version_part.replace("_", ".")
            except:
                pass
        elif "linux" in ua_lower:
            os = "Linux"

    return {
        "device_type": device_type,
        "browser": browser,
        "browser_version": browser_version,
        "os": os,
        "os_version": os_version
    }


def create_click_log(
    db: Session,
    url_id: int,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    referer: Optional[str] = None
) -> models.ClickLog:
    parsed_ua = parse_user_agent(user_agent)
    country, region, city = get_geolocation(ip_address) if ip_address else (None, None, None)
    
    click_log = models.ClickLog(
        url_id=url_id,
        ip_address=ip_address,
        user_agent=user_agent,
        referer=referer,
        country=country,
        region=region,
        city=city,
        device_type=parsed_ua["device_type"],
        browser=parsed_ua["browser"],
        browser_version=parsed_ua["browser_version"],
        os=parsed_ua["os"],
        os_version=parsed_ua["os_version"]
    )
    db.add(click_log)
    db.commit()
    db.refresh(click_log)
    return click_log


def update_db_clicks(
    db: Session,
    db_url: schemas.URL,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    referer: Optional[str] = None
) -> models.URL:
    db_url.clicks += 1
    create_click_log(
        db=db,
        url_id=db_url.id,
        ip_address=ip_address,
        user_agent=user_agent,
        referer=referer
    )
    db.commit()
    db.refresh(db_url)
    return db_url


def deactivate_db_url_by_secret_key(
        db: Session, secret_key: str
) -> models.URL:
    db_url = get_db_url_by_secret_key(db, secret_key)
    if db_url:
        db_url.is_active = False
        db.commit()
        db.refresh(db_url)
    return db_url


def get_daily_clicks(
    db: Session,
    url_id: int,
    days: int = DEFAULT_DAYS
) -> List[Dict]:
    days = max(MIN_DAYS, min(MAX_DAYS, int(days)))
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    results = (
        db.query(
            func.date(models.ClickLog.clicked_at).label("date"),
            func.count(models.ClickLog.id).label("clicks")
        )
        .filter(
            models.ClickLog.url_id == url_id,
            models.ClickLog.clicked_at >= start_date,
            models.ClickLog.clicked_at <= end_date
        )
        .group_by(func.date(models.ClickLog.clicked_at))
        .order_by(func.date(models.ClickLog.clicked_at))
        .all()
    )
    
    date_clicks = {}
    for result in results:
        date_clicks[result.date] = result.clicks
    
    full_data = []
    for i in range(days, -1, -1):
        date = (end_date - timedelta(days=i)).date()
        full_data.append({
            "date": date.isoformat(),
            "clicks": date_clicks.get(date, 0)
        })
    
    return full_data


def get_device_stats(db: Session, url_id: int) -> Dict:
    results = (
        db.query(
            models.ClickLog.device_type,
            func.count(models.ClickLog.id).label("count")
        )
        .filter(models.ClickLog.url_id == url_id)
        .group_by(models.ClickLog.device_type)
        .all()
    )
    
    total = sum(result.count for result in results) if results else 0
    stats = {}
    for result in results:
        percentage = (result.count / total * 100) if total > 0 else 0
        stats[result.device_type or "unknown"] = {
            "count": result.count,
            "percentage": round(percentage, 2)
        }
    
    return stats


def get_browser_stats(db: Session, url_id: int) -> Dict:
    results = (
        db.query(
            models.ClickLog.browser,
            func.count(models.ClickLog.id).label("count")
        )
        .filter(models.ClickLog.url_id == url_id)
        .group_by(models.ClickLog.browser)
        .all()
    )
    
    total = sum(result.count for result in results) if results else 0
    stats = {}
    for result in results:
        percentage = (result.count / total * 100) if total > 0 else 0
        stats[result.browser or "unknown"] = {
            "count": result.count,
            "percentage": round(percentage, 2)
        }
    
    return stats


def get_os_stats(db: Session, url_id: int) -> Dict:
    results = (
        db.query(
            models.ClickLog.os,
            func.count(models.ClickLog.id).label("count")
        )
        .filter(models.ClickLog.url_id == url_id)
        .group_by(models.ClickLog.os)
        .all()
    )
    
    total = sum(result.count for result in results) if results else 0
    stats = {}
    for result in results:
        percentage = (result.count / total * 100) if total > 0 else 0
        stats[result.os or "unknown"] = {
            "count": result.count,
            "percentage": round(percentage, 2)
        }
    
    return stats


def get_referer_stats(db: Session, url_id: int) -> List[Dict]:
    results = (
        db.query(
            models.ClickLog.referer,
            func.count(models.ClickLog.id).label("count")
        )
        .filter(
            models.ClickLog.url_id == url_id,
            models.ClickLog.referer != None,
            models.ClickLog.referer != ""
        )
        .group_by(models.ClickLog.referer)
        .order_by(func.count(models.ClickLog.id).desc())
        .all()
    )
    
    total = sum(result.count for result in results) if results else 0
    stats = []
    for result in results:
        percentage = (result.count / total * 100) if total > 0 else 0
        stats.append({
            "referer": result.referer,
            "count": result.count,
            "percentage": round(percentage, 2)
        })
    
    return stats


def get_country_stats(db: Session, url_id: int) -> Dict:
    results = (
        db.query(
            models.ClickLog.country,
            func.count(models.ClickLog.id).label("count")
        )
        .filter(
            models.ClickLog.url_id == url_id,
            models.ClickLog.country != None,
            models.ClickLog.country != ""
        )
        .group_by(models.ClickLog.country)
        .all()
    )
    
    total = sum(result.count for result in results) if results else 0
    stats = {}
    for result in results:
        percentage = (result.count / total * 100) if total > 0 else 0
        stats[result.country] = {
            "count": result.count,
            "percentage": round(percentage, 2)
        }
    
    return stats


def get_click_analytics(db: Session, url_id: int, days: int = DEFAULT_DAYS) -> Dict:
    return {
        "total_clicks": db.query(models.ClickLog).filter(models.ClickLog.url_id == url_id).count(),
        "daily_clicks": get_daily_clicks(db, url_id, days),
        "device_stats": get_device_stats(db, url_id),
        "browser_stats": get_browser_stats(db, url_id),
        "os_stats": get_os_stats(db, url_id),
        "referer_stats": get_referer_stats(db, url_id),
        "country_stats": get_country_stats(db, url_id)
    }
