from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.api.upload import read_uploaded_table
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.bank_balance import BankBalance
from app.models.user import User
from app.schemas.bank import BankListOut, BankUploadOut
from app.services.bank_parser import BankParseError, parse_bank_rows

router = APIRouter(prefix="/banks", tags=["Banks"])


@router.get("/", response_model=BankListOut)
async def list_bank_accounts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(BankBalance).order_by(BankBalance.detail_code))
    items = result.scalars().all()

    return {
        "items": items,
        "totals": {
            "count": len(items),
            "opening_balance": sum(i.opening_balance for i in items),
            "receipts": sum(i.receipts for i in items),
            "payments": sum(i.payments for i in items),
            "balance": sum(i.balance for i in items),
        },
        "source_file": items[0].source_file if items else None,
        "uploaded_at": items[0].uploaded_at if items else None,
    }


@router.post("/upload", response_model=BankUploadOut)
async def upload_bank_accounts(
    file: UploadFile = File(...),
    file_type: str | None = Form(None),  # از فرانت ارسال می‌شود؛ اینجا لازم نیست
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # همان تابع خواندن فایل پروژه (xls / xlsx / xml / html و محدودیت حجم ۲۰ مگابایت)
    try:
        # keep_text=True: کدها مثل «039» با صفر اول خوانده شوند (نیاز به تغییر کوچک در upload.py)
        df = await read_uploaded_table(file, keep_text=True)
    except TypeError:
        df = await read_uploaded_table(file)
    rows = [list(df.columns)] + df.astype(object).where(df.notna(), None).values.tolist()

    try:
        parsed = await run_in_threadpool(parse_bank_rows, rows)
    except BankParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # این گزارش «وضعیت کامل» بانک‌هاست؛ پس جایگزین داده‌ی قبلی می‌شود (در یک تراکنش)
    await db.execute(delete(BankBalance))
    db.add_all(
        BankBalance(
            detail_code=r.detail_code,
            title=r.title,
            account_number=r.account_number,
            opening_balance=r.opening_balance,
            receipts=r.receipts,
            payments=r.payments,
            balance=r.balance,
            source_file=file.filename,
        )
        for r in parsed
    )
    await db.commit()

    return {"message": "گزارش بانک‌ها بارگذاری شد", "inserted": len(parsed)}
