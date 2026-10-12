from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

# ⚠️ اگر Base در پروژه‌ی شما جای دیگری تعریف شده، همین یک import را عوض کنید
# (همان جایی که در models/user.py از آن import می‌کنید).
from app.core.database import Base


class BankBalance(Base):
    """یک ردیف از گزارش «مرور بانک‌ها (دریافت و پرداخت)»."""

    __tablename__ = "bank_balances"

    id: Mapped[int] = mapped_column(primary_key=True)
    detail_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(300))
    account_number: Mapped[str | None] = mapped_column(String(64), nullable=True)

    opening_balance: Mapped[int] = mapped_column(BigInteger, default=0)
    receipts: Mapped[int] = mapped_column(BigInteger, default=0)
    payments: Mapped[int] = mapped_column(BigInteger, default=0)
    balance: Mapped[int] = mapped_column(BigInteger, default=0)

    source_file: Mapped[str | None] = mapped_column(String(300), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )