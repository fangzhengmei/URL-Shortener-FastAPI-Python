# main.py
# FastAPI Implementation

from typing import List
import validators
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from starlette.datastructures import URL
from . import crud, models, schemas
from .database import SessionLocal, engine
from .config import get_settings

app = FastAPI()
models.Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_request_domain(request: Request) -> str:
    return request.url.netloc


def validate_domain(domain: str) -> bool:
    settings = get_settings()
    return domain in settings.domains


def get_admin_info(db_url: models.URL, request_domain: str = None) -> schemas.URLInfo:
    settings = get_settings()
    
    if db_url.domain and db_url.domain in settings.domains:
        use_domain = db_url.domain
    elif request_domain and request_domain in settings.domains:
        use_domain = request_domain
    else:
        base_url = URL(settings.base_url)
        use_domain = base_url.netloc
    
    base_url_str = f"http://{use_domain}" if not use_domain.startswith("http") else use_domain
    base_url = URL(base_url_str)
    
    admin_endpoint = app.url_path_for(
        "administration info", secret_key=db_url.secret_key
    )
    db_url.url = str(base_url.replace(path=f"/{db_url.key}"))
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


@app.get("/domains", response_model=List[str])
def get_available_domains():
    return get_settings().domains


@app.post("/url", response_model=schemas.URLInfo)
def create_url(
    url: schemas.URLBase, 
    request: Request,
    db: Session = Depends(get_db)
):
    if not validators.url(url.target_url):
        raise_bad_request(message="Your provided URL is not valid")
    
    request_domain = get_request_domain(request)
    
    if url.domain:
        if not validate_domain(url.domain):
            raise_bad_request(
                message=f"Domain '{url.domain}' is not configured. Available domains: {get_settings().domains}"
            )
        selected_domain = url.domain
    else:
        if validate_domain(request_domain):
            selected_domain = request_domain
        else:
            base_url = URL(get_settings().base_url)
            selected_domain = base_url.netloc

    db_url = crud.create_db_url(db=db, url=url, domain=selected_domain)
    return get_admin_info(db_url)


@app.get("/{url_key}")
def forward_to_target_url(
        url_key: str,
        request: Request,
        db: Session = Depends(get_db)
):
    request_domain = get_request_domain(request)
    settings = get_settings()
    
    domains_to_try = [request_domain] if request_domain in settings.domains else settings.domains
    
    for domain in domains_to_try:
        if db_url := crud.get_db_url_by_key(db=db, url_key=url_key, domain=domain):
            crud.update_db_clicks(db=db, db_url=db_url)
            return RedirectResponse(db_url.target_url)
    
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
        request_domain = get_request_domain(request)
        return get_admin_info(db_url, request_domain=request_domain)
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
