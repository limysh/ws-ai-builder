import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.foundry_responses_client import FoundryResponsesError
from app.main import create_app
from app.models import CaseReport


class ChatEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.session_factory = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=cls.engine,
        )
        Base.metadata.create_all(bind=cls.engine)

        cls.app = create_app()

        def override_get_db():
            db = cls.session_factory()
            try:
                yield db
            finally:
                db.close()

        cls.app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(cls.app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        cls.app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=cls.engine)
        cls.engine.dispose()

    def setUp(self):
        with self.session_factory() as db:
            db.query(CaseReport).delete()
            db.commit()

    @patch("app.routes.call_compliance_supervisor_via_responses")
    def test_chat_redacts_and_persists_a_normalized_report(self, supervisor):
        supervisor.return_value = {
            "case_type": "account-support",
            "risk_level": "medium",
            "risk_score": 0.72,
            "recommended_action": "require_human",
            "reasons": ["Contains account data"],
            "policy_citations": [{"title": "PII", "doc_id": "POL-7"}],
            "questions_for_human": ["Was identity verified?"],
            "audit_summary": "Manual review required",
            "confidence": 0.91,
            "redactions": [
                {
                    "type": "email",
                    "original": "pat@example.com",
                    "replacement": "[EMAIL]",
                }
            ],
        }

        response = self.client.post(
            "/chat",
            json={"text": "Contact pat@example.com about account 42"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["sanitized_content"], "Contact [EMAIL] about account 42")
        self.assertEqual(body["case_report"]["risk_level"], "MEDIUM")
        self.assertEqual(body["case_report"]["recommended_action"], "REQUIRE_HUMAN")
        self.assertIn("human review", body["final_answer"])

        with self.session_factory() as db:
            row = db.query(CaseReport).one()
            self.assertIsNone(row.raw_user_text)
            self.assertEqual(row.sanitized_content, "Contact [EMAIL] about account 42")
            self.assertEqual(row.risk_level, "MEDIUM")

        kpis = self.client.get("/kpis").json()
        self.assertEqual(kpis["total"], 1)
        self.assertEqual(kpis["risk_summary"], {"MEDIUM": 1})
        self.assertEqual(kpis["top_reasons"], [{"reason": "Contains account data", "count": 1}])

    @patch("app.routes.call_compliance_supervisor_via_responses")
    def test_chat_rejects_empty_input_before_calling_supervisor(self, supervisor):
        response = self.client.post("/chat", json={"text": "   "})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "text is required"})
        supervisor.assert_not_called()

    @patch("app.routes.call_compliance_supervisor_via_responses")
    def test_chat_maps_foundry_failure_to_bad_gateway(self, supervisor):
        supervisor.side_effect = FoundryResponsesError("Foundry timed out")

        response = self.client.post("/chat", json={"text": "Review this request"})

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json(), {"detail": "Foundry timed out"})

    @patch("app.routes.call_compliance_supervisor_via_responses")
    def test_chat_rejects_malformed_supervisor_report_without_persisting(self, supervisor):
        invalid_reports = [
            [],
            {"risk_level": "CRITICAL"},
            {"risk_score": "not-a-number"},
        ]

        for invalid_report in invalid_reports:
            with self.subTest(invalid_report=invalid_report):
                supervisor.return_value = invalid_report
                response = self.client.post("/chat", json={"text": "Review this"})

                self.assertEqual(response.status_code, 502)
                self.assertEqual(
                    response.json(),
                    {"detail": "Supervisor returned an invalid case report"},
                )

        with self.session_factory() as db:
            self.assertEqual(db.query(CaseReport).count(), 0)


if __name__ == "__main__":
    unittest.main()
