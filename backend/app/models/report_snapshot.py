from sqlalchemy import Column, Integer, String, Numeric, DateTime
from sqlalchemy.sql import func
from app.core.database import Base


class ReportSnapshot(Base):
    """One row per successful upload: keeps history even though uploads replace the data."""
    __tablename__ = "report_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    report_type = Column(String(50), nullable=False, index=True)  # sales | receivables | payables | expense | inventory
    total_amount = Column(Numeric(20, 2), nullable=True)           # sum of amounts in this upload (None for inventory)
    row_count = Column(Integer, nullable=False)
    mode = Column(String(30), nullable=True)                       # replace | append | skip_duplicates
    filename = Column(String(255), nullable=True)
    uploaded_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)