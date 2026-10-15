from sqlalchemy import Column, Integer, String, Numeric, DateTime, Text
from sqlalchemy.sql import func
from app.core.database import Base


class BankCheck(Base):
    __tablename__ = "bank_checks"

    id = Column(Integer, primary_key=True, index=True)
    check_type = Column(String(30), nullable=False, index=True)  # receivable_check | payable_check
    status = Column(String(30), nullable=False, default="unknown", index=True)

    detail_code = Column(String(50), nullable=True)
    party_name = Column(String(255), nullable=True, index=True)
    movement_type = Column(String(100), nullable=True)
    check_number = Column(String(50), nullable=True, index=True)
    amount = Column(Numeric(18, 2), nullable=False, default=0)

    due_date = Column(String(20), nullable=True)
    receive_date = Column(String(20), nullable=True)
    bank_name = Column(String(100), nullable=True)
    owner_name = Column(String(255), nullable=True)
    settle_date = Column(String(50), nullable=True)

    description = Column(Text, nullable=True)
    source_file = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    