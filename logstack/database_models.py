from sqlalchemy import UUID, Column, DateTime, Integer, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Flamechart(Base):
    __tablename__ = "flamechart"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, index=True, nullable=False)
    upload_uuid = Column(UUID, index=True, nullable=False)
    prefix = Column(String, index=True, nullable=False)
    error_count = Column(Integer, nullable=False)

    from_date = Column(DateTime, index=True, nullable=False)
    to_date = Column(DateTime, index=True, nullable=False)
    created_at = Column(DateTime, index=True, nullable=False)
