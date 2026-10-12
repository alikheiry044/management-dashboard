from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.api.upload import MAX_UPLOAD_BYTES, read_uploaded_table
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.party_balance import PartyBalance
from app.models.user import User
from app.schemas.party_balance import PartyListOut, PartyUploadOut
from app.services.party_parser import PartyParseError, parse_party_rows, sniff_period

router = APIRouter(prefix="/party-balances", tags=["Party balances"])


@router.get("/", response_model=PartyListOut)
async def list_party_balances(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(PartyBalance).order_by(PartyBalance.balance.desc()))
    items = result.scalars().all()

    receivable = [i.balance for i in items if i.balance > 0]
    payable = [i.balance for i in items if i.balance < 0]

    return {
        "items": items,
        "totals": {
            "count": len(items),
            "receivable_count": len(receivable),
            "payable_count": len(payable),
            "receivable_total": sum(receivable),
            "payable_total": sum(payable),
            "net": sum(receivable) + sum(payable),
        },
        "period_label": items[0].period_label if items else None,
        "source_file": items[0].source_file if items else None,
        "uploaded_at": items[0].uploaded_at if items else None,
    }


@router.post("/upload", response_model=PartyUploadOut)
async def upload_party_balances(
    file: UploadFile = File(...),
    file_type: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="حجم فایل بیشتر از ۲۰ مگابایت است")
    period = sniff_period(content)
    await file.seek(0)

    try:
        # keep_text=True: کدها با صفر اول خوانده شوند (نیاز به تغییر کوچک در upload.py)
        df = await read_uploaded_table(file, keep_text=True)
    except TypeError:
        df = await read_uploaded_table(file)
    rows = [list(df.columns)] + df.astype(object).where(df.notna(), None).values.tolist()

    try:
        parsed = await run_in_threadpool(parse_party_rows, rows)
    except PartyParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # گزارش «وضعیت کامل» است؛ پس جایگزین مانده‌ی قبلی می‌شود (در یک تراکنش)
    await db.execute(delete(PartyBalance))
    db.add_all(
        PartyBalance(
            detail_code=r.detail_code,
            title=r.title,
            balance=r.balance,
            period_label=period,
            source_file=file.filename,
        )
        for r in parsed.rows
    )
    await db.commit()

    return {
        "message": "مانده‌ی مشتریان بارگذاری شد",
        "inserted": len(parsed.rows),
        "skipped_zero": parsed.skipped_zero,
        "total_matches": parsed.total_matches,
        "period_label": period,
    }