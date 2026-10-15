from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, desc
from typing import List, Optional
from datetime import date
import os

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.finance import FinanceTransaction
from app.services.bank_parser import parse_bank_accounts

router = APIRouter(prefix="/banking", tags=["Banking"])

DEFAULT_BANK_FILE = "مرور بانكها دريافت و پرداخت.xls"


@router.get("/stats")
async def get_banking_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """آمار عملیات بانکی بر اساس فایل اکسل واقعی و دیتابیس"""
    total_balance = 0.0
    total_accounts = 0

    if os.path.exists(DEFAULT_BANK_FILE):
        try:
            with open(DEFAULT_BANK_FILE, "rb") as f:
                content = f.read()
            accounts_data = parse_bank_accounts(content)
            total_accounts = len(accounts_data)
            total_balance = float(sum(acc.balance for acc in accounts_data))
        except Exception:
            pass

    today = date.today()
    today_result = await db.execute(
        select(func.count(FinanceTransaction.id)).where(
            func.date(FinanceTransaction.created_at) == today
        )
    )
    today_transactions = today_result.scalar() or 0

    pending_result = await db.execute(
        select(func.count(FinanceTransaction.id)).where(
            FinanceTransaction.status == "needs_review"
        )
    )
    pending_reconciliations = pending_result.scalar() or 0

    clean_accounts = max(0, total_accounts - (1 if pending_reconciliations > 0 else 0))

    return {
        "total_balance": total_balance,
        "total_accounts": total_accounts,
        "today_transactions": today_transactions,
        "pending_reconciliations": pending_reconciliations,
        "clean_accounts": clean_accounts,
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
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in transactions
    ]


@router.get("/accounts")
async def get_bank_accounts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """لیست حساب‌های بانکی استخراج شده مستقیم از فایل اکسل مرور بانک‌ها"""
    if not os.path.exists(DEFAULT_BANK_FILE):
        return []

    try:
        with open(DEFAULT_BANK_FILE, "rb") as f:
            content = f.read()
        accounts = parse_bank_accounts(content)

        return [
            {
                "id": acc.detail_code,
                "name": acc.title,
                "bank": acc.title.split()[0] if acc.title else "نامشخص",
                "number": acc.account_number or "-",
                "opening_balance": acc.opening_balance,
                "receipts": acc.receipts,
                "payments": acc.payments,
                "balance": acc.balance,
                "status": "clean",
            }
            for acc in accounts
        ]
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"خطا در خواندن فایل اکسل بانک‌ها: {str(e)}"
        )


@router.post("/upload-bank-file")
async def upload_bank_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """آپلود و جایگزینی فایل اکسل جدید مرور بانک‌ها"""
    try:
        content = await file.read()
        accounts = parse_bank_accounts(content)

        with open(DEFAULT_BANK_FILE, "wb") as f:
            f.write(content)

        return {
            "status": "success",
            "message": f"فایل با موفقیت آپلود شد و تعداد {len(accounts)} حساب بانکی بروزرسانی گردید.",
            "count": len(accounts),
        }
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"فایل نامعتبر است: {str(e)}"
        )
    