from pydantic import BaseModel, Field
from typing import Optional, List
from decimal import Decimal
from datetime import datetime
from enum import Enum


# ===== Enums =====
class TransactionType(str, Enum):
    EXPENSE = "expense"
    RECEIVABLE = "receivable"
    PAYABLE = "payable"


class TransactionStatus(str, Enum):
    NORMAL = "normal"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    STOPPED = "stopped"
    SETTLED = "settled"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ApprovalStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class PaymentMethod(str, Enum):
    CASH = "cash"
    CHECK = "check"
    TRANSFER = "transfer"


# ===== Base Schemas =====
class FinanceCreate(BaseModel):
    type: TransactionType
    amount: Decimal = Field(..., gt=0, description="مبلغ تراکنش")
    party_name: Optional[str] = None
    description: Optional[str] = None
    transaction_date: Optional[str] = None
    reference_number: Optional[str] = None
    payment_method: Optional[PaymentMethod] = None

    status: TransactionStatus = TransactionStatus.NORMAL
    risk_level: RiskLevel = RiskLevel.LOW
    risk_score: int = Field(default=0, ge=0, le=100)
    needs_followup: bool = False
    note: Optional[str] = None


class FinanceOut(BaseModel):
    id: int
    type: str
    amount: Decimal
    party_name: Optional[str] = None
    description: Optional[str] = None
    transaction_date: Optional[str] = None
    reference_number: Optional[str] = None
    payment_method: Optional[str] = None

    status: str
    risk_level: str
    risk_score: int

    is_duplicate: bool = False
    has_bank_change: bool = False
    amount_anomaly: bool = False

    requires_approval_from: Optional[str] = None
    approval_status: str = "not_required"
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None

    reviewed_by: Optional[int] = None
    reviewed_at: Optional[datetime] = None

    needs_followup: bool = False
    note: Optional[str] = None

    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class FinanceStatusUpdate(BaseModel):
    status: TransactionStatus
    note: Optional[str] = None
    risk_level: Optional[RiskLevel] = None
    risk_score: Optional[int] = Field(default=None, ge=0, le=100)


class FinanceTransactionUpdate(BaseModel):
    amount: Optional[Decimal] = Field(default=None, gt=0)
    party_name: Optional[str] = None
    description: Optional[str] = None
    transaction_date: Optional[str] = None
    reference_number: Optional[str] = None
    payment_method: Optional[PaymentMethod] = None
    status: Optional[TransactionStatus] = None
    risk_level: Optional[RiskLevel] = None
    risk_score: Optional[int] = Field(default=None, ge=0, le=100)
    needs_followup: Optional[bool] = None
    note: Optional[str] = None


class FinanceApproval(BaseModel):
    approval_status: ApprovalStatus
    note: Optional[str] = None


class ReviewQueueItem(BaseModel):
    id: int
    type: str
    amount: Decimal
    party_name: Optional[str] = None
    description: Optional[str] = None
    transaction_date: Optional[str] = None
    reference_number: Optional[str] = None

    risk_level: str
    risk_score: int
    is_duplicate: bool
    has_bank_change: bool
    amount_anomaly: bool

    status: str
    requires_approval_from: Optional[str] = None

    note: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class RiskAssessment(BaseModel):
    transaction_id: int
    risk_score: int
    risk_level: RiskLevel
    factors: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)


class FinanceSummary(BaseModel):
    total_transactions: int
    total_amount: Decimal
    pending_review: int
    high_risk: int
    stopped: int
    approved: int
    settled: int


class RiskOverview(BaseModel):
    low_risk_count: int
    medium_risk_count: int
    high_risk_count: int
    average_risk_score: float
    total_at_risk_amount: Decimal


class FinanceListResponse(BaseModel):
    items: List[FinanceOut]
    total: int
    page: int
    page_size: int
    total_pages: int

