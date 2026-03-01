from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field
RiskLevel = Literal["LOW", "MEDIUM", "HIGH"]
RecommendedAction = Literal["ALLOW", "REQUIRE_HUMAN", "ESCALATE", "REVIEW"]
class PolicyCitation(BaseModel):
   title: str
   doc_id: str
class RedactionItem(BaseModel):
   type: str
   original: Optional[str] = None
   replacement: Optional[str] = None
class CaseReportOut(BaseModel):
   case_type: str = ""
   risk_level: RiskLevel = "LOW"
   risk_score: float = 0.0
   recommended_action: Union[RecommendedAction, str] = "ALLOW"
   reasons: List[str] = Field(default_factory=list)
   policy_citations: List[PolicyCitation] = Field(default_factory=list)
   questions_for_human: List[str] = Field(default_factory=list)
   audit_summary: str = ""
   confidence: float = 0.0
   redactions: List[RedactionItem] = Field(default_factory=list)
class ChatRequest(BaseModel):
   text: str
   user_id: Optional[str] = None
   session_id: Optional[str] = None
class ChatResponse(BaseModel):
   final_answer: str
   sanitized_content: str
   case_report: CaseReportOut
class CaseRow(BaseModel):
   id: int
   created_at: str
   case_type: Optional[str] = None
   risk_level: str
   recommended_action: str
   risk_score: Optional[float] = None
   audit_summary: Optional[str] = None
class CasesResponse(BaseModel):
   items: List[CaseRow]
class KPIsResponse(BaseModel):
   total: int
   risk_summary: Dict[str, int]
   action_summary: Dict[str, int]
   top_reasons: List[Dict[str, Union[str, int]]]