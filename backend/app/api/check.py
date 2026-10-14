from decimal import Decimal

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.bank_check import BankCheck
from app.models.user import User
from app.api.check_parser import parse_checks_file, norm
# فایل check_parser.py را در app/services/ بگذار


try:
    from app.api.upload import clean_amount
except Exception:                      # اگر نبود، نسخه‌ی ساده
    def clean_amount(v):
        s = norm(v).replace(",", "")
        try:
            return Decimal(s)
        except Exception:
            return Decimal(0)

router = APIRouter(
    prefix="/checks",
    tags=["Checks"],
    dependencies=[Depends(get_current_user)],
)

# کلیدها بعد از norm() مقایسه می‌شوند (ك/ي عربی قبلاً فارسی شده‌اند)
STATUS_MAP = {
    "خرج شده": "spent",
    "خرج": "spent",
    "پاس شده": "passed",
    "پاس": "passed",
    "وصول شده": "passed",
    "در جریان": "open",
    "نزد صندوق": "open",
    "واخواست": "returned",
    "برگشتی": "returned",
    "برگشت": "returned",
    "open": "open",
    "passed": "passed",
}

ALLOWED_STATUS = {"spent", "passed", "open", "returned"}


def _map_status(raw) -> str:
    text = norm(raw)
    if not text:
        return "unknown"
    for k, v in STATUS_MAP.items():
        if k in text:
            return v
    return "unknown"


def _dedupe_key(check_type, number, party, due):
    return (check_type, norm(number), norm(party), norm(due))


async def _save_checks(
    db: AsyncSession,
    file: UploadFile,
    check_type: str,
    force_status: str | None,
    replace: bool,
    message: str,
):
    if force_status and force_status not in ALLOWED_STATUS:
        raise HTTPException(400, f"وضعیت نامعتبر: {force_status}")

    content = await file.read()
    if not content:
        raise HTTPException(400, "فایل خالی است")

    try:
        parsed = parse_checks_file(content, check_type, filename=file.filename or "")
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, f"خواندن فایل ممکن نشد: {e}")

    items, errors, seen = [], [], set()
    skipped = len(parsed["skipped"])

    for c in parsed["checks"]:
        try:
            party = c["party"]
            # فقط ردیف خلاصه/جمع را رد کن (نه هر نامی که «ارز» دارد)
            if not party or party.startswith(("جمع", "مجموع", "تعداد رکورد")):
                skipped += 1
                continue

            # وضعیت: اجباری از نوع فایل > ستون وضعیت فایل > تاریخ وصول
            if force_status:
                status = force_status
            elif c["status_raw"]:
                status = _map_status(c["status_raw"])
            else:
                status = c["status"] if c["status"] in ALLOWED_STATUS else "unknown"

            amount = clean_amount(c["amount"]) if c["amount"] is not None else Decimal(0)
            # چک دریافتی بدون مبلغ معتبر نیست؛ پرداختنی ممکن است ستون مبلغ نداشته باشد
            if check_type == "receivable_check" and amount <= 0:
                skipped += 1
                continue

            key = _dedupe_key(check_type, c["check_no"], party, c["due_date"])
            if key in seen:
                skipped += 1
                continue
            seen.add(key)

            items.append(BankCheck(
                check_type=check_type,
                status=status,
                detail_code=c["party_code"] or None,
                party_name=party,
                movement_type=c["type"] or None,
                check_number=c["check_no"] or None,
                amount=amount,
                due_date=c["due_date"] or None,
                receive_date=c["receive_date"] or c["issue_date"] or None,
                bank_name=c["bank_account"] or None,
                owner_name=c["owner"],
                settle_date=c["clear_date"],
                description=c["description"],
                source_file=file.filename,
            ))
        except Exception as e:
            errors.append(f"چک {c.get('check_no') or '?'}: {e}")

    if not items:
        raise HTTPException(400, "هیچ چک معتبری پیدا نشد")

    if replace:
        # فقط وضعیت‌هایی که در این فایل هست جایگزین می‌شوند؛
        # آپلود فایل «خرج‌شده» چک‌های دریافتنی در جریان را پاک نمی‌کند.
        statuses = {i.status for i in items}
        await db.execute(
            delete(BankCheck).where(
                BankCheck.check_type == check_type,
                BankCheck.status.in_(statuses),
            )
        )

    # چک‌هایی که از قبل (با وضعیت دیگر) ثبت شده‌اند دوباره اضافه نشوند
    existing = (await db.execute(
        select(BankCheck).where(BankCheck.check_type == check_type)
    )).scalars().all()
    exist_keys = {
        _dedupe_key(r.check_type, r.check_number, r.party_name, r.due_date)
        for r in existing
    }
    new_items = [
        i for i in items
        if _dedupe_key(i.check_type, i.check_number, i.party_name, i.due_date) not in exist_keys
    ]
    dup = len(items) - len(new_items)

    db.add_all(new_items)
    await db.commit()

    return {
        "message": message,
        "created": len(new_items),
        "skipped": skipped,
        "skipped_duplicates": dup,
        "errors": errors[:20],
        "warnings": parsed["warnings"],
    }


@router.post("/upload-receivable")
async def upload_receivable_checks(
    file: UploadFile = File(...),
    replace: bool = Query(True),
    force_status: str | None = Query(None, description="spent | passed | open | returned"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """چک دریافتی (از جمله خرج‌شده / سررسید)."""
    return await _save_checks(
        db, file, "receivable_check", force_status, replace,
        "آپلود چک‌های دریافتی انجام شد",
    )


@router.post("/upload-payable")
async def upload_payable_checks(
    file: UploadFile = File(...),
    replace: bool = Query(True),
    force_status: str | None = Query(None, description="مثلاً passed برای فایل «پاس‌شده»"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """چک پرداختنی (مرور بانک چک پرداختنی / پاس‌شده)."""
    return await _save_checks(
        db, file, "payable_check", force_status, replace,
        "آپلود چک‌های پرداختنی انجام شد",
    )


@router.get("/")
async def list_checks(
    check_type: str | None = Query(None),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(BankCheck).order_by(BankCheck.due_date.desc().nullslast())
    if check_type:
        q = q.where(BankCheck.check_type == check_type)
    if status:
        q = q.where(BankCheck.status == status)

    rows = (await db.execute(q)).scalars().all()
    return [
        {
            "id": r.id,
            "check_type": r.check_type,
            "status": r.status,
            "detail_code": r.detail_code,
            "party_name": r.party_name,
            "check_number": r.check_number,
            "amount": str(r.amount),
            "due_date": r.due_date,
            "receive_date": r.receive_date,
            "settle_date": r.settle_date,
            "bank_name": r.bank_name,
            "owner_name": r.owner_name,
            "description": r.description,
        }
        for r in rows
    ]


@router.get("/summary")
async def checks_summary(
    check_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(BankCheck)
    if check_type:
        q = q.where(BankCheck.check_type == check_type)
    rows = (await db.execute(q)).scalars().all()
    total = sum((r.amount or Decimal(0) for r in rows), Decimal(0))
    by_status = {}
    for r in rows:
        by_status[r.status] = by_status.get(r.status, 0) + 1

    return {
        "count": len(rows),
        "total_amount": str(total),
        "by_status": by_status,
    }