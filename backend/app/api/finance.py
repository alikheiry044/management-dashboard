from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc, func, and_, or_
from typing import Optional, List
from datetime import datetime

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.finance import FinanceTransaction
from app.schemas.finance import (
    FinanceOut,
    FinanceStatusUpdate,
    FinanceCreate,
    FinanceTransactionUpdate,
    FinanceApproval,
    ReviewQueueItem,
    RiskAssessment,
    FinanceSummary,
    RiskOverview,
    FinanceListResponse,
    TransactionStatus,
    RiskLevel,
    ApprovalStatus,
)

router = APIRouter(prefix="/finance", tags=["Finance"])


# ===== Helper Functions =====

async def calculate_risk_score(
        db: AsyncSession,
        transaction: FinanceTransaction
) -> tuple[int, List[str], List[str]]:
    """
    محاسبه امتیاز ریسک تراکنش
    Returns: (risk_score, risk_factors, recommendations)
    """
    score = 0
    factors = []
    recommendations = []

    # 1. بررسی مبلغ غیرعادی (بیشتر از 2 برابر میانگین)
    result = await db.execute(
        select(func.avg(FinanceTransaction.amount)).where(
            FinanceTransaction.type == transaction.type
        )
    )
    avg_amount = result.scalar() or 0
    if transaction.amount > avg_amount * 2 and avg_amount > 0:
        score += 20
        factors.append("مبلغ غیرعادی (بیش از 2 برابر میانگین)")
        recommendations.append("بررسی دلیل مبلغ بالا با واحد مربوطه")

    # 2. بررسی فاکتور تکراری (همان مبلغ و طرف در 30 روز گذشته)
    from datetime import timedelta
    thirty_days_ago = datetime.now() - timedelta(days=30)
    result = await db.execute(
        select(FinanceTransaction).where(
            and_(
                FinanceTransaction.amount == transaction.amount,
                FinanceTransaction.party_name == transaction.party_name,
                FinanceTransaction.created_at >= thirty_days_ago,
                FinanceTransaction.id != transaction.id,
            )
        )
    )
    duplicates = result.scalars().all()
    if duplicates:
        score += 25
        factors.append("فاکتور تکراری (مبلغ و طرف یکسان در 30 روز گذشته)")
        recommendations.append("بررسی عدم ثبت تکراری فاکتور")

    # 3. تغییر حساب بانکی (اگر party_name قبلاً بوده و الان تغییر کرده)
    if transaction.party_name:
        result = await db.execute(
            select(FinanceTransaction).where(
                and_(
                    FinanceTransaction.party_name == transaction.party_name,
                    FinanceTransaction.id != transaction.id,
                )
            )
        )
        previous = result.scalars().first()
        if previous:
            # در نسخه پیشرفته‌تر، باید حساب بانکی را هم چک کنیم
            pass

    # 4. تراکنش‌های با مبلغ بسیار بالا (بیش از 500 میلیون)
    if transaction.amount > 500_000_000:
        score += 15
        factors.append("مبلغ بسیار بالا (بیش از 500 میلیون)")
        recommendations.append("نیاز به تأیید مدیرعامل")

    # 5. تراکنش بدون توضیحات
    if not transaction.description:
        score += 10
        factors.append("فاقد توضیحات")
        recommendations.append("افزودن توضیحات کامل برای تراکنش")

    # محدود کردن امتیاز به 100
    score = min(score, 100)

    # تعیین سطح ریسک
    if score >= 70:
        risk_level = "high"
    elif score >= 40:
        risk_level = "medium"
    else:
        risk_level = "low"

    return score, factors, recommendations


async def determine_approval_requirement(amount: float) -> Optional[str]:
    """تعیین نیاز به تأیید بر اساس مبلغ"""
    if amount > 2_000_000_000:  # 2 میلیارد
        return "ceo_and_owner"
    elif amount > 500_000_000:  # 500 میلیون
        return "ceo"
    elif amount > 100_000_000:  # 100 میلیون
        return "finance_manager"
    return None


# ===== API Endpoints =====

@router.get("/", response_model=FinanceListResponse)
async def list_finance(
        type: Optional[str] = Query(default=None, description="نوع تراکنش"),
        status: Optional[str] = Query(default=None, description="وضعیت تراکنش"),
        risk_level: Optional[str] = Query(default=None, description="سطح ریسک"),
        party_name: Optional[str] = Query(default=None, description="نام طرف"),
        min_amount: Optional[float] = Query(default=None, description="حداقل مبلغ"),
        max_amount: Optional[float] = Query(default=None, description="حداکثر مبلغ"),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=50, ge=1, le=100),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """لیست تراکنش‌های مالی با فیلتر پیشرفته و pagination"""

    query = select(FinanceTransaction)
    count_query = select(func.count(FinanceTransaction.id))

    # اعمال فیلترها
    if type:
        query = query.where(FinanceTransaction.type == type)
        count_query = count_query.where(FinanceTransaction.type == type)

    if status:
        query = query.where(FinanceTransaction.status == status)
        count_query = count_query.where(FinanceTransaction.status == status)

    if risk_level:
        query = query.where(FinanceTransaction.risk_level == risk_level)
        count_query = count_query.where(FinanceTransaction.risk_level == risk_level)

    if party_name:
        query = query.where(FinanceTransaction.party_name.ilike(f"%{party_name}%"))
        count_query = count_query.where(FinanceTransaction.party_name.ilike(f"%{party_name}%"))

    if min_amount is not None:
        query = query.where(FinanceTransaction.amount >= min_amount)
        count_query = count_query.where(FinanceTransaction.amount >= min_amount)

    if max_amount is not None:
        query = query.where(FinanceTransaction.amount <= max_amount)
        count_query = count_query.where(FinanceTransaction.amount <= max_amount)

    # شمارش کل
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # pagination
    offset = (page - 1) * page_size
    query = query.order_by(desc(FinanceTransaction.id)).offset(offset).limit(page_size)

    result = await db.execute(query)
    items = result.scalars().all()

    total_pages = (total + page_size - 1) // page_size

    return FinanceListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("/", response_model=FinanceOut, status_code=status.HTTP_201_CREATED)
async def create_finance(
        payload: FinanceCreate,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """ایجاد تراکنش مالی جدید با ارزیابی ریسک خودکار"""

    item = FinanceTransaction(
        type=payload.type,
        amount=payload.amount,
        party_name=payload.party_name,
        description=payload.description,
        transaction_date=payload.transaction_date,
        reference_number=payload.reference_number,
        payment_method=payload.payment_method,
        status=payload.status,
        risk_level=payload.risk_level,
        risk_score=payload.risk_score,
        needs_followup=payload.needs_followup,
        note=payload.note,
    )

    db.add(item)
    await db.flush()  # برای گرفتن ID قبل از commit

    # ارزیابی ریسک خودکار
    risk_score, risk_factors, recommendations = await calculate_risk_score(db, item)

    item.risk_score = risk_score
    item.risk_level = "high" if risk_score >= 70 else "medium" if risk_score >= 40 else "low"

    # تشخیص فاکتور تکراری
    if "فاکتور تکراری" in " ".join(risk_factors):
        item.is_duplicate = True

    # تعیین نیاز به تأیید
    approval_required = await determine_approval_requirement(float(item.amount))
    if approval_required:
        item.requires_approval_from = approval_required
        item.approval_status = "pending"
        item.status = "needs_review"

    await db.commit()
    await db.refresh(item)

    return item


@router.patch("/{item_id}/status", response_model=FinanceOut)
async def update_finance_status(
        item_id: int,
        payload: FinanceStatusUpdate,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """به‌روزرسانی وضعیت تراکنش"""

    result = await db.execute(
        select(FinanceTransaction).where(FinanceTransaction.id == item_id)
    )
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="تراکنش پیدا نشد"
        )

    # اعتبارسنجی وضعیت
    allowed_statuses = [s.value for s in TransactionStatus]
    if payload.status not in allowed_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"وضعیت نامعتبر. مقادیر مجاز: {allowed_statuses}"
        )

    # به‌روزرسانی فیلدها
    item.status = payload.status
    if payload.note is not None:
        item.note = payload.note
    if payload.risk_level is not None:
        item.risk_level = payload.risk_level
    if payload.risk_score is not None:
        item.risk_score = payload.risk_score

    # تنظیم needs_followup
    item.needs_followup = payload.status in ("needs_review", "stopped")

    # اگر تأیید شده، اطلاعات بررسی‌کننده را ثبت کن
    if payload.status == "approved":
        item.reviewed_by = current_user.id
        item.reviewed_at = datetime.now()

    await db.commit()
    await db.refresh(item)
    return item


@router.get("/review-queue", response_model=List[ReviewQueueItem])
async def review_queue(
        risk_level: Optional[str] = Query(default=None, description="فیلتر بر اساس سطح ریسک"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """صف بررسی تراکنش‌های نیازمند توجه"""

    query = select(FinanceTransaction).where(
        FinanceTransaction.status.in_(["needs_review", "stopped"])
    )

    if risk_level:
        query = query.where(FinanceTransaction.risk_level == risk_level)

    query = query.order_by(desc(FinanceTransaction.risk_score), desc(FinanceTransaction.amount))

    result = await db.execute(query)
    return result.scalars().all()


@router.post("/{item_id}/approve", response_model=FinanceOut)
async def approve_transaction(
        item_id: int,
        payload: FinanceApproval,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """تأیید یا رد تراکنش"""

    result = await db.execute(
        select(FinanceTransaction).where(FinanceTransaction.id == item_id)
    )
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="تراکنش پیدا نشد"
        )

    if payload.approval_status == ApprovalStatus.APPROVED:
        item.approval_status = "approved"
        item.approved_by = current_user.id
        item.approved_at = datetime.now()
        item.status = "approved"
    elif payload.approval_status == ApprovalStatus.REJECTED:
        item.approval_status = "rejected"
        item.status = "stopped"
        if payload.note:
            item.note = payload.note

    item.reviewed_by = current_user.id
    item.reviewed_at = datetime.now()

    await db.commit()
    await db.refresh(item)
    return item


@router.get("/{item_id}/risk-assessment", response_model=RiskAssessment)
async def get_risk_assessment(
        item_id: int,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """دریافت ارزیابی ریسک تراکنش"""

    result = await db.execute(
        select(FinanceTransaction).where(FinanceTransaction.id == item_id)
    )
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="تراکنش پیدا نشد"
        )

    # محاسبه مجدد ریسک
    risk_score, risk_factors, recommendations = await calculate_risk_score(db, item)

    return RiskAssessment(
        transaction_id=item.id,
        risk_score=risk_score,
        risk_level=RiskLevel.HIGH if risk_score >= 70 else RiskLevel.MEDIUM if risk_score >= 40 else RiskLevel.LOW,
        factors=risk_factors,
        recommendations=recommendations,
    )


@router.get("/summary/overview", response_model=FinanceSummary)
async def finance_summary(
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """خلاصه آماری تراکنش‌های مالی"""

    # شمارش کل
    total_result = await db.execute(select(func.count(FinanceTransaction.id)))
    total_transactions = total_result.scalar() or 0

    # مجموع مبلغ
    amount_result = await db.execute(select(func.sum(FinanceTransaction.amount)))
    total_amount = amount_result.scalar() or 0

    # شمارش بر اساس وضعیت
    pending_result = await db.execute(
        select(func.count(FinanceTransaction.id)).where(
            FinanceTransaction.status == "needs_review"
        )
    )
    pending_review = pending_result.scalar() or 0

    high_risk_result = await db.execute(
        select(func.count(FinanceTransaction.id)).where(
            FinanceTransaction.risk_level == "high"
        )
    )
    high_risk = high_risk_result.scalar() or 0

    stopped_result = await db.execute(
        select(func.count(FinanceTransaction.id)).where(
            FinanceTransaction.status == "stopped"
        )
    )
    stopped = stopped_result.scalar() or 0

    approved_result = await db.execute(
        select(func.count(FinanceTransaction.id)).where(
            FinanceTransaction.status == "approved"
        )
    )
    approved = approved_result.scalar() or 0

    settled_result = await db.execute(
        select(func.count(FinanceTransaction.id)).where(
            FinanceTransaction.status == "settled"
        )
    )
    settled = settled_result.scalar() or 0

    return FinanceSummary(
        total_transactions=total_transactions,
        total_amount=total_amount,
        pending_review=pending_review,
        high_risk=high_risk,
        stopped=stopped,
        approved=approved,
        settled=settled,
    )


@router.get("/risk/overview", response_model=RiskOverview)
async def risk_overview(
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """نمای کلی ریسک تراکنش‌ها"""

    # شمارش بر اساس سطح ریسک
    low_result = await db.execute(
        select(func.count(FinanceTransaction.id)).where(
            FinanceTransaction.risk_level == "low"
        )
    )
    low_risk_count = low_result.scalar() or 0

    medium_result = await db.execute(
        select(func.count(FinanceTransaction.id)).where(
            FinanceTransaction.risk_level == "medium"
        )
    )
    medium_risk_count = medium_result.scalar() or 0

    high_result = await db.execute(
        select(func.count(FinanceTransaction.id)).where(
            FinanceTransaction.risk_level == "high"
        )
    )
    high_risk_count = high_result.scalar() or 0

    # میانگین امتیاز ریسک
    avg_result = await db.execute(
        select(func.avg(FinanceTransaction.risk_score))
    )
    average_risk_score = avg_result.scalar() or 0

    # مجموع مبلغ در ریسک
    at_risk_result = await db.execute(
        select(func.sum(FinanceTransaction.amount)).where(
            FinanceTransaction.risk_level.in_(["medium", "high"])
        )
    )
    total_at_risk_amount = at_risk_result.scalar() or 0

    return RiskOverview(
        low_risk_count=low_risk_count,
        medium_risk_count=medium_risk_count,
        high_risk_count=high_risk_count,
        average_risk_score=float(average_risk_score),
        total_at_risk_amount=total_at_risk_amount,
    )


# ===== Banking Endpoints =====

@router.get("/banking/stats", response_model=dict)
async def banking_stats(
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """آمار عملیات بانکی از روی تراکنش‌های مالی"""


# ===== Banking Endpoints =====
from typing import List  # اگر این خط در بالای فایل نیست، آن را به بالای فایل اضافه کن


# ==========================================
# ===== Banking Endpoints (عملیات بانکی) =====
# ==========================================

@router.get("/banking/stats")
async def banking_stats(
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """آمار عملیات بانکی از روی تراکنش‌های مالی"""
    from datetime import date
    from sqlalchemy import func

    # تعداد کل تراکنش‌ها
    total_result = await db.execute(select(func.count(FinanceTransaction.id)))
    total_tx = total_result.scalar() or 0

    # مجموع مبلغ
    amount_result = await db.execute(select(func.sum(FinanceTransaction.amount)))
    total_amount = amount_result.scalar() or 0

    # تراکنش‌های امروز
    today = date.today()
    today_result = await db.execute(
        select(func.count(FinanceTransaction.id)).where(
            func.date(FinanceTransaction.created_at) == today
        )
    )
    today_tx = today_result.scalar() or 0

    # تراکنش‌های نیازمند بررسی (مغایرت)
    pending_result = await db.execute(
        select(func.count(FinanceTransaction.id)).where(
            FinanceTransaction.status == "needs_review"
        )
    )
    pending_tx = pending_result.scalar() or 0

    # تراکنش‌های تأییدشده (بدون مغایرت)
    approved_result = await db.execute(
        select(func.count(FinanceTransaction.id)).where(
            FinanceTransaction.status.in_(["approved", "settled"])
        )
    )
    approved_tx = approved_result.scalar() or 0

    return {
        "total_balance": float(total_amount) if total_amount else 0.0,
        "total_accounts": 4,
        "today_transactions": today_tx,
        "pending_reconciliations": pending_tx,
        "clean_accounts": max(0, 4 - (1 if pending_tx > 0 else 0)),
        "total_transactions": total_tx,
        "approved_transactions": approved_tx
    }


@router.get("/banking/transactions", response_model=List[FinanceOut])
async def banking_transactions(
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
    return result.scalars().all()


