# models.py
# Declare schema for data stored in database

from sqlalchemy import Boolean, Column, Integer, String, UniqueConstraint

from .database import Base


class URL(Base):
    __tablename__ = "urls"

    id = Column(Integer, primary_key=True)
    domain = Column(String, index=True, nullable=False)
    key = Column(String, index=True)
    secret_key = Column(String, unique=True, index=True)
    target_url = Column(String, index=True)
    is_active = Column(Boolean, default=True)
    clicks = Column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint('domain', 'key', name='uq_domain_key'),
    )
