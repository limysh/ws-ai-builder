from typing import Any, Dict, List


def apply_redactions(original_text: str, redactions: List[Dict[str, Any]]) -> str:
    """Apply supervisor-provided redactions before text is persisted or returned."""
    if not redactions:
        return original_text[:500]

    sanitized = original_text
    for redaction in redactions:
        original = redaction.get("original")
        replacement = redaction.get("replacement") or "[REDACTED]"
        if isinstance(original, str) and original.strip():
            sanitized = sanitized.replace(original, replacement)
    return sanitized[:1000]


def final_user_message(case_json: Dict[str, Any]) -> str:
    """Return a deterministic, policy-safe message for a supervisor decision."""
    action = str(case_json.get("recommended_action", "ALLOW")).upper()
    risk = str(case_json.get("risk_level", "LOW")).upper()

    if action == "ESCALATE":
        return (
            "I can’t help with that request. It requires escalation to a human "
            "compliance team."
        )
    if action in ("REQUIRE_HUMAN", "REVIEW"):
        return (
            f"This request is {risk} risk and requires human review. "
            "Please proceed through an approved support channel."
        )
    return "Allowed. Here’s the information at a high level (no sensitive data processed)."

