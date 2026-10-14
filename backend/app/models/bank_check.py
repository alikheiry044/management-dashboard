from sqlalchemy import Column, Integer, String, Numeric, DateTime, Text
from sqlalchemy.sql import func
from app.core.database import Base


class BankCheck(Base):
    __tablename__ = "bank_checks"

    id = Column(Integer, primary_key=True, index=True)

    # receivable_check | payable_check
    check_type = Column(String(30), nullable=False, index=True)

    # open | passed | spent | returned | unknown
    status = Column(String(30), nullable=False, default="open", index=True)

    check_number = Column(String(50), nullable=True, index=True)
    bank_name = Column(String(100), nullable=True)
    account_no = Column(String(50), nullable=True)

    party_name = Column(String(255), nullable=True, index=True)
    amount = Column(Numeric(18, 2), nullable=False, default=0)

    issue_date = Column(String(20), nullable=True)
    due_date = Column(String(20), nullable=True)

    description = Column(Text, nullable=True)
    source_file = Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    