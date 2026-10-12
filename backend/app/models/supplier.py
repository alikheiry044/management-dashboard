from sqlalchemy import Column, Integer, String, Numeric, DateTime, Text
from sqlalchemy.sql import func
from app.core.database import Base


class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), nullable=True, index=True)
    name = Column(String(255), nullable=False, index=True)

    debit_turnover = Column(Numeric(18, 2), default=0)
    debit_balance = Column(Numeric(18, 2), default=0)
    credit_balance = Column(Numeric(18, 2), default=0)

    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

