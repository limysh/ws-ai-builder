from sqlalchemy import Column, DateTime, Float, Integer, String, Text
from sqlalchemy.sql import func

from .db import Base


class CaseReport(Base):
    __tablename__ = "case_reports"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    raw_user_text = Column(Text, nullable=True)
    sanitized_content = Column(Text, nullable=True)
    case_type = Column(String(200), nullable=True)
    risk_level = Column(String(20), nullable=False, default="LOW")
    risk_score = Column(Float, nullable=True)
    recommended_action = Column(String(50), nullable=False, default="ALLOW")
    reasons_json = Column(Text, nullable=True)
    policy_citations_json = Column(Text, nullable=True)
    questions_for_human_json = Column(Text, nullable=True)
    redactions_json = Column(Text, nullable=True)
    audit_summary = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)
    case_report_json = Column(Text, nullable=False)

