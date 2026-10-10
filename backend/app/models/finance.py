from sqlalchemy import Column, Integer, String, Numeric, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.sql import func
from app.core.database import Base


class FinanceTransaction(Base):
    __tablename__ = "finance_transactions"

    id = Column(Integer, primary_key=True, index=True)

    # نوع تراکنش: expense / receivable / payable
    type = Column(String(50), nullable=False)

    # مبلغ تراکنش
    amount = Column(Numeric(18, 2), nullable=False, default=0)

    # تاریخ تراکنش (شمسی - به صورت متن)
    transaction_date = Column(String(20), nullable=True)

    # نام طرف حساب (تأمین‌کننده / مشتری)
    party_name = Column(String(255), nullable=True)

    # توضیحات تراکنش
    description = Column(Text, nullable=True)

    # شماره مرجع (شماره فاکتور / سند)
    reference_number = Column(String(100), nullable=True)

    # روش پرداخت: cash / check / transfer
    payment_method = Column(String(50), nullable=True)

    # ===== وضعیت و پیگیری =====
    # normal | needs_review | approved | stopped | settled
    status = Column(String(50), nullable=False, default="normal")

    # نیاز به پیگیری دارد؟
    needs_followup = Column(Boolean, default=False)

    # یادداشت / توضیحات بررسی
    note = Column(Text, nullable=True)

    # ===== ارزیابی ریسک =====
    # low | medium | high
    risk_level = Column(String(20), nullable=False, default="low")

    # امتیاز ریسک عددی (0 تا 100)
    risk_score = Column(Integer, default=0)

    # ===== تشخیص‌های هوشمند =====
    # آیا فاکتور تکراری است؟
    is_duplicate = Column(Boolean, default=False)

    # آیا حساب بانکی تغییر کرده است؟
    has_bank_change = Column(Boolean, default=False)

    # آیا مبلغ غیرعادی است؟
    amount_anomaly = Column(Boolean, default=False)

    # ===== گردش کار تأیید =====
    # چه کسی باید تأیید کند؟ (finance_manager / ceo / ceo_and_owner)
    requires_approval_from = Column(String(100), nullable=True)

    # وضعیت تأیید: not_required / pending / approved / rejected
    approval_status = Column(String(50), default="not_required")

    # شناسه کاربر تأییدکننده
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # زمان تأیید
    approved_at = Column(DateTime(timezone=True), nullable=True)

    # ===== بررسی‌کننده =====
    # شناسه کاربر بررسی‌کننده
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # زمان بررسی
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    # ===== زمان‌های سیستمی =====
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<FinanceTransaction(id={self.id}, type={self.type}, amount={self.amount}, status={self.status})>"
    