import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import DEFAULT_ALLOWED_ORIGINS, create_app, parse_allowed_origins


class AllowedOriginsTests(unittest.TestCase):
    def test_defaults_to_local_frontends(self):
        self.assertEqual(parse_allowed_origins(None), list(DEFAULT_ALLOWED_ORIGINS))

    def test_normalizes_and_deduplicates_configured_origins(self):
        origins = parse_allowed_origins(
            " https://app.example.com/,https://admin.example.com,"
            "https://app.example.com "
        )

        self.assertEqual(
            origins,
            ["https://app.example.com", "https://admin.example.com"],
        )

    def test_rejects_unsafe_or_malformed_origins(self):
        invalid_values = [
            "*",
            "https://*.example.com",
            "ftp://app.example.com",
            "https://app.example.com/path",
            "https://user:password@app.example.com",
            "https://app.example.com:invalid",
        ]

        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_allowed_origins(value)


class CorsMiddlewareTests(unittest.TestCase):
    def test_preflight_allows_only_configured_origin(self):
        with patch.dict(
            os.environ,
            {"ALLOWED_ORIGINS": "https://app.example.com"},
        ):
            app = create_app()

        with TestClient(app) as client:
            allowed = client.options(
                "/chat",
                headers={
                    "Origin": "https://app.example.com",
                    "Access-Control-Request-Method": "POST",
                },
            )
            blocked = client.options(
                "/chat",
                headers={
                    "Origin": "https://attacker.example",
                    "Access-Control-Request-Method": "POST",
                },
            )

        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(
            allowed.headers["access-control-allow-origin"],
            "https://app.example.com",
        )
        self.assertEqual(blocked.status_code, 400)
        self.assertNotIn("access-control-allow-origin", blocked.headers)


if __name__ == "__main__":
    unittest.main()
