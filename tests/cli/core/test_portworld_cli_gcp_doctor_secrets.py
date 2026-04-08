from __future__ import annotations

import unittest

from portworld_cli.gcp.doctor import _build_secret_checks, _build_secret_readiness


class GCPDoctorSecretReadinessTests(unittest.TestCase):
    def test_openclaw_token_is_required_secret_when_enabled(self) -> None:
        readiness = _build_secret_readiness(
            {
                "REALTIME_PROVIDER": "openai",
                "OPENAI_API_KEY": "openai-key",
                "REALTIME_TOOLING_ENABLED": "true",
                "OPENCLAW_ENABLED": "true",
                "OPENCLAW_BASE_URL": "https://portworld.duckdns.org",
            }
        )

        self.assertIn("OPENCLAW_AUTH_TOKEN", readiness.required_secret_keys)
        self.assertIn("OPENCLAW_AUTH_TOKEN", readiness.missing_required_secret_keys)
        self.assertFalse(readiness.key_presence["OPENCLAW_AUTH_TOKEN"])

        checks = {check.id: check for check in _build_secret_checks(secrets=readiness)}
        self.assertEqual(checks["provider_secret_openclaw_auth_token"].status, "fail")

    def test_openclaw_token_is_secret_ready_when_present(self) -> None:
        readiness = _build_secret_readiness(
            {
                "REALTIME_PROVIDER": "openai",
                "OPENAI_API_KEY": "openai-key",
                "REALTIME_TOOLING_ENABLED": "true",
                "OPENCLAW_ENABLED": "true",
                "OPENCLAW_BASE_URL": "https://portworld.duckdns.org",
                "OPENCLAW_AUTH_TOKEN": "secret-token",
            }
        )

        self.assertIn("OPENCLAW_AUTH_TOKEN", readiness.required_secret_keys)
        self.assertNotIn("OPENCLAW_AUTH_TOKEN", readiness.missing_required_secret_keys)
        self.assertTrue(readiness.key_presence["OPENCLAW_AUTH_TOKEN"])

        checks = {check.id: check for check in _build_secret_checks(secrets=readiness)}
        self.assertEqual(checks["provider_secret_openclaw_auth_token"].status, "pass")


if __name__ == "__main__":
    unittest.main()
