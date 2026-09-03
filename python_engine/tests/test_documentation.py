from __future__ import annotations

import unittest
from pathlib import Path


class DocumentationTest(unittest.TestCase):
    def test_source_audit_exists_and_marks_uncertainty(self) -> None:
        audit_path = Path(__file__).parents[2] / "docs" / "SOURCE_AUDIT.md"
        content = audit_path.read_text(encoding="utf-8")

        self.assertIn("Mercado Publico", content)
        self.assertIn("TO_VERIFY", content)
        self.assertIn("MANUAL", content)


if __name__ == "__main__":
    unittest.main()
