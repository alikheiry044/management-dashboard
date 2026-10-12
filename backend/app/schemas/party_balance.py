from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PartyBalanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    detail_code: str
    title: str
    balance: int


class PartyTotals(BaseModel):
    count: int
    receivable_count: int
    payable_count: int
    receivable_total: int   # جمع مانده‌های مثبت
    payable_total: int      # جمع مانده‌های منفی (عدد منفی)
    net: int


class PartyListOut(BaseModel):
    items: list[PartyBalanceOut]
    totals: PartyTotals
    period_label: str | None = None
    source_file: str | None = None
    uploaded_at: datetime | None = None


class PartyUploadOut(BaseModel):
    message: str
    inserted: int
    skipped_zero: int
    total_matches: bool
    period_label: str | None = None
    