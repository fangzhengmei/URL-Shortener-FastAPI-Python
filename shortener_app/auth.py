# auth.py
# User authentication and JWT utilities

from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import models, schemas
from .config import get_settings
from .database import SessionLocal

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None
    jti: Optional[str] = None
    iat: Optional[datetime] = None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> tuple:
    settings = get_settings()
    to_encode = data.copy()
    
    jti = str(uuid4())
    iat = datetime.utcnow()
    to_encode.update({"jti": jti, "iat": iat})
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(
        to_encode, 
        settings.jwt_secret_key, 
        algorithm=settings.jwt_algorithm
    )
    return encoded_jwt, jti, expire


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_user(db: Session, username: str) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.username == username).first()


def get_user_by_email(db: Session, email: str) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.email == email).first()


def is_account_locked(user: models.User) -> bool:
    if user.locked_until and user.locked_until > datetime.utcnow():
        return True
    return False


def get_lockout_remaining_minutes(user: models.User) -> int:
    if not user.locked_until:
        return 0
    remaining = user.locked_until - datetime.utcnow()
    return max(0, int(remaining.total_seconds() / 60))


def record_failed_login(db: Session, user: models.User) -> models.User:
    settings = get_settings()
    
    user.failed_login_attempts += 1
    
    if user.failed_login_attempts >= settings.max_login_attempts:
        user.locked_until = datetime.utcnow() + timedelta(minutes=settings.account_lockout_minutes)
    
    db.commit()
    db.refresh(user)
    return user


def reset_failed_login_attempts(db: Session, user: models.User) -> models.User:
    user.failed_login_attempts = 0
    user.locked_until = None
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, username: str, password: str) -> Optional[models.User]:
    user = get_user(db, username)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def is_token_revoked(db: Session, jti: str) -> bool:
    revoked = db.query(models.RevokedToken).filter(
        models.RevokedToken.jti == jti
    ).first()
    return revoked is not None


def is_token_outdated(user: models.User, token_iat: Optional[datetime]) -> bool:
    if token_iat is None:
        return False
    if user.last_password_change is None:
        return False
    return token_iat < user.last_password_change


def revoke_token(
    db: Session, 
    jti: str, 
    token: str, 
    expires_at: Optional[datetime],
    user_id: Optional[int]
) -> models.RevokedToken:
    revoked_token = models.RevokedToken(
        jti=jti,
        token=token,
        revoked_at=datetime.utcnow(),
        expires_at=expires_at,
        user_id=user_id
    )
    db.add(revoked_token)
    db.commit()
    db.refresh(revoked_token)
    return revoked_token


def decode_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(
        token, 
        settings.jwt_secret_key, 
        algorithms=[settings.jwt_algorithm]
    )


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    client_host = request.client.host if request.client else "unknown"
    return client_host


def get_user_agent(request: Request) -> str:
    return request.headers.get("User-Agent", "unknown")


def log_audit_event(
    db: Session,
    event_type: str,
    user: Optional[models.User] = None,
    request: Optional[Request] = None,
    success: bool = True,
    description: Optional[str] = None,
    error_message: Optional[str] = None,
    username: Optional[str] = None
) -> models.AuditLog:
    ip_address = None
    user_agent = None
    
    if request:
        ip_address = get_client_ip(request)
        user_agent = get_user_agent(request)
    
    audit_log = models.AuditLog(
        user_id=user.id if user else None,
        username=username or (user.username if user else None),
        event_type=event_type,
        event_description=description,
        ip_address=ip_address,
        user_agent=user_agent,
        success=success,
        error_message=error_message
    )
    
    db.add(audit_log)
    db.commit()
    db.refresh(audit_log)
    
    return audit_log


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        settings = get_settings()
        payload = jwt.decode(
            token, 
            settings.jwt_secret_key, 
            algorithms=[settings.jwt_algorithm]
        )
        username: str = payload.get("sub")
        jti: str = payload.get("jti")
        iat_timestamp: int = payload.get("iat")
        
        token_iat = None
        if iat_timestamp:
            token_iat = datetime.utcfromtimestamp(iat_timestamp)
        
        if username is None:
            raise credentials_exception
        
        if jti and is_token_revoked(db, jti):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        token_data = TokenData(username=username, jti=jti, iat=token_iat)
    except JWTError:
        raise credentials_exception
    
    user = get_user(db, username=token_data.username)
    if user is None:
        raise credentials_exception
    
    if is_token_outdated(user, token_data.iat):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been invalidated due to password change",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account has been disabled",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user


async def get_current_active_user(
    current_user: models.User = Depends(get_current_user)
) -> models.User:
    return current_user


def create_user(db: Session, user: schemas.UserCreate) -> models.User:
    hashed_password = get_password_hash(user.password)
    db_user = models.User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password,
        is_active=True,
        is_admin=False,
        failed_login_attempts=0,
        last_password_change=datetime.utcnow()
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def get_user_by_id(db: Session, user_id: int) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.id == user_id).first()


def update_user_password(db: Session, user: models.User, new_password: str) -> models.User:
    user.hashed_password = get_password_hash(new_password)
    user.last_password_change = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user


def deactivate_user(db: Session, user: models.User) -> models.User:
    user.is_active = False
    db.commit()
    db.refresh(user)
    return user
