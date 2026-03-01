import os
import httpx
from typing import Any, Dict, Optional

FOUNDRY_WORKFLOW_URL = (os.getenv("FOUNDRY_WORKFLOW_URL") or "").strip()
FOUNDRY_API_KEY = (os.getenv("FOUNDRY_API_KEY") or "").strip()

class WorkflowCallError(Exception):
   pass

def _must_env(name: str, val: str):
   if not val:
       raise WorkflowCallError(f"Missing env var {name}")

async def run_workflow(user_text: str, conversation_id: Optional[str] = None) -> Dict[str, Any]:
   """
   Calls the published Foundry workflow endpoint.
   Returns parsed JSON response (whatever the workflow returns).
   """
   _must_env("FOUNDRY_WORKFLOW_URL", FOUNDRY_WORKFLOW_URL)
   _must_env("FOUNDRY_API_KEY", FOUNDRY_API_KEY)
   # Keep inputs flexible (workflows ignore extra keys)
   payload: Dict[str, Any] = {
       "inputs": {
           "text": user_text,
           "user_case_details": user_text,
       }
   }
   if conversation_id:
       payload["inputs"]["conversation_id"] = conversation_id
   headers = {
       "Content-Type": "application/json",
       "api-key": FOUNDRY_API_KEY,
   }
   async with httpx.AsyncClient(timeout=60.0) as client:
       resp = await client.post(FOUNDRY_WORKFLOW_URL, json=payload, headers=headers)
   if resp.status_code >= 400:
       raise WorkflowCallError(f"Workflow call failed {resp.status_code}: {resp.text[:2000]}")
   return resp.json()