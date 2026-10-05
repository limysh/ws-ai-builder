import json
import os
from collections import Counter
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session

from .db import get_db
from .foundry_responses_client import (
    FoundryResponsesError,
    call_compliance_supervisor_via_responses,
)
from .models import CaseReport
from .policy import apply_redactions, final_user_message
from .schemas import (
    CaseReportOut,
    CaseRow,
    CasesResponse,
    ChatRequest,
    ChatResponse,
    RedactionItem,
)

router = APIRouter()
STORE_RAW_USER_TEXT = os.getenv("STORE_RAW_USER_TEXT", "false").lower() == "true"
MAX_RAW_TEXT_LEN = int(os.getenv("MAX_RAW_TEXT_LEN", "2000"))


def _safe_get(data: Dict[str, Any], key: str, default):
    value = data.get(key, default)
    return value if value is not None else default


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, db: Session = Depends(get_db)):
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    try:
        case_json = call_compliance_supervisor_via_responses(text)
    except FoundryResponsesError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    reasons = case_json.get("reasons")
    if not isinstance(reasons, list):
        reasons = []
    policy_citations = case_json.get("policy_citations")
    if not isinstance(policy_citations, list):
        policy_citations = []
    questions_for_human = case_json.get("questions_for_human")
    if not isinstance(questions_for_human, list):
        questions_for_human = []
    redactions_raw = case_json.get("redactions")
    if not isinstance(redactions_raw, list):
        redactions_raw = []

    redactions = []
    for redaction in redactions_raw:
        if isinstance(redaction, dict):
            redaction.setdefault("type", "unknown")
            redactions.append(RedactionItem(**redaction))

    case_out = CaseReportOut(
        case_type=str(_safe_get(case_json, "case_type", "")),
        risk_level=str(_safe_get(case_json, "risk_level", "LOW")).upper(),  # type: ignore
        risk_score=float(_safe_get(case_json, "risk_score", 0.0) or 0.0),
        recommended_action=str(
            _safe_get(case_json, "recommended_action", "ALLOW")
        ).upper(),
        reasons=[str(value) for value in reasons if isinstance(value, (str, int, float))],
        policy_citations=policy_citations,
        questions_for_human=[
            str(value)
            for value in questions_for_human
            if isinstance(value, (str, int, float))
        ],
        audit_summary=str(_safe_get(case_json, "audit_summary", "")),
        confidence=float(_safe_get(case_json, "confidence", 0.0) or 0.0),
        redactions=redactions,
    )
    case_out_dict = case_out.model_dump()
    sanitized_content = apply_redactions(text, redactions_raw)
    final_answer = final_user_message(case_json)
    raw_text = text[:MAX_RAW_TEXT_LEN] if STORE_RAW_USER_TEXT else None

    row = CaseReport(
        raw_user_text=raw_text,
        sanitized_content=sanitized_content,
        case_type=case_out.case_type,
        risk_level=case_out.risk_level,
        risk_score=case_out.risk_score,
        recommended_action=str(case_out.recommended_action),
        reasons_json=json.dumps(case_out_dict.get("reasons", []), default=str),
        policy_citations_json=json.dumps(
            case_out_dict.get("policy_citations", []), default=str
        ),
        questions_for_human_json=json.dumps(
            case_out_dict.get("questions_for_human", []), default=str
        ),
        redactions_json=json.dumps(case_out_dict.get("redactions", []), default=str),
        audit_summary=case_out.audit_summary,
        confidence=case_out.confidence,
        case_report_json=json.dumps(case_json, default=str),
    )
    db.add(row)
    db.commit()
    return ChatResponse(
        final_answer=final_answer,
        sanitized_content=sanitized_content,
        case_report=case_out,
    )


@router.get("/cases", response_model=CasesResponse)
def list_cases(limit: int = 50, db: Session = Depends(get_db)):
    limit = max(1, min(limit, 200))
    rows = db.query(CaseReport).order_by(desc(CaseReport.created_at)).limit(limit).all()
    items: List[CaseRow] = []
    for row in rows:
        items.append(
            CaseRow(
                id=row.id,
                created_at=row.created_at.isoformat() if row.created_at else "",
                case_type=row.case_type,
                risk_level=row.risk_level,
                recommended_action=row.recommended_action,
                risk_score=row.risk_score,
                audit_summary=row.audit_summary,
            )
        )
    return CasesResponse(items=items)


@router.get("/kpis")
def kpis(db: Session = Depends(get_db)):
    rows = db.query(CaseReport).all()
    risk_counter = Counter(row.risk_level or "UNKNOWN" for row in rows)
    action_counter = Counter(row.recommended_action or "UNKNOWN" for row in rows)
    reason_counter = Counter()
    for row in rows:
        if not row.reasons_json:
            continue
        try:
            reasons = json.loads(row.reasons_json)
            if isinstance(reasons, list):
                for reason in reasons:
                    if isinstance(reason, str) and reason.strip():
                        reason_counter[reason.strip()] += 1
        except (TypeError, ValueError, json.JSONDecodeError):
            continue

    return {
        "total": len(rows),
        "risk_summary": dict(risk_counter),
        "action_summary": dict(action_counter),
        "top_reasons": [
            {"reason": reason, "count": count}
            for reason, count in reason_counter.most_common(8)
        ],
    }


@router.get("/health")
def health():
    return {"ok": True}

