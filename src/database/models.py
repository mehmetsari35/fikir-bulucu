from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, date, timezone
from typing import Generator, Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.config import settings


engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class RawSignal(Base):
    __tablename__ = "raw_signals"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(100), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    url = Column(String(1000), nullable=True)
    content = Column(Text, nullable=True)
    _metadata = Column("metadata", Text, nullable=True)
    scraped_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    processed = Column(Boolean, default=False, nullable=False)

    @property
    def metadata_dict(self) -> dict:
        if self._metadata:
            try:
                return json.loads(self._metadata)
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}

    @metadata_dict.setter
    def metadata_dict(self, value: dict) -> None:
        self._metadata = json.dumps(value) if value else None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "title": self.title,
            "url": self.url,
            "content": self.content,
            "metadata": self.metadata_dict,
            "scraped_at": self.scraped_at.isoformat() if self.scraped_at else None,
            "processed": self.processed,
        }


class Opportunity(Base):
    __tablename__ = "opportunities"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    explanation = Column(Text, nullable=True)
    why_it_works = Column(Text, nullable=True)
    market_opportunity = Column(Text, nullable=True)
    monetization = Column(Text, nullable=True)
    difficulty = Column(Integer, nullable=True)
    success_factors = Column(Text, nullable=True)
    category = Column(String(50), nullable=False, index=True)
    score = Column(Float, default=0.0, nullable=False)
    _source_signals = Column("source_signals", Text, nullable=True)
    created_date = Column(Date, default=lambda: datetime.now(timezone.utc).date(), nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    @property
    def source_signals(self) -> list:
        if self._source_signals:
            try:
                return json.loads(self._source_signals)
            except (json.JSONDecodeError, TypeError):
                return []
        return []

    @source_signals.setter
    def source_signals(self, value: list) -> None:
        self._source_signals = json.dumps(value) if value else "[]"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "explanation": self.explanation,
            "why_it_works": self.why_it_works,
            "market_opportunity": self.market_opportunity,
            "monetization": self.monetization,
            "difficulty": self.difficulty,
            "success_factors": self.success_factors,
            "category": self.category,
            "score": self.score,
            "source_signals": self.source_signals,
            "created_date": self.created_date.isoformat() if self.created_date else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ScanLog(Base):
    __tablename__ = "scan_logs"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(100), nullable=False, index=True)
    status = Column(String(50), nullable=False)
    signals_found = Column(Integer, default=0, nullable=False)
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "status": self.status,
            "signals_found": self.signals_found,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
        }


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
