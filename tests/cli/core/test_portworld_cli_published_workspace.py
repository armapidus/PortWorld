from __future__ import annotations

import unittest

from portworld_cli.workspace.published import load_published_env_template


class PublishedWorkspaceTests(unittest.TestCase):
    def test_load_published_env_template_exposes_expected_keys(self) -> None:
        template = load_published_env_template()

        self.assertIn("PORT", template.ordered_keys)
        self.assertIn("BACKEND_BEARER_TOKEN", template.ordered_keys)


if __name__ == "__main__":
    unittest.main()
