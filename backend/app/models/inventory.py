from sqlalchemy import Column, Integer, String, Numeric, DateTime, Text
from sqlalchemy.sql import func
from app.core.database import Base


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), nullable=False, index=True)
    title = Column(String(255), nullable=False, index=True)
    quantity = Column(Numeric(18, 3), nullable=False, default=0)
    total_value = Column(Numeric(18, 2), nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())