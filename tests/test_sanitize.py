from __future__ import annotations

import unittest

from spoon.sanitize import redact_secrets, redact_secrets_in_data, scan_for_secrets


class SanitizeTests(unittest.TestCase):
    def test_redacts_api_key_assignment(self):
        text = "export OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz012345"
        redacted = redact_secrets(text)
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz012345", redacted)
        self.assertIn("[REDACTED", redacted)

    def test_redacts_github_token(self):
        text = "token ghp_abcdefghijklmnopqrstuvwxyz0123456789"
        redacted = redact_secrets(text)
        self.assertNotIn("ghp_abcdefghijklmnopqrstuvwxyz0123456789", redacted)

    def test_scan_finds_secret_families(self):
        text = "Authorization: Bearer super-secret-token-value"
        labels = scan_for_secrets(text)
        self.assertTrue(labels)

    def test_redact_secrets_in_data_nested(self):
        payload = {
            "reason": "api_key=sk-abcdefghijklmnopqrstuvwxyz012345",
            "nested": ["safe", "password=hunter2-extra"],
        }
        redacted = redact_secrets_in_data(payload)
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz012345", str(redacted))
        self.assertNotIn("hunter2-extra", str(redacted))


if __name__ == "__main__":
    unittest.main()
