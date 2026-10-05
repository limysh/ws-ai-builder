import unittest

from app.policy import apply_redactions, final_user_message


class ApplyRedactionsTests(unittest.TestCase):
    def test_replaces_every_occurrence_with_supplied_value(self):
        text = "Contact Pat at pat@example.com; repeat pat@example.com."

        result = apply_redactions(
            text,
            [
                {
                    "type": "email",
                    "original": "pat@example.com",
                    "replacement": "[EMAIL]",
                }
            ],
        )

        self.assertEqual(result, "Contact Pat at [EMAIL]; repeat [EMAIL].")

    def test_uses_safe_default_and_ignores_empty_originals(self):
        result = apply_redactions(
            "Account 1234 remains visible",
            [
                {"type": "account", "original": "1234"},
                {"type": "empty", "original": "   ", "replacement": "bad"},
            ],
        )

        self.assertEqual(result, "Account [REDACTED] remains visible")

    def test_caps_unredacted_text(self):
        self.assertEqual(len(apply_redactions("x" * 800, [])), 500)


class FinalUserMessageTests(unittest.TestCase):
    def test_escalation_message(self):
        message = final_user_message({"recommended_action": "escalate"})
        self.assertIn("escalation", message)

    def test_human_review_includes_normalized_risk(self):
        message = final_user_message(
            {"recommended_action": "require_human", "risk_level": "high"}
        )
        self.assertIn("HIGH risk", message)
        self.assertIn("human review", message)

    def test_allow_is_the_safe_default(self):
        self.assertTrue(final_user_message({}).startswith("Allowed."))


if __name__ == "__main__":
    unittest.main()

