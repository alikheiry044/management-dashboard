from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from typing import List, Optional
from pydantic import BaseModel

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User

router = APIRouter(prefix="/suppliers", tags=["Suppliers"])


# ===== Models =====
class SupplierOut(BaseModel):
    id: int
    name: str
    code: str
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    risk_level: str
    risk_score: int
    status: str  # active, inactive, high_risk

    class Config:
        from_attributes = True


# ===== Endpoints =====
@router.get("/list")
async def get_suppliers(
        risk_level: Optional[str] = Query(None),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """لیست تأمین‌کنندگان"""

    # داده‌های نمونه
    suppliers = [
        {
            "id": 1,
            "name": "شرکت فولاد مبارکه اصفهان",
            "code": "SUP-001",
            "bank_name": "ملت",
            "account_number": "0123456789",
            "risk_level": "low",
            "risk_score": 15,
            "status": "active"
        },
        {
            "id": 2,
            "name": "پتروشیمی بندر امام",
            "code": "SUP-002",
            "bank_name": "صادرات",
            "account_number": "9876543210",
            "risk_level": "low",
            "risk_score": 20,
            "status": "active"
        },
        {
            "id": 3,
            "name": "شرکت آلفا تأمین",
            "code": "SUP-003",
            "bank_name": "پارسیان",
            "account_number": "5551234567",
            "risk_level": "high",
            "risk_score": 75,
            "status": "high_risk"
        },
        {
            "id": 4,
            "name": "شرکت ملی مس ایران",
            "code": "SUP-004",
            "bank_name": "تجارت",
            "account_number": "7778889990",
            "risk_level": "medium",
            "risk_score": 45,
            "status": "active"
        }
    ]

    # فیلتر کردن
    if risk_level:
        suppliers = [s for s in suppliers if s["risk_level"] == risk_level]

    return suppliers


@router.get("/stats")
async def get_supplier_stats(
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """آمار تأمین‌کنندگان"""
    return {
        "total_suppliers": 4,
        "active": 3,
        "high_risk": 1,
        "bank_changes": 0
    }
