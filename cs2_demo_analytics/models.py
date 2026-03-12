from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    steam_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    name: Mapped[str] = mapped_column(String, index=True)

    events_as_attacker = relationship("Event", back_populates="attacker", foreign_keys="Event.attacker_id")
    events_as_victim = relationship("Event", back_populates="victim", foreign_keys="Event.victim_id")
    metrics = relationship("Metric", back_populates="player")


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    demo_filename: Mapped[str] = mapped_column(String, index=True)
    map_name: Mapped[str] = mapped_column(String, default="unknown")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    total_rounds: Mapped[int] = mapped_column(Integer, default=0)
    parse_source: Mapped[str] = mapped_column(String, default="demoparser2")
    tick_rate: Mapped[int] = mapped_column(Integer, default=64)
    total_ticks: Mapped[int] = mapped_column(Integer, default=0)

    rounds = relationship("Round", back_populates="match", cascade="all, delete-orphan")
    events = relationship("Event", back_populates="match", cascade="all, delete-orphan")
    metrics = relationship("Metric", back_populates="match", cascade="all, delete-orphan")


class Round(Base):
    __tablename__ = "rounds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    round_number: Mapped[int] = mapped_column(Integer)
    start_tick: Mapped[int] = mapped_column(Integer, default=0)
    end_tick: Mapped[int] = mapped_column(Integer, default=0)

    match = relationship("Match", back_populates="rounds")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    event_type: Mapped[str] = mapped_column(String, index=True)
    tick: Mapped[int] = mapped_column(Integer, index=True)
    round_number: Mapped[int] = mapped_column(Integer, default=0)
    attacker_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"), nullable=True)
    victim_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"), nullable=True)
    value: Mapped[float] = mapped_column(Float, default=0.0)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)

    match = relationship("Match", back_populates="events")
    attacker = relationship("Player", back_populates="events_as_attacker", foreign_keys=[attacker_id])
    victim = relationship("Player", back_populates="events_as_victim", foreign_keys=[victim_id])


class Metric(Base):
    __tablename__ = "metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    key: Mapped[str] = mapped_column(String, index=True)
    value: Mapped[float] = mapped_column(Float)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False)

    match = relationship("Match", back_populates="metrics")
    player = relationship("Player", back_populates="metrics")
