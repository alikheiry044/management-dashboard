from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BankAccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    detail_code: str
    title: str
    account_number: str | None = None
    opening_balance: int
    receipts: int
    payments: int
    balance: int


class BankTotals(BaseModel):
    count: int
    opening_balance: int
    receipts: int
    payments: int
    balance: int


class BankListOut(BaseModel):
    items: list[BankAccountOut]
    totals: BankTotals
    source_file: str | None = None
    uploaded_at: datetime | None = None


class BankUploadOut(BaseModel):
    message: str
    inserted: int