# models.py
# Declare schema for data stored in database

from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from .database import Base


class URL(Base):
    __tablename__ = "urls"

    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True, index=True)
    secret_key = Column(String, unique=True, index=True)
    target_url = Column(String, index=True)
    is_active = Column(Boolean, default=True)
    clicks = Column(Integer, default=0)
    click_logs = relationship("ClickLog", back_populates="url")


class ClickLog(Base):
    __tablename__ = "click_logs"

    id = Column(Integer, primary_key=True)
    url_id = Column(Integer, ForeignKey("urls.id"), nullable=False)
    clicked_at = Column(DateTime, default=datetime.utcnow, index=True)
    ip_address = Column(String(45), index=True)
    user_agent = Column(String(500))
    referer = Column(String(500))
    country = Column(String(100))
    region = Column(String(100))
    city = Column(String(100))
    device_type = Column(String(50))
    browser = Column(String(100))
    browser_version = Column(String(100))
    os = Column(String(100))
    os_version = Column(String(100))

    url = relationship("URL", back_populates="click_logs")
