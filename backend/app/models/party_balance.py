from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

# ⚠️ اگر Base در پروژه‌ی شما جای دیگری تعریف شده، همین یک import را عوض کنید
from app.core.database import Base


class PartyBalance(Base):
    """مانده‌ی یک شخص (مشتری/تأمین‌کننده) از گزارش «مرور فروش».

    balance مثبت  = بدهکار  = مطالبات ما از او
    balance منفی  = بستانکار = بدهی ما به او
    """

    __tablename__ = "party_balances"

    id: Mapped[int] = mapped_column(primary_key=True)
    detail_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(300))
    balance: Mapped[int] = mapped_column(BigInteger, default=0)

    period_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_file: Mapped[str | None] = mapped_column(String(300), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    