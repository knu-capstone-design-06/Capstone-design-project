"""backend/.env.example lists every setting the backend reads, and its empty values keep the defaults."""

import os
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from app.common.config.settings import Settings

EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"


class EnvExampleTests(unittest.TestCase):
    def test_every_setting_is_listed(self):
        listed = set(re.findall(r"^([A-Z][A-Z0-9_]*)=", EXAMPLE.read_text(encoding="utf-8"), re.MULTILINE))
        self.assertEqual(listed, {name.upper() for name in Settings.model_fields})

    def test_the_template_leaves_the_demonstration_switch_off(self):
        with patch.dict(os.environ):
            os.environ.pop("DECISION_SEND_SUPPORT", None)
            self.assertFalse(Settings(_env_file=EXAMPLE).decision_send_support)


if __name__ == "__main__":
    unittest.main()
