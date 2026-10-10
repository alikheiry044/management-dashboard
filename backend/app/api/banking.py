from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, desc
from typing import List, Optional
from datetime import date

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.finance import FinanceTransaction

router = APIRouter(prefix="/banking", tags=["Banking"])


@router.get("/stats")
async def get_banking_stats(
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """آمار عملیات بانکی"""

    # مجموع موجودی (از تراکنش‌های receivable منهای payable)
    receivable_result = await db.execute(
        select(func.sum(FinanceTransaction.amount)).where(
            FinanceTransaction.type == "receivable"
        )
    )
    receivable_total = receivable_result.scalar() or 0

    payable_result = await db.execute(
        select(func.sum(FinanceTransaction.amount)).where(
            FinanceTransaction.type == "payable"
        )
    )
    payable_total = payable_result.scalar() or 0

    total_balance = float(receivable_total - payable_total)

    # تعداد حساب‌ها (فعلاً ثابت - بعداً از مدل BankAccount خوانده می‌شود)
    total_accounts = 4

    # تراکنش‌های امروز
    today = date.today()
    today_result = await db.execute(
        select(func.count(FinanceTransaction.id)).where(
            func.date(FinanceTransaction.created_at) == today
        )
    )
    today_transactions = today_result.scalar() or 0

    # مغایرت‌ها (تراکنش‌های نیازمند بررسی)
    pending_result = await db.execute(
        select(func.count(FinanceTransaction.id)).where(
            FinanceTransaction.status == "needs_review"
        )
    )
    pending_reconciliations = pending_result.scalar() or 0

    # حساب‌های بدون مغایرت
    clean_accounts = max(0, total_accounts - (1 if pending_reconciliations > 0 else 0))

    return {
        "total_balance": total_balance,
        "total_accounts": total_accounts,
        "today_transactions": today_transactions,
        "pending_reconciliations": pending_reconciliations,
        "clean_accounts": clean_accounts
    }


@router.get("/transactions")
async def get_banking_transactions(
        limit: int = Query(10, ge=1, le=50),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """آخرین تراکنش‌های بانکی"""
    result = await db.execute(
        select(FinanceTransaction)
        .order_by(desc(FinanceTransaction.created_at))
        .limit(limit)
    )
    transactions = result.scalars().all()

    return [
        {
            "id": t.id,
            "type": t.type,
            "amount": float(t.amount),
            "party_name": t.party_name,
            "description": t.description,
            "transaction_date": t.transaction_date,
            "status": t.status,
            "risk_level": t.risk_level,
            "created_at": t.created_at.isoformat() if t.created_at else None
        }
        for t in transactions
    ]


@router.get("/accounts")
async def get_bank_accounts(
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """لیست حساب‌های بانکی (نمونه - بعداً از دیتابیس خوانده می‌شود)"""

    # داده‌های نمونه (بعداً از مدل BankAccount خوانده می‌شود)
    accounts = [
        {
            "id": 1,
            "name": "بانک ملت - حساب جاری",
            "bank": "ملت",
            "number": "0123456789",
            "balance": 2850000000,
            "status": "clean"
        },
        {
            "id": 2,
            "name": "بانک صادرات - حساب سپرده",
            "bank": "صادرات",
            "number": "9876543210",
            "balance": 1420000000,
            "status": "clean"
        },
        {
            "id": 3,
            "name": "بانک پارسیان - حساب ارزی",
            "bank": "پارسیان",
            "number": "5551234567",
            "balance": 680000000,
            "status": "unmatched"
        },
        {
            "id": 4,
            "name": "بانک تجارت - حساب حقوق",
            "bank": "تجارت",
            "number": "7778889990",
            "balance": 340000000,
            "status": "clean"
        }
    ]

    return accounts
