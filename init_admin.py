# init_admin.py
# Initialize admin user script

from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shortener_app.config import get_settings
from shortener_app.database import Base
from shortener_app.models import User
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def init_admin():
    settings = get_settings()
    
    engine = create_engine(
        settings.db_url, connect_args={"check_same_thread": False}
    )
    
    Base.metadata.create_all(bind=engine)
    
    SessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=engine
    )
    
    db = SessionLocal()
    
    try:
        admin_username = input("请输入管理员用户名 (默认: admin): ").strip() or "admin"
        
        existing_user = db.query(User).filter(User.username == admin_username).first()
        
        if existing_user:
            print(f"用户 '{admin_username}' 已存在")
            update_existing = input("是否更新密码? (y/n, 默认: n): ").strip().lower()
            
            if update_existing == 'y':
                new_password = input("请输入新密码: ").strip()
                if len(new_password) < 6:
                    print("密码长度至少6位")
                    return
                existing_user.hashed_password = get_password_hash(new_password)
                existing_user.is_admin = True
                db.commit()
                print(f"用户 '{admin_username}' 密码已更新，并已设置为管理员")
            return
        
        password = input("请输入密码: ").strip()
        if len(password) < 6:
            print("密码长度至少6位")
            return
        
        email = input("请输入邮箱 (可选): ").strip() or None
        
        admin_user = User(
            username=admin_username,
            email=email,
            hashed_password=get_password_hash(password),
            is_active=True,
            is_admin=True,
            created_at=datetime.utcnow()
        )
        
        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)
        
        print("\n" + "="*50)
        print("管理员用户创建成功!")
        print("="*50)
        print(f"用户名: {admin_user.username}")
        print(f"邮箱: {admin_user.email or '未设置'}")
        print(f"是否管理员: 是")
        print("="*50)
        print(f"\n现在可以使用该账号登录: http://localhost:8000/login")
        
    except Exception as e:
        print(f"创建管理员失败: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    init_admin()
