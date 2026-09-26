"""Modelos SQLAlchemy — leads, mensagens, agendamentos, imóveis sugeridos."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
    perfil: Mapped[dict] = mapped_column(JSONB, default=dict)
    score: Mapped[int] = mapped_column(Integer, default=0)
    prioridade: Mapped[str] = mapped_column(String(16), default="frio", index=True)

    mensagens: Mapped[list[Mensagem]] = relationship(
        back_populates="lead", cascade="all, delete-orphan", order_by="Mensagem.em"
    )
    agendamentos: Mapped[list[Agendamento]] = relationship(
        back_populates="lead", cascade="all, delete-orphan"
    )
    imoveis_sugeridos: Mapped[list[ImovelSugerido]] = relationship(
        back_populates="lead", cascade="all, delete-orphan"
    )


class Mensagem(Base):
    __tablename__ = "mensagens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    papel: Mapped[str] = mapped_column(String(16))
    texto: Mapped[str] = mapped_column(Text)
    em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    lead: Mapped[Lead] = relationship(back_populates="mensagens")


class Agendamento(Base):
    __tablename__ = "agendamentos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    horario: Mapped[str] = mapped_column(String(64))
    tipo: Mapped[str] = mapped_column(String(32), default="reuniao")
    status: Mapped[str] = mapped_column(String(32), default="agendado")
    imovel_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    lead: Mapped[Lead] = relationship(back_populates="agendamentos")


class ImovelSugerido(Base):
    __tablename__ = "imoveis_sugeridos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    imovel_id: Mapped[str] = mapped_column(String(64))
    snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    lead: Mapped[Lead] = relationship(back_populates="imoveis_sugeridos")
