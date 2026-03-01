import os
import json
from collections import Counter
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from .db import get_db
from .models import CaseReport
from .schemas import (
   ChatRequest,
   ChatResponse,
   CaseReportOut,
   CasesResponse,
   CaseRow,
   RedactionItem,
)
from .foundry_responses_client import (
   call_compliance_supervisor_via_responses,
   FoundryResponsesError,
)
router = APIRouter()
STORE_RAW_USER_TEXT = os.getenv("STORE_RAW_USER_TEXT", "false").lower() == "true"
MAX_RAW_TEXT_LEN = int(os.getenv("MAX_RAW_TEXT_LEN", "2000"))
def _safe_get(d: Dict[str, Any], key: str, default):
   v = d.get(key, default)
   return v if v is not None else default
def _apply_redactions(original_text: str, redactions: List[Dict[str, Any]]) -> str:
   if not redactions:
       return original_text[:500]
   sanitized = original_text
   for r in redactions:
       orig = r.get("original")
       repl = r.get("replacement") or "[REDACTED]"
       if isinstance(orig, str) and orig.strip():
           sanitized = sanitized.replace(orig, repl)
   return sanitized[:1000]
def _final_user_message(case_json: Dict[str, Any]) -> str:
   action = str(case_json.get("recommended_action", "ALLOW")).upper()
   risk = str(case_json.get("risk_level", "LOW")).upper()
   if action == "ESCALATE":
       return "I can’t help with that request. It requires escalation to a human compliance team."
   if action in ("REQUIRE_HUMAN", "REVIEW"):
       return f"This request is {risk} risk and requires human review. Please proceed through an approved support channel."
   return "Allowed. Here’s the information at a high level (no sensitive data processed)."
@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, db: Session = Depends(get_db)):
   text = (req.text or "").strip()
   if not text:
       raise HTTPException(status_code=400, detail="text is required")
   try:
       case_json = call_compliance_supervisor_via_responses(text)
   except FoundryResponsesError as e:
       raise HTTPException(status_code=502, detail=str(e))
   # normalize lists
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
   # Convert redactions into Pydantic objects for response model
   redactions_objs: List[RedactionItem] = []
   for r in redactions_raw:
       if isinstance(r, dict):
           # Ensure the 'type' field is present, default to 'unknown' if missing
           r.setdefault("type", "unknown")
           # tolerate different keys if your workflow varies
           # expects: type, original, replacement
           redactions_objs.append(RedactionItem(**r))
   case_out = CaseReportOut(
       case_type=str(_safe_get(case_json, "case_type", "")),
       risk_level=str(_safe_get(case_json, "risk_level", "LOW")).upper(),  # type: ignore
       risk_score=float(_safe_get(case_json, "risk_score", 0.0) or 0.0),
       recommended_action=str(_safe_get(case_json, "recommended_action", "ALLOW")).upper(),
       reasons=[str(x) for x in reasons if isinstance(x, (str, int, float))],
       policy_citations=policy_citations,
       questions_for_human=[str(x) for x in questions_for_human if isinstance(x, (str, int, float))],
       audit_summary=str(_safe_get(case_json, "audit_summary", "")),
       confidence=float(_safe_get(case_json, "confidence", 0.0) or 0.0),
       redactions=redactions_objs,
   )
   # IMPORTANT: when persisting to DB, serialize using model_dump()
   case_out_dict = case_out.model_dump()
   sanitized_content = _apply_redactions(text, redactions_raw)
   final_answer = _final_user_message(case_json)
   raw_text = text[:MAX_RAW_TEXT_LEN] if STORE_RAW_USER_TEXT else None
   row = CaseReport(
       raw_user_text=raw_text,
       sanitized_content=sanitized_content,
       case_type=case_out.case_type,
       risk_level=case_out.risk_level,
       risk_score=case_out.risk_score,
       recommended_action=str(case_out.recommended_action),
       reasons_json=json.dumps(case_out_dict.get("reasons", []), default=str),
       policy_citations_json=json.dumps(case_out_dict.get("policy_citations", []), default=str),
       questions_for_human_json=json.dumps(case_out_dict.get("questions_for_human", []), default=str),
       # FIX: dump redactions as plain dicts
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
   for r in rows:
       items.append(
           CaseRow(
               id=r.id,
               created_at=r.created_at.isoformat() if r.created_at else "",
               case_type=r.case_type,
               risk_level=r.risk_level,
               recommended_action=r.recommended_action,
               risk_score=r.risk_score,
               audit_summary=r.audit_summary,
           )
       )
   return CasesResponse(items=items)
@router.get("/kpis")
def kpis(db: Session = Depends(get_db)):
   rows = db.query(CaseReport).all()
   total = len(rows)
   risk_counter = Counter([r.risk_level or "UNKNOWN" for r in rows])
   action_counter = Counter([r.recommended_action or "UNKNOWN" for r in rows])
   reason_counter = Counter()
   for r in rows:
       if not r.reasons_json:
           continue
       try:
           reasons = json.loads(r.reasons_json)
           if isinstance(reasons, list):
               for x in reasons:
                   if isinstance(x, str) and x.strip():
                       reason_counter[x.strip()] += 1
       except Exception:
           continue
   top_reasons = [{"reason": k, "count": v} for k, v in reason_counter.most_common(8)]
   return {
       "total": total,
       "risk_summary": dict(risk_counter),
       "action_summary": dict(action_counter),
       "top_reasons": top_reasons,
   }
@router.get("/health")
def health():
   return {"ok": True}
