import json
import os
import time
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
    except (KeyError, IndexError, TypeError, AttributeError) as error:
        raise FoundryResponsesError("Unexpected supervisor response shape") from error


def _retry_delay(response: httpx.Response) -> float | None:
    """Respect short Retry-After delays; never block a request for long periods."""
    retry_after = response.headers.get("Retry-After")
    if retry_after is None:
        return 0.25
    try:
        delay = float(retry_after)
    except ValueError:
        return None
    return delay if 0 <= delay <= 2 else None


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

    try:
        with httpx.Client(
            timeout=httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0)
        ) as client:
            for attempt in range(2):
                response = client.post(
                    FOUNDRY_SUPERVISOR_RESPONSES_URL, headers=headers, json=payload
                )
                # Only retry throttling/unavailability; other failures may have run the model.
                if response.status_code in (429, 503) and attempt == 0:
                    delay = _retry_delay(response)
                    if delay is not None:
                        time.sleep(delay)
                        continue
                break
    except httpx.RequestError as error:
        # Upstream exception details can contain request text or credentials.
        raise FoundryResponsesError("Supervisor request failed") from error

    if response.status_code >= 400:
        raise FoundryResponsesError(
            f"Supervisor call failed ({response.status_code})"
        )

    try:
        json_text = _extract_json_text(response.json())
    except ValueError as error:
        raise FoundryResponsesError("Supervisor returned an invalid response") from error
    if not json_text.startswith("{"):
        first = json_text.find("{")
        last = json_text.rfind("}")
        if first != -1 and last != -1 and last > first:
            json_text = json_text[first : last + 1]

    try:
        return json.loads(json_text)
    except (TypeError, ValueError) as error:
        raise FoundryResponsesError("Supervisor did not return valid JSON") from error
