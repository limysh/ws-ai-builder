import os
from typing import Any, Dict, Optional

import httpx

FOUNDRY_WORKFLOW_URL = (os.getenv("FOUNDRY_WORKFLOW_URL") or "").strip()
FOUNDRY_API_KEY = (os.getenv("FOUNDRY_API_KEY") or "").strip()


class WorkflowCallError(Exception):
    pass


def _must_env(name: str, value: str):
    if not value:
        raise WorkflowCallError(f"Missing env var {name}")


async def run_workflow(
    user_text: str, conversation_id: Optional[str] = None
) -> Dict[str, Any]:
    """Call the published Foundry workflow endpoint and return its JSON response."""
    _must_env("FOUNDRY_WORKFLOW_URL", FOUNDRY_WORKFLOW_URL)
    _must_env("FOUNDRY_API_KEY", FOUNDRY_API_KEY)

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
        response = await client.post(FOUNDRY_WORKFLOW_URL, json=payload, headers=headers)
    if response.status_code >= 400:
        raise WorkflowCallError(
            f"Workflow call failed {response.status_code}: {response.text[:2000]}"
        )
    return response.json()

