import json
import unittest
from unittest.mock import patch

import httpx

from app import foundry_responses_client as foundry


class FoundryTransportTests(unittest.TestCase):
    def invoke(self, responses):
        seen = []
        def handle(request):
            seen.append(request)
            response = responses[min(len(seen) - 1, len(responses) - 1)]
            if isinstance(response, Exception):
                raise response
            return response
        client = httpx.Client(transport=httpx.MockTransport(handle))
        with (
            patch.object(foundry, "FOUNDRY_SUPERVISOR_RESPONSES_URL", "https://example.org/response"),
            patch.object(foundry, "_get_bearer_token", return_value="test"),
            patch.object(foundry.httpx, "Client", return_value=client),
            patch.object(foundry.time, "sleep") as sleep,
        ):
            try:
                value = foundry.call_compliance_supervisor_via_responses("example input")
            except foundry.FoundryResponsesError as error:
                value = str(error)
        return value, seen, sleep.call_args_list

    def ok(self):
        return httpx.Response(200, json={
            "output": [{"content": [{"text": json.dumps({"risk_level": "LOW"})}]}]
        })

    def test_retry_429_preserves_request(self):
        value, seen, sleeps = self.invoke([
            httpx.Response(429, headers={"Retry-After": "0.5"}), self.ok()
        ])
        self.assertEqual(value, {"risk_level": "LOW"})
        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[0].content, seen[1].content)
        self.assertEqual(sleeps[0].args, (0.5,))

    def test_503_has_bounded_retry(self):
        value, seen, sleeps = self.invoke([httpx.Response(503, text="upstream details")])
        self.assertEqual(value, "Supervisor call failed (503)")
        self.assertEqual(len(seen), 2)
        self.assertEqual(sleeps[0].args, (0.25,))

    def test_other_http_errors_are_not_retried(self):
        for status in (400, 500):
            with self.subTest(status=status):
                value, seen, sleeps = self.invoke([httpx.Response(status)])
                self.assertEqual(value, f"Supervisor call failed ({status})")
                self.assertEqual(len(seen), 1)
                self.assertEqual(sleeps, [])

    def test_long_or_invalid_retry_after_is_not_ignored(self):
        for delay in ("60", "nan", "bad", "-1"):
            with self.subTest(delay=delay):
                value, seen, sleeps = self.invoke([
                    httpx.Response(429, headers={"Retry-After": delay})
                ])
                self.assertEqual(value, "Supervisor call failed (429)")
                self.assertEqual(len(seen), 1)
                self.assertEqual(sleeps, [])

    def test_timeout_does_not_retry_or_expose_exception(self):
        value, seen, sleeps = self.invoke([httpx.ReadTimeout("sensitive upstream error")])
        self.assertEqual(value, "Supervisor request failed")
        self.assertEqual(len(seen), 1)
        self.assertEqual(sleeps, [])

    def test_invalid_responses_are_sanitized(self):
        bad = [
            (httpx.Response(200, json={"output": [{"untrusted": "sensitive"}]}),
             "Unexpected supervisor response shape"),
            (httpx.Response(200, content=b"invalid envelope"),
             "Supervisor returned an invalid response"),
            (httpx.Response(200, json={"output": [{"content": [{"text": "sensitive"}]}]}),
             "Supervisor did not return valid JSON"),
        ]
        for response, expected in bad:
            with self.subTest(expected=expected):
                value, seen, _ = self.invoke([response])
                self.assertEqual(value, expected)
                self.assertEqual(len(seen), 1)


if __name__ == "__main__":
    unittest.main()
