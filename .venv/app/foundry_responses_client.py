import os
import json
import httpx
from typing import Any, Dict
from azure.identity import DefaultAzureCredential
FOUNDRY_SUPERVISOR_RESPONSES_URL = os.getenv("FOUNDRY_SUPERVISOR_RESPONSES_URL", "").strip()
class FoundryResponsesError(Exception):
   pass
def _must_env(name: str, val: str):
   if not val:
       raise FoundryResponsesError(f"Missing required env var: {name}")
def _get_bearer_token() -> str:
   # For Foundry APIs, use Entra auth for resource https://ai.azure.com
   cred = DefaultAzureCredential(exclude_interactive_browser_credential=False)
   token = cred.get_token("https://ai.azure.com/.default")
   return token.token
def _extract_json_text(foundry_response: Dict[str, Any]) -> str:
   """
   Foundry Responses API returns:
     output: [
       { type:"message", content:[ {type:"output_text", text:"{...json...}"} ] }
     ]
   """
   try:
       output0 = foundry_response["output"][0]
       content0 = output0["content"][0]
       text = content0["text"]
       return (text or "").strip()
   except Exception as e:
       raise FoundryResponsesError(
           f"Unexpected response shape while extracting output_text: {e}. "
           f"Response={json.dumps(foundry_response)[:1200]}"
       )
def call_compliance_supervisor_via_responses(user_text: str) -> Dict[str, Any]:
   """
   Calls the published ComplianceSupervisor application via Foundry Responses endpoint,
   and returns the parsed JSON case report.
   """
   _must_env("FOUNDRY_SUPERVISOR_RESPONSES_URL", FOUNDRY_SUPERVISOR_RESPONSES_URL)
   bearer = _get_bearer_token()
   payload = {
       "input": [
           {
               "role": "user",
               "content": [
                   {
                       "type": "input_text",
                       "text": user_text
                   }
               ]
           }
       ]
   }
   headers = {
       "Authorization": f"Bearer {bearer}",
       "Content-Type": "application/json",
   }
   with httpx.Client(timeout=60.0) as client:
       resp = client.post(FOUNDRY_SUPERVISOR_RESPONSES_URL, headers=headers, json=payload)
   if resp.status_code >= 400:
       raise FoundryResponsesError(f"Supervisor call failed {resp.status_code}: {resp.text[:2000]}")
   data = resp.json()
   json_text = _extract_json_text(data)
   # Some models might return accidental extra text; extract JSON object if needed.
   if not json_text.startswith("{"):
       first = json_text.find("{")
       last = json_text.rfind("}")
       if first != -1 and last != -1 and last > first:
           json_text = json_text[first:last + 1]
   try:
       return json.loads(json_text)
   except Exception as e:
       raise FoundryResponsesError(
           f"Supervisor did not return valid JSON. Error={e}. Content={json_text[:2000]}"
       )