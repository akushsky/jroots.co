from sqlalchemy import (
    Column,
    Integer,
    String,
    ForeignKey,
    DateTime,
    Index,
    UniqueConstraint,
    func,
)

from app.models.base import Base


class Credit(Base):
    __tablename__ = "credits"

    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    searches_left = Column(Integer, nullable=False, default=0, server_default="0")
    scans_left = Column(Integer, nullable=False, default=0, server_default="0")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class CreditTransaction(Base):
    __tablename__ = "credit_transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    delta_searches = Column(Integer, nullable=False, default=0, server_default="0")
    delta_scans = Column(Integer, nullable=False, default=0, server_default="0")
    reason = Column(String(32), nullable=False)
    ref_id = Column(String(128), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_credit_transactions_user_created", "user_id", "created_at"),
        UniqueConstraint(
            "user_id",
            "reason",
            "ref_id",
            name="uq_credit_transactions_user_reason_ref",
        ),
    )
