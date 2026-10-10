# app/services/risk_engine.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_
from datetime import datetime, timedelta
from typing import Tuple, List, Dict, Any
from app.models.finance import FinanceTransaction


async def assess_transaction_risk(
        db: AsyncSession,
        transaction_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    موتور ارزیابی ریسک تراکنش‌های مالی
    ورودی: دیکشنری داده‌های تراکنش (قبل از ذخیره نهایی)
    خروجی: دیکشنری شامل risk_score, risk_level, factors, recommendations, is_duplicate, amount_anomaly
    """
    score = 0
    factors = []
    recommendations = []
    is_duplicate = False
    amount_anomaly = False

    amount = float(transaction_data.get("amount", 0))
    party_name = transaction_data.get("party_name", "")
    trans_type = transaction_data.get("type", "expense")
    description = transaction_data.get("description", "")

    # ۱. بررسی فاکتور تکراری (همان مبلغ و طرف حساب در ۳۰ روز گذشته)
    if amount > 0 and party_name:
        thirty_days_ago = datetime.now() - timedelta(days=30)
        # توجه: اگر transaction_date شمسی است، مقایسه با created_at انجام می‌شود
        query = select(FinanceTransaction).where(
            and_(
                FinanceTransaction.amount == amount,
                FinanceTransaction.party_name == party_name,
                FinanceTransaction.created_at >= thirty_days_ago,
                FinanceTransaction.type == trans_type
            )
        )
        result = await db.execute(query)
        duplicates = result.scalars().all()

        if duplicates:
            score += 30
            is_duplicate = True
            factors.append("فاکتور تکراری (مبلغ و طرف یکسان در ۳۰ روز گذشته)")
            recommendations.append("بررسی عدم ثبت تکراری فاکتور و تطبیق با اسناد قبلی")

    # ۲. بررسی مبلغ غیرعادی (بیش از ۲ برابر میانگین همان نوع تراکنش)
    if amount > 0:
        avg_query = select(func.avg(FinanceTransaction.amount)).where(
            FinanceTransaction.type == trans_type
        )
        avg_result = await db.execute(avg_query)
        avg_amount = float(avg_result.scalar() or 0)

        if avg_amount > 0 and amount > (avg_amount * 2):
            score += 20
            amount_anomaly = True
            factors.append("مبلغ غیرعادی (بیش از ۲ برابر میانگین تاریخی)")
            recommendations.append("بررسی دلیل مبلغ بالا با واحد درخواست‌کننده")

    # ۳. بررسی مبالغ بسیار بالا (سقف‌های کنترلی)
    if amount > 2_000_000_000:  # بیش از ۲ میلیارد
        score += 25
        factors.append("مبلغ بسیار بالا (بیش از ۲ میلیارد)")
        recommendations.append("نیاز به تأیید مدیرعامل و مالک")
    elif amount > 500_000_000:  # بیش از ۵۰۰ میلیون
        score += 15
        factors.append("مبلغ بالا (بیش از ۵۰۰ میلیون)")
        recommendations.append("نیاز به تأیید مدیر مالی")

    # ۴. تراکنش بدون توضیحات
    if not description or len(description.strip()) < 5:
        score += 10
        factors.append("فاقد توضیحات کافی")
        recommendations.append("الزامی کردن درج توضیحات کامل برای تراکنش")

    # محدود کردن امتیاز به حداکثر ۱۰۰
    score = min(score, 100)

    # تعیین سطح ریسک بر اساس امتیاز
    if score >= 60:
        risk_level = "high"
    elif score >= 30:
        risk_level = "medium"
    else:
        risk_level = "low"

    return {
        "risk_score": score,
        "risk_level": risk_level,
        "factors": factors,
        "recommendations": recommendations,
        "is_duplicate": is_duplicate,
        "amount_anomaly": amount_anomaly,
        "requires_approval_from": "ceo_and_owner" if amount > 2_000_000_000 else "ceo" if amount > 500_000_000 else "finance_manager" if amount > 100_000_000 else None
    }
