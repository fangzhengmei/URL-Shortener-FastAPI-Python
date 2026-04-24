# crud.py
# Implement helper functions for CRUD operations on database

from typing import List, Optional

from sqlalchemy.orm import Session

from . import keygen, models, schemas


def create_db_url(
    db: Session, 
    url: schemas.URLBase, 
    user: Optional[models.User] = None
) -> models.URL:
    key = keygen.create_unique_random_key(db)
    secret_key = f"{key}_{keygen.create_random_key(length=8)}"
    db_url = models.URL(
        target_url=url.target_url, 
        key=key, 
        secret_key=secret_key,
        user_id=user.id if user else None
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


def get_urls_by_user(db: Session, user: models.User, skip: int = 0, limit: int = 100) -> List[models.URL]:
    return (
        db.query(models.URL)
        .filter(models.URL.user_id == user.id, models.URL.is_active)
        .offset(skip)
        .limit(limit)
        .all()
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


def is_url_owner(db: Session, url: models.URL, user: models.User) -> bool:
    return url.user_id == user.id


def get_all_urls(db: Session, skip: int = 0, limit: int = 100) -> List[models.URL]:
    return (
        db.query(models.URL)
        .offset(skip)
        .limit(limit)
        .all()
    )
