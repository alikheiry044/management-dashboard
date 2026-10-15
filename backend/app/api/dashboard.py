from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.finance import FinanceTransaction
from app.models.inventory import InventoryItem
from app.models.report_snapshot import ReportSnapshot
from app.models.sales import SalesInvoice

# بانک و چک
try:
    from app.models.bank_balance import BankBalance
except Exception:
    BankBalance = None
try:
    from app.models.bank_check import BankCheck
except Exception:
    BankCheck = None

router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"],
    dependencies=[Depends(get_current_user)],
)

ALERT_CONCENTRATION_PCT = 0.20
ALERT_MIN_PARTIES = 3
ALERT_OVERDUE_DAYS = 30
MAX_NAMES_IN_MESSAGE = 3

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def jalali_to_gregorian(jy: int, jm: int, jd: int) -> tuple[int, int, int]:
    jy += 1595
    days = -355668 + (365 * jy) + ((jy // 33) * 8) + (((jy % 33) + 3) // 4) + jd
    if jm < 7:
        days += (jm - 1) * 31
    else:
        days += ((jm - 7) * 30) + 186
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    leap = (gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0
    month_days = [0, 31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 0
    while gm < 13 and gd > month_days[gm]:
        gd -= month_days[gm]
        gm += 1
    return gy, gm, gd


def parse_sale_date(value) -> date | None:
    if value is None:
        return None
    text = str(value).strip().translate(_DIGITS)[:10]
    parts = text.replace("-", "/").split("/")
    if len(parts) != 3:
        return None
    try:
        y, m, d = (int(p) for p in parts)
        if y >= 1700:
            return date(y, m, d)
        if not (1 <= m <= 12) or not (1 <= d <= (31 if m <= 6 else 30)):
            return None
        gy, gm, gd = jalali_to_gregorian(y, m, d)
        return date(gy, gm, gd)
    except (ValueError, OverflowError):
        return None


def _names(items: list[str]) -> str:
    shown = "، ".join(items[:MAX_NAMES_IN_MESSAGE])
    return shown + (" و ..." if len(items) > MAX_NAMES_IN_MESSAGE else "")


def build_alerts(
    *,
    receivables_by_party,
    open_invoices,
    inventory,
    checks_open: int = 0,
    bank_negative: int = 0,
    today: date,
) -> list[dict]:
    alerts: list[dict] = []

    positives = [(n or "نامشخص", Decimal(a)) for n, a in receivables_by_party if a and Decimal(a) > 0]
    total = sum((a for _, a in positives), Decimal(0))
    if len(positives) >= ALERT_MIN_PARTIES and total > 0:
        for name, amount in sorted(positives, key=lambda x: x[1], reverse=True):
            share = amount / total
            if share >= Decimal(str(ALERT_CONCENTRATION_PCT)):
                alerts.append({
                    "code": "receivable_concentration",
                    "severity": "high",
                    "message": f"مطالبات «{name}» حدود {round(share * 100)}٪ کل مطالبات است",
                    "amount": str(amount),
                })

    overdue = []
    for _name, sale_date, remaining in open_invoices:
        d = parse_sale_date(sale_date)
        if d is not None and (today - d).days > ALERT_OVERDUE_DAYS:
            overdue.append(Decimal(remaining))
    if overdue:
        alerts.append({
            "code": "overdue_invoices",
            "severity": "medium",
            "message": f"{len(overdue)} فاکتور بیش از {ALERT_OVERDUE_DAYS} روز تسویه نشده",
            "amount": str(sum(overdue, Decimal(0))),
        })

    negatives = [str(t or c) for c, t, q in inventory if q is not None and Decimal(q) < 0]
    zeros = [str(t or c) for c, t, q in inventory if q is not None and Decimal(q) == 0]
    if negatives:
        alerts.append({
            "code": "negative_stock",
            "severity": "high",
            "message": f"{len(negatives)} کالا موجودی منفی: {_names(negatives)}",
            "amount": None,
        })
    if zeros:
        alerts.append({
            "code": "zero_stock",
            "severity": "medium",
            "message": f"{len(zeros)} کالا موجودی صفر: {_names(zeros)}",
            "amount": None,
        })

    if checks_open:
        alerts.append({
            "code": "open_checks",
            "severity": "medium",
            "message": f"{checks_open} فقره چک با وضعیت باز/نامشخص",
            "amount": None,
        })
    if bank_negative:
        alerts.append({
            "code": "negative_bank",
            "severity": "high",
            "message": f"{bank_negative} حساب بانکی مانده منفی دارد",
            "amount": None,
        })

    order = {"high": 0, "medium": 1}
    alerts.sort(key=lambda a: order.get(a["severity"], 9))
    return alerts


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = (
        355666
        + (365 * gy)
        + ((gy2 + 3) // 4)
        - ((gy2 + 99) // 100)
        + ((gy2 + 399) // 400)
        + gd
        + g_d_m[gm - 1]
    )
    jy = -1595 + (33 * (days // 12053))
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + days % 31
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + (days - 186) % 30
    return jy, jm, jd


REPORT_TOP_N = 5


def _inv_title_col():
    # مدل بعضی‌ها title و بعضی name دارند
    if hasattr(InventoryItem, "title"):
        return InventoryItem.title
    if hasattr(InventoryItem, "name"):
        return InventoryItem.name
    return InventoryItem.code


async def _load_common(db: AsyncSession):
    open_rows = (
        await db.execute(
            select(
                SalesInvoice.customer_name,
                SalesInvoice.sale_date,
                SalesInvoice.remaining_amount,
            ).where(SalesInvoice.remaining_amount > 0)
        )
    ).all()
    receivable_rows = (
        await db.execute(
            select(FinanceTransaction.party_name, func.sum(FinanceTransaction.amount))
            .where(FinanceTransaction.type == "receivable")
            .group_by(FinanceTransaction.party_name)
        )
    ).all()
    title_col = _inv_title_col()
    inventory_rows = (
        await db.execute(select(InventoryItem.code, title_col, InventoryItem.quantity))
    ).all()
    return open_rows, receivable_rows, inventory_rows


@router.get("/summary")
async def dashboard_summary(db: AsyncSession = Depends(get_db)):
    total_sales = (
        await db.execute(select(func.coalesce(func.sum(SalesInvoice.amount), 0)))
    ).scalar_one()
    invoice_count = (
        await db.execute(select(func.count()).select_from(SalesInvoice))
    ).scalar_one()

    open_rows, receivable_rows, inventory_rows = await _load_common(db)
    total_receivables = sum((Decimal(a or 0) for _, a in receivable_rows), Decimal(0))

    total_payables = (
        await db.execute(
            select(func.coalesce(func.sum(FinanceTransaction.amount), 0)).where(
                FinanceTransaction.type == "payable"
            )
        )
    ).scalar_one()

    # انبار
    inv_value_col = (
        InventoryItem.total_value
        if hasattr(InventoryItem, "total_value")
        else None
    )
    if inv_value_col is not None:
        inventory_value = (
            await db.execute(select(func.coalesce(func.sum(inv_value_col), 0)))
        ).scalar_one()
    else:
        inventory_value = 0

    low_stock = sum(
        1
        for _, _, q in inventory_rows
        if q is not None and Decimal(q) > 0 and Decimal(q) < 10
    )
    zero_stock = sum(
        1 for _, _, q in inventory_rows if q is not None and Decimal(q) == 0
    )

    # بانک
    bank_balance = 0
    bank_negative = 0
    if BankBalance is not None:
        bank_balance = (
            await db.execute(select(func.coalesce(func.sum(BankBalance.balance), 0)))
        ).scalar_one()
        bank_negative = (
            await db.execute(
                select(func.count()).select_from(BankBalance).where(BankBalance.balance < 0)
            )
        ).scalar_one()

    # چک
    checks_count = 0
    checks_amount = 0
    checks_open = 0
    if BankCheck is not None:
        checks_count = (
            await db.execute(select(func.count()).select_from(BankCheck))
        ).scalar_one()
        checks_amount = (
            await db.execute(select(func.coalesce(func.sum(BankCheck.amount), 0)))
        ).scalar_one()
        checks_open = (
            await db.execute(
                select(func.count())
                .select_from(BankCheck)
                .where(BankCheck.status.in_(["open", "unknown"]))
            )
        ).scalar_one()

    alerts = build_alerts(
        receivables_by_party=receivable_rows,
        open_invoices=open_rows,
        inventory=inventory_rows,
        checks_open=int(checks_open or 0),
        bank_negative=int(bank_negative or 0),
        today=date.today(),
    )

    return {
        "total_sales": str(total_sales),
        "invoice_count": int(invoice_count or 0),
        "total_receivables": str(total_receivables),
        "total_payables": str(total_payables),
        "open_invoices": len(open_rows),
        "inventory_value": str(inventory_value),
        "low_stock": low_stock,
        "zero_stock": zero_stock,
        "bank_balance": str(bank_balance),
        "checks_count": int(checks_count or 0),
        "checks_amount": str(checks_amount),
        "alerts": alerts,
    }


@router.get("/report")
async def management_report(db: AsyncSession = Depends(get_db)):
    invoice_count, total_sales = (
        await db.execute(
            select(func.count(), func.coalesce(func.sum(SalesInvoice.amount), 0)).select_from(
                SalesInvoice
            )
        )
    ).one()
    sale_dates = (await db.execute(select(SalesInvoice.sale_date).distinct())).scalars().all()
    payable_total = (
        await db.execute(
            select(func.coalesce(func.sum(FinanceTransaction.amount), 0)).where(
                FinanceTransaction.type == "payable"
            )
        )
    ).scalar_one()
    open_rows, receivable_rows, inventory_rows = await _load_common(db)

    # گزارش متنی قبلی + خلاصه بانک/چک در همین ساختار
    summary_extra = await dashboard_summary(db)

    from_report = {
        "generated_on": summary_extra.get("alerts") and date.today().isoformat(),
        "sales": {
            "total": str(total_sales),
            "invoice_count": invoice_count,
            "open_count": len(open_rows),
        },
        "receivables": {"total": summary_extra["total_receivables"]},
        "payables": {"total": str(payable_total)},
        "inventory": {
            "value": summary_extra["inventory_value"],
            "zero_count": summary_extra["zero_stock"],
            "low_stock": summary_extra["low_stock"],
        },
        "bank": {"balance": summary_extra["bank_balance"]},
        "checks": {
            "count": summary_extra["checks_count"],
            "amount": summary_extra["checks_amount"],
        },
        "alerts": summary_extra["alerts"],
    }
    return from_report


@router.get("/sales-trend")
async def sales_trend(db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(
                SalesInvoice.sale_date,
                func.coalesce(func.sum(SalesInvoice.amount), 0),
            )
            .group_by(SalesInvoice.sale_date)
            .order_by(SalesInvoice.sale_date)
        )
    ).all()
    return {
        "labels": [str(d) if d is not None else "نامشخص" for d, _ in rows],
        "values": [float(v or 0) for _, v in rows],
    }


@router.get("/history")
async def snapshot_history(
    report_type: Literal["sales", "receivables", "payables", "expense", "inventory"] = Query(...),
    limit: int = Query(60, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(ReportSnapshot)
            .where(ReportSnapshot.report_type == report_type)
            .order_by(ReportSnapshot.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [
        {
            "date": r.created_at.isoformat() if r.created_at else None,
            "total": str(r.total_amount) if r.total_amount is not None else None,
            "rows": r.row_count,
            "mode": r.mode,
            "filename": r.filename,
        }
        for r in reversed(rows)
    ]


@router.get("/expense-trend")
async def expense_trend(db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(
                FinanceTransaction.transaction_date,
                func.coalesce(func.sum(FinanceTransaction.amount), 0),
            )
            .where(FinanceTransaction.type == "expense")
            .group_by(FinanceTransaction.transaction_date)
            .order_by(FinanceTransaction.transaction_date)
        )
    ).all()
    return {
        "labels": [str(d) if d is not None else "نامشخص" for d, _ in rows],
        "values": [float(v or 0) for _, v in rows],
    }


@router.get("/receivables-trend")
async def receivables_trend(db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(
                FinanceTransaction.party_name,
                func.coalesce(func.sum(FinanceTransaction.amount), 0),
            )
            .where(FinanceTransaction.type == "receivable")
            .group_by(FinanceTransaction.party_name)
            .order_by(func.sum(FinanceTransaction.amount).desc())
            .limit(10)
        )
    ).all()
    return {
        "labels": [str(name) if name else "نامشخص" for name, _ in rows],
        "values": [float(v or 0) for _, v in rows],
    }
