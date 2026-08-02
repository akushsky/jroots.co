from sqlalchemy import (
    JSON,
    Column,
    Integer,
    String,
    ForeignKey,
    DateTime,
    Date,
    Numeric,
    func,
)

from app.models.base import Base


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String(32), nullable=False)
    provider_payment_id = Column(String(128), nullable=False, unique=True)
    order_id = Column(String(128), nullable=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    tariff = Column(String(32), nullable=True)
    amount = Column(Numeric(10, 2), nullable=True)
    currency = Column(String(8), nullable=True)
    status = Column(String(32), nullable=True)
    raw_payload_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider = Column(String(32), nullable=True)
    provider_sub_id = Column(String(128), nullable=True)
    status = Column(String(32), nullable=True)
    current_period_end = Column(DateTime, nullable=True)


class DailyBudget(Base):
    __tablename__ = "daily_budget"

    day = Column(Date, primary_key=True)
    free_spend_usd = Column(
        Numeric(10, 4), nullable=False, default=0, server_default="0"
    )
