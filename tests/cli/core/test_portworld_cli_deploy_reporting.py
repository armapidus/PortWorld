from __future__ import annotations

import unittest

from portworld_cli.deploy.reporting import build_failure_result


class DeployReportingFailureMessageTests(unittest.TestCase):
    def test_build_failure_result_includes_problem_and_next(self) -> None:
        result = build_failure_result(
            stage="cloud_build",
            exc=RuntimeError("Cloud Build submission failed."),
            stage_records=[],
            resources={},
            action="Inspect Cloud Build logs and rerun deploy.",
            error_type="RuntimeError",
        )
        self.assertFalse(result.ok)
        self.assertIn("stage: cloud_build", result.message or "")
        self.assertIn("problem: Cloud Build submission failed.", result.message or "")
        self.assertIn("next: Inspect Cloud Build logs and rerun deploy.", result.message or "")

    def test_build_failure_result_uses_default_next_when_missing(self) -> None:
        result = build_failure_result(
            stage="parameter_resolution",
            exc=RuntimeError("Missing project id."),
            stage_records=[],
            resources={},
            action=None,
            error_type="RuntimeError",
            exit_code=2,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.exit_code, 2)
        self.assertIn("problem: Missing project id.", result.message or "")
        self.assertIn("next: Inspect the stage details in output and rerun deploy.", result.message or "")


if __name__ == "__main__":
    unittest.main()
