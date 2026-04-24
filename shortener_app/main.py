# main.py
# FastAPI Implementation

from datetime import datetime
from pathlib import Path
from typing import List, Optional

import validators
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError
from sqlalchemy.orm import Session
from starlette.datastructures import URL

from . import auth, crud, models, schemas
from .database import SessionLocal, engine
from .config import get_settings

app = FastAPI(title="URL Shortener API with Auth", description="A URL shortener service with user authentication")
models.Base.metadata.create_all(bind=engine)

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_admin_info(db_url: models.URL) -> schemas.URLInfo:
    base_url = URL(get_settings().base_url)
    admin_endpoint = app.url_path_for(
        "administration info", secret_key=db_url.secret_key
    )
    db_url.url = str(base_url.replace(path=db_url.key))
    db_url.admin_url = str(base_url.replace(path=admin_endpoint))
    return db_url


def get_url_list_item(db_url: models.URL) -> schemas.URLList:
    base_url = URL(get_settings().base_url)
    admin_endpoint = app.url_path_for(
        "administration info", secret_key=db_url.secret_key
    )
    return schemas.URLList(
        target_url=db_url.target_url,
        is_active=db_url.is_active,
        clicks=db_url.clicks,
        created_at=db_url.created_at,
        key=db_url.key,
        secret_key=db_url.secret_key,
        url=str(base_url.replace(path=db_url.key)),
        admin_url=str(base_url.replace(path=admin_endpoint)),
    )


def raise_bad_request(message):
    raise HTTPException(status_code=400, detail=message)


def raise_not_found(request):
    message = f"URL '{request.url}' doesn't exist"
    raise HTTPException(status_code=404, detail=message)


def raise_forbidden(message="Not authorized to access this resource"):
    raise HTTPException(status_code=403, detail=message)


def check_url_ownership(db_url: models.URL, user: models.User):
    if not crud.is_url_owner(None, db_url, user) and not user.is_admin:
        raise_forbidden()


def check_registration_allowed(user: schemas.UserCreate, settings):
    if settings.invite_code:
        if not user.invite_code or user.invite_code.strip() != settings.invite_code:
            raise_forbidden("Invalid or missing invite code.")
    else:
        if not settings.allow_public_registration:
            raise_forbidden("Registration is disabled. Please contact the administrator.")


def get_token_from_request(request: Request) -> str:
    authorization = request.headers.get("Authorization")
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication scheme",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token.strip()


@app.get("/")
def read_root():
    return RedirectResponse(url="/login")


@app.get("/login")
async def login_page():
    login_html = TEMPLATES_DIR / "login.html"
    if login_html.exists():
        return FileResponse(str(login_html))
    return RedirectResponse(url="/docs")


@app.get("/dashboard")
async def dashboard_page():
    dashboard_html = TEMPLATES_DIR / "dashboard.html"
    if dashboard_html.exists():
        return FileResponse(str(dashboard_html))
    return RedirectResponse(url="/docs")


@app.get("/auth/settings", response_model=schemas.AuthSettings)
def get_auth_settings():
    settings = get_settings()
    return schemas.AuthSettings(
        allow_public_registration=settings.allow_public_registration,
        invite_code_required=settings.invite_code is not None,
        min_password_length=settings.min_password_length,
    )


@app.post("/auth/register", response_model=schemas.User, status_code=status.HTTP_201_CREATED)
def register_user(
    user: schemas.UserCreate, 
    request: Request,
    db: Session = Depends(get_db)
):
    settings = get_settings()
    
    check_registration_allowed(user, settings)
    
    existing_user = auth.get_user(db, username=user.username)
    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Username already registered"
        )
    
    if user.email:
        existing_email = auth.get_user_by_email(db, email=user.email)
        if existing_email:
            raise HTTPException(
                status_code=400,
                detail="Email already registered"
            )
    
    new_user = auth.create_user(db=db, user=user)
    
    auth.log_audit_event(
        db=db,
        event_type=models.AuditEventType.USER_CREATED,
        user=new_user,
        request=request,
        success=True,
        description="User registered via public registration"
    )
    
    return new_user


@app.post("/auth/login", response_model=schemas.Token)
def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    settings = get_settings()
    username = form_data.username
    
    user = auth.get_user(db, username=username)
    
    if not user:
        auth.log_audit_event(
            db=db,
            event_type=models.AuditEventType.LOGIN_FAILED,
            request=request,
            success=False,
            description=f"Login attempt for non-existent user: {username}",
            username=username
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if user.is_active and auth.is_account_locked(user):
        remaining = auth.get_lockout_remaining_minutes(user)
        auth.log_audit_event(
            db=db,
            event_type=models.AuditEventType.LOGIN_FAILED,
            user=user,
            request=request,
            success=False,
            description=f"Login attempt on locked account. {remaining} minutes remaining."
        )
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Account is locked. Try again in {remaining} minutes.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not auth.authenticate_user(db, username=username, password=form_data.password):
        if user.is_active:
            user = auth.record_failed_login(db, user)
            
            if auth.is_account_locked(user):
                auth.log_audit_event(
                    db=db,
                    event_type=models.AuditEventType.ACCOUNT_LOCKED,
                    user=user,
                    request=request,
                    success=True,
                    description=f"Account locked after {settings.max_login_attempts} failed login attempts"
                )
                raise HTTPException(
                    status_code=status.HTTP_423_LOCKED,
                    detail=f"Too many failed attempts. Account is locked for {settings.account_lockout_minutes} minutes.",
                    headers={"WWW-Authenticate": "Bearer"},
                )
        
        remaining_attempts = settings.max_login_attempts - user.failed_login_attempts
        auth.log_audit_event(
            db=db,
            event_type=models.AuditEventType.LOGIN_FAILED,
            user=user,
            request=request,
            success=False,
            description=f"Failed login attempt. Remaining attempts: {remaining_attempts}"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Incorrect username or password. {remaining_attempts} attempts remaining.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        auth.log_audit_event(
            db=db,
            event_type=models.AuditEventType.LOGIN_FAILED,
            user=user,
            request=request,
            success=False,
            description="Login attempt on disabled account"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account has been disabled",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = auth.reset_failed_login_attempts(db, user)
    user.last_login = datetime.utcnow()
    db.commit()
    db.refresh(user)
    
    auth.log_audit_event(
        db=db,
        event_type=models.AuditEventType.LOGIN_SUCCESS,
        user=user,
        request=request,
        success=True,
        description="Successful login"
    )
    
    access_token, jti, expires_at = auth.create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/auth/logout", response_model=schemas.LogoutResponse)
def logout(
    request: Request,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db)
):
    try:
        token = get_token_from_request(request)
        payload = auth.decode_token(token)
        jti = payload.get("jti")
        exp_timestamp = payload.get("exp")
        
        expires_at = None
        if exp_timestamp:
            expires_at = datetime.utcfromtimestamp(exp_timestamp)
        
        if jti:
            auth.revoke_token(
                db=db,
                jti=jti,
                token=token,
                expires_at=expires_at,
                user_id=current_user.id
            )
    except (JWTError, HTTPException):
        pass
    
    auth.log_audit_event(
        db=db,
        event_type=models.AuditEventType.LOGOUT,
        user=current_user,
        request=request,
        success=True,
        description="User logged out"
    )
    
    return schemas.LogoutResponse()


@app.get("/auth/me", response_model=schemas.User)
def read_users_me(
    current_user: models.User = Depends(auth.get_current_active_user)
):
    return current_user


@app.put("/auth/me", response_model=schemas.User)
def update_user_me(
    user_update: schemas.UserUpdate,
    request: Request,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db)
):
    if user_update.email:
        existing_email = auth.get_user_by_email(db, email=user_update.email)
        if existing_email and existing_email.id != current_user.id:
            raise HTTPException(
                status_code=400,
                detail="Email already registered"
            )
        current_user.email = user_update.email
    
    if user_update.password:
        current_user = auth.update_user_password(db, current_user, user_update.password)
        auth.log_audit_event(
            db=db,
            event_type=models.AuditEventType.PASSWORD_CHANGED,
            user=current_user,
            request=request,
            success=True,
            description="User changed their own password"
        )
    else:
        db.commit()
        db.refresh(current_user)
    
    return current_user


@app.post("/url", response_model=schemas.URLInfo)
def create_url(
    url: schemas.URLBase,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    if not validators.url(url.target_url):
        raise_bad_request(message="Your provided URL is not valid")

    db_url = crud.create_db_url(db=db, url=url, user=current_user)
    return get_admin_info(db_url)


@app.get("/{url_key}")
def forward_to_target_url(
        url_key: str,
        request: Request,
        db: Session = Depends(get_db)
):
    if db_url := crud.get_db_url_by_key(db=db, url_key=url_key):
        crud.update_db_clicks(db=db, db_url=db_url)
        return RedirectResponse(db_url.target_url)
    else:
        raise_not_found(request)


@app.get(
    "/admin/{secret_key}",
    name="administration info",
    response_model=schemas.URLInfo,
)
def get_url_info(
        secret_key: str,
        request: Request,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(auth.get_current_active_user)
):
    if db_url := crud.get_db_url_by_secret_key(db, secret_key=secret_key):
        check_url_ownership(db_url, current_user)
        db_url.url = db_url.key
        db_url.admin_url = db_url.secret_key
        return get_admin_info(db_url)
    else:
        raise_not_found(request)


@app.delete("/admin/{secret_key}")
def delete_url(
        secret_key: str,
        request: Request,
        db: Session = Depends(get_db),
        current_user: models.User = Depends(auth.get_current_active_user)
):
    if db_url := crud.get_db_url_by_secret_key(db, secret_key=secret_key):
        check_url_ownership(db_url, current_user)
        db_url = crud.deactivate_db_url_by_secret_key(db, secret_key=secret_key)
        message = (
            f"Successfully deleted shortened URL for '{db_url.target_url}'"
        )
        return {"detail": message}
    else:
        raise_not_found(request)


@app.get("/user/urls", response_model=List[schemas.URLList])
def get_user_urls(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    urls = crud.get_urls_by_user(db, user=current_user, skip=skip, limit=limit)
    return [get_url_list_item(url) for url in urls]


@app.post("/admin/users", response_model=schemas.User, status_code=status.HTTP_201_CREATED)
def admin_create_user(
    user_data: schemas.AdminUserCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    if not current_user.is_admin:
        raise_forbidden("Admin access required")
    
    existing_user = auth.get_user(db, username=user_data.username)
    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Username already registered"
        )
    
    if user_data.email:
        existing_email = auth.get_user_by_email(db, email=user_data.email)
        if existing_email:
            raise HTTPException(
                status_code=400,
                detail="Email already registered"
            )
    
    hashed_password = auth.get_password_hash(user_data.password)
    db_user = models.User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hashed_password,
        is_active=True,
        is_admin=user_data.is_admin,
        created_at=datetime.utcnow(),
        failed_login_attempts=0,
        last_password_change=datetime.utcnow()
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    auth.log_audit_event(
        db=db,
        event_type=models.AuditEventType.USER_CREATED,
        user=db_user,
        request=request,
        success=True,
        description=f"User created by admin {current_user.username}"
    )
    
    return db_user


@app.get("/admin/users", response_model=List[schemas.User])
def get_all_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    if not current_user.is_admin:
        raise_forbidden("Admin access required")
    users = db.query(models.User).offset(skip).limit(limit).all()
    return users


@app.put("/admin/users/{user_id}/toggle-active", response_model=schemas.User)
def toggle_user_active(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    if not current_user.is_admin:
        raise_forbidden("Admin access required")
    
    user = auth.get_user_by_id(db, user_id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    was_active = user.is_active
    
    if user.is_admin and user.id != current_user.id:
        user.is_active = not user.is_active
    elif user.is_admin and user.id == current_user.id:
        raise_forbidden("Cannot deactivate yourself")
    else:
        user.is_active = not user.is_active
    
    db.commit()
    db.refresh(user)
    
    event_type = models.AuditEventType.ACCOUNT_ENABLED if user.is_active else models.AuditEventType.ACCOUNT_DISABLED
    action = "enabled" if user.is_active else "disabled"
    
    auth.log_audit_event(
        db=db,
        event_type=event_type,
        user=user,
        request=request,
        success=True,
        description=f"Account {action} by admin {current_user.username}"
    )
    
    return user


@app.put("/admin/users/{user_id}/unlock", response_model=schemas.User)
def admin_unlock_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    if not current_user.is_admin:
        raise_forbidden("Admin access required")
    
    user = auth.get_user_by_id(db, user_id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    was_locked = auth.is_account_locked(user)
    user = auth.reset_failed_login_attempts(db, user)
    
    if was_locked:
        auth.log_audit_event(
            db=db,
            event_type=models.AuditEventType.ACCOUNT_UNLOCKED,
            user=user,
            request=request,
            success=True,
            description=f"Account unlocked by admin {current_user.username}"
        )
    
    return user


@app.put("/admin/users/{user_id}/reset-password", response_model=schemas.User)
def admin_reset_password(
    user_id: int,
    new_password: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    if not current_user.is_admin:
        raise_forbidden("Admin access required")
    
    user = auth.get_user_by_id(db, user_id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    settings = get_settings()
    if len(new_password) < settings.min_password_length:
        raise HTTPException(
            status_code=400,
            detail=f"Password must be at least {settings.min_password_length} characters"
        )
    
    user = auth.update_user_password(db, user, new_password)
    
    auth.log_audit_event(
        db=db,
        event_type=models.AuditEventType.PASSWORD_RESET,
        user=user,
        request=request,
        success=True,
        description=f"Password reset by admin {current_user.username}"
    )
    
    return user


@app.get("/admin/logs", response_model=schemas.AuditLogList)
def get_audit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    user_id: Optional[int] = Query(None, description="Filter by user ID"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    success: Optional[bool] = Query(None, description="Filter by success status"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    if not current_user.is_admin:
        raise_forbidden("Admin access required")
    
    query = db.query(models.AuditLog)
    
    if user_id is not None:
        query = query.filter(models.AuditLog.user_id == user_id)
    if event_type is not None:
        query = query.filter(models.AuditLog.event_type == event_type)
    if success is not None:
        query = query.filter(models.AuditLog.success == success)
    
    total = query.count()
    
    logs = query.order_by(models.AuditLog.timestamp.desc()).offset(skip).limit(limit).all()
    
    return schemas.AuditLogList(total=total, logs=logs)
