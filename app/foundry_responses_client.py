import json
import os
from typing import Any, Dict

import httpx
from azure.identity import DefaultAzureCredential

FOUNDRY_SUPERVISOR_RESPONSES_URL = os.getenv(
    "FOUNDRY_SUPERVISOR_RESPONSES_URL", ""
).strip()


class FoundryResponsesError(Exception):
    pass


def _must_env(name: str, value: str):
    if not value:
        raise FoundryResponsesError(f"Missing required env var: {name}")


def _get_bearer_token() -> str:
    credential = DefaultAzureCredential(exclude_interactive_browser_credential=False)
    token = credential.get_token("https://ai.azure.com/.default")
    return token.token


def _extract_json_text(foundry_response: Dict[str, Any]) -> str:
    try:
        output = foundry_response["output"][0]
        content = output["content"][0]
        return (content["text"] or "").strip()
    except Exception as error:
        raise FoundryResponsesError(
            "Unexpected response shape while extracting output_text: "
            f"{error}. Response={json.dumps(foundry_response)[:1200]}"
        ) from error


def call_compliance_supervisor_via_responses(user_text: str) -> Dict[str, Any]:
    """Call the published ComplianceSupervisor and return its JSON case report."""
    _must_env("FOUNDRY_SUPERVISOR_RESPONSES_URL", FOUNDRY_SUPERVISOR_RESPONSES_URL)
    bearer = _get_bearer_token()
    payload = {
        "input": [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": user_text}],
            }
        ]
    }
    headers = {
        "Authorization": f"Bearer {bearer}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=60.0) as client:
        response = client.post(
            FOUNDRY_SUPERVISOR_RESPONSES_URL, headers=headers, json=payload
        )
    if response.status_code >= 400:
        raise FoundryResponsesError(
            f"Supervisor call failed {response.status_code}: {response.text[:2000]}"
        )

    json_text = _extract_json_text(response.json())
    if not json_text.startswith("{"):
        first = json_text.find("{")
        last = json_text.rfind("}")
        if first != -1 and last != -1 and last > first:
            json_text = json_text[first : last + 1]

    try:
        return json.loads(json_text)
    except Exception as error:
        raise FoundryResponsesError(
            "Supervisor did not return valid JSON. "
            f"Error={error}. Content={json_text[:2000]}"
        ) from error

