# crud.py
# Implement helper functions for CRUD operations on database

from sqlalchemy.orm import Session
from . import keygen, models, schemas


def create_db_url(db: Session, url: schemas.URLBase, domain: str) -> models.URL:
    key = keygen.create_unique_random_key(db, domain)
    secret_key = f"{key}_{keygen.create_random_key(length=8)}"
    db_url = models.URL(
        target_url=url.target_url,
        domain=domain,
        key=key,
        secret_key=secret_key
    )
    db.add(db_url)
    db.commit()
    db.refresh(db_url)
    return db_url


def get_db_url_by_key(db: Session, url_key: str, domain: str) -> models.URL:
    return (
        db.query(models.URL)
        .filter(
            models.URL.key == url_key,
            models.URL.domain == domain,
            models.URL.is_active
        )
        .first()
    )


def get_db_url_by_secret_key(db: Session, secret_key: str) -> models.URL:
    return (
        db.query(models.URL)
        .filter(models.URL.secret_key == secret_key, models.URL.is_active)
        .first()
    )


def update_db_clicks(db: Session, db_url: schemas.URL) -> models.URL:
    db_url.clicks += 1
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


def get_all_urls_by_domain(db: Session, domain: str, include_inactive: bool = False):
    query = db.query(models.URL).filter(models.URL.domain == domain)
    if not include_inactive:
        query = query.filter(models.URL.is_active)
    return query.order_by(models.URL.id.desc()).all()


def get_url_count_by_domain(db: Session, domain: str, include_inactive: bool = False):
    query = db.query(models.URL).filter(models.URL.domain == domain)
    if not include_inactive:
        query = query.filter(models.URL.is_active)
    return query.count()
