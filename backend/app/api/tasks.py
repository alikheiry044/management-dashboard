from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, desc
from typing import List, Optional
from datetime import datetime, date
from pydantic import BaseModel

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User

router = APIRouter(prefix="/tasks", tags=["Tasks"])


# ===== Models =====
class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    assigned_to: Optional[str] = None
    priority: str = "medium"  # low, medium, high, critical
    due_date: Optional[str] = None


class TaskOut(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    assigned_to: Optional[str] = None
    priority: str
    status: str  # pending, in_progress, completed, overdue
    due_date: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ===== Endpoints =====
@router.get("/stats")
async def get_task_stats(
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """آمار وظایف"""

    # داده‌های نمونه (بعداً از دیتابیس خوانده می‌شود)
    return {
        "total_tasks": 105,
        "completed": 86,
        "overdue": 7,
        "critical": 3,
        "on_time_rate": 91
    }


@router.get("/list")
async def get_tasks(
        status: Optional[str] = Query(None),
        priority: Optional[str] = Query(None),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """لیست وظایف"""

    # داده‌های نمونه
    tasks = [
        {
            "id": 1,
            "title": "بررسی فاکتورهای مغایرت‌دار",
            "description": "۳ فاکتور نیازمند بررسی فوری",
            "assigned_to": "مدیر مالی",
            "priority": "high",
            "status": "pending",
            "due_date": "1403/07/20",
            "created_at": "2024-10-01T10:00:00"
        },
        {
            "id": 2,
            "title": "تأیید پرداخت به تأمین‌کننده",
            "description": "مبلغ ۸۵ میلیون تومان",
            "assigned_to": "مدیرعامل",
            "priority": "critical",
            "status": "pending",
            "due_date": "1403/07/18",
            "created_at": "2024-10-01T09:00:00"
        },
        {
            "id": 3,
            "title": "بررسی تغییر حساب بانکی",
            "description": "تأمین‌کننده فولاد مبارکه",
            "assigned_to": "کارشناس مالی",
            "priority": "high",
            "status": "in_progress",
            "due_date": "1403/07/19",
            "created_at": "2024-10-01T08:00:00"
        },
        {
            "id": 4,
            "title": "گزارش ماهانه فروش",
            "description": "آماده‌سازی گزارش برای هیئت مدیره",
            "assigned_to": "مدیر فروش",
            "priority": "medium",
            "status": "completed",
            "due_date": "1403/07/15",
            "created_at": "2024-09-28T10:00:00"
        },
        {
            "id": 5,
            "title": "بررسی موجودی انبار",
            "description": "کالاهای کم‌موجودی",
            "assigned_to": "مدیر انبار",
            "priority": "medium",
            "status": "overdue",
            "due_date": "1403/07/10",
            "created_at": "2024-09-25T10:00:00"
        }
    ]

    # فیلتر کردن
    if status:
        tasks = [t for t in tasks if t["status"] == status]
    if priority:
        tasks = [t for t in tasks if t["priority"] == priority]

    return tasks


@router.post("/create", response_model=TaskOut)
async def create_task(
        task: TaskCreate,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """ایجاد وظیفه جدید"""
    # در نسخه واقعی، در دیتابیس ذخیره می‌شود
    return {
        "id": 999,
        "title": task.title,
        "description": task.description,
        "assigned_to": task.assigned_to,
        "priority": task.priority,
        "status": "pending",
        "due_date": task.due_date,
        "created_at": datetime.now()
    }