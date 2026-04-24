# main.py
# FastAPI Implementation

from typing import Optional
import validators
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from starlette.datastructures import URL
from . import crud, models, schemas
from .database import SessionLocal, engine
from .config import get_settings
from .constants import MIN_DAYS, MAX_DAYS, DEFAULT_DAYS

app = FastAPI()
models.Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_client_ip(request: Request) -> Optional[str]:
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    x_real_ip = request.headers.get("X-Real-IP")
    if x_real_ip:
        return x_real_ip
    return request.client.host if request.client else None


def get_admin_info(db_url: models.URL) -> schemas.URLInfo:
    base_url = URL(get_settings().base_url)
    admin_endpoint = app.url_path_for(
        "administration info", secret_key=db_url.secret_key
    )
    db_url.url = str(base_url.replace(path=db_url.key))
    db_url.admin_url = str(base_url.replace(path=admin_endpoint))
    return db_url


def raise_bad_request(message):
    raise HTTPException(status_code=400, detail=message)


def raise_not_found(request):
    message = f"URL '{request.url}' doesn't exist"
    raise HTTPException(status_code=404, detail=message)


@app.get("/")
def read_root():
    return "Welcome to the URL shortener API ;-)"


@app.post("/url", response_model=schemas.URLInfo)
def create_url(url: schemas.URLBase, db: Session = Depends(get_db)):
    if not validators.url(url.target_url):
        raise_bad_request(message="Your provided URL is not valid")

    db_url = crud.create_db_url(db=db, url=url)
    return get_admin_info(db_url)


@app.get("/{url_key}")
def forward_to_target_url(
        url_key: str,
        request: Request,
        db: Session = Depends(get_db)
):
    if db_url := crud.get_db_url_by_key(db=db, url_key=url_key):
        ip_address = get_client_ip(request)
        user_agent = request.headers.get("User-Agent")
        referer = request.headers.get("Referer")
        
        crud.update_db_clicks(
            db=db, 
            db_url=db_url,
            ip_address=ip_address,
            user_agent=user_agent,
            referer=referer
        )
        return RedirectResponse(db_url.target_url)
    else:
        raise_not_found(request)


@app.get(
    "/admin/{secret_key}",
    name="administration info",
    response_model=schemas.URLInfo,
)
def get_url_info(
        secret_key: str, request: Request, db: Session = Depends(get_db)
):
    if db_url := crud.get_db_url_by_secret_key(db, secret_key=secret_key):
        db_url.url = db_url.key
        db_url.admin_url = db_url.secret_key
        return get_admin_info(db_url)
    else:
        raise_not_found(request)


@app.get(
    "/admin/{secret_key}/analytics",
    response_model=schemas.URLAnalytics,
)
def get_url_analytics(
        secret_key: str,
        request: Request,
        days: int = Query(
            default=DEFAULT_DAYS,
            ge=MIN_DAYS,
            le=MAX_DAYS,
            description=f"Number of days to analyze (range: {MIN_DAYS}-{MAX_DAYS})"
        ),
        db: Session = Depends(get_db)
):
    if db_url := crud.get_db_url_by_secret_key(db, secret_key=secret_key):
        analytics = crud.get_click_analytics(db=db, url_id=db_url.id, days=days)
        base_url = URL(get_settings().base_url)
        return schemas.URLAnalytics(
            url=str(base_url.replace(path=db_url.key)),
            target_url=db_url.target_url,
            clicks=db_url.clicks,
            analytics=schemas.ClickAnalytics(**analytics)
        )
    else:
        raise_not_found(request)


@app.get(
    "/admin/{secret_key}/analytics/daily",
)
def get_daily_analytics(
        secret_key: str,
        request: Request,
        days: int = Query(
            default=DEFAULT_DAYS,
            ge=MIN_DAYS,
            le=MAX_DAYS,
            description=f"Number of days to analyze (range: {MIN_DAYS}-{MAX_DAYS})"
        ),
        db: Session = Depends(get_db)
):
    if db_url := crud.get_db_url_by_secret_key(db, secret_key=secret_key):
        return {
            "url_key": db_url.key,
            "target_url": db_url.target_url,
            "days": days,
            "daily_clicks": crud.get_daily_clicks(db=db, url_id=db_url.id, days=days)
        }
    else:
        raise_not_found(request)


@app.get(
    "/admin/{secret_key}/analytics/devices",
)
def get_device_analytics(
        secret_key: str,
        request: Request,
        db: Session = Depends(get_db)
):
    if db_url := crud.get_db_url_by_secret_key(db, secret_key=secret_key):
        return {
            "url_key": db_url.key,
            "target_url": db_url.target_url,
            "device_stats": crud.get_device_stats(db=db, url_id=db_url.id)
        }
    else:
        raise_not_found(request)


@app.get(
    "/admin/{secret_key}/analytics/browsers",
)
def get_browser_analytics(
        secret_key: str,
        request: Request,
        db: Session = Depends(get_db)
):
    if db_url := crud.get_db_url_by_secret_key(db, secret_key=secret_key):
        return {
            "url_key": db_url.key,
            "target_url": db_url.target_url,
            "browser_stats": crud.get_browser_stats(db=db, url_id=db_url.id)
        }
    else:
        raise_not_found(request)


@app.get(
    "/admin/{secret_key}/analytics/os",
)
def get_os_analytics(
        secret_key: str,
        request: Request,
        db: Session = Depends(get_db)
):
    if db_url := crud.get_db_url_by_secret_key(db, secret_key=secret_key):
        return {
            "url_key": db_url.key,
            "target_url": db_url.target_url,
            "os_stats": crud.get_os_stats(db=db, url_id=db_url.id)
        }
    else:
        raise_not_found(request)


@app.get(
    "/admin/{secret_key}/analytics/referers",
)
def get_referer_analytics(
        secret_key: str,
        request: Request,
        db: Session = Depends(get_db)
):
    if db_url := crud.get_db_url_by_secret_key(db, secret_key=secret_key):
        return {
            "url_key": db_url.key,
            "target_url": db_url.target_url,
            "referer_stats": crud.get_referer_stats(db=db, url_id=db_url.id)
        }
    else:
        raise_not_found(request)


@app.get(
    "/admin/{secret_key}/analytics/countries",
)
def get_country_analytics(
        secret_key: str,
        request: Request,
        db: Session = Depends(get_db)
):
    if db_url := crud.get_db_url_by_secret_key(db, secret_key=secret_key):
        return {
            "url_key": db_url.key,
            "target_url": db_url.target_url,
            "country_stats": crud.get_country_stats(db=db, url_id=db_url.id)
        }
    else:
        raise_not_found(request)


@app.delete("/admin/{secret_key}")
def delete_url(
        secret_key: str, request: Request, db: Session = Depends(get_db)
):
    if db_url := crud.deactivate_db_url_by_secret_key(
            db, secret_key=secret_key
    ):
        message = (
            f"Successfully deleted shortened URL for '{db_url.target_url}'"
        )
        return {"detail": message}
    else:
        raise_not_found(request)
