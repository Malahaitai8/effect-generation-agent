from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from effect_generation_agent.config import load_local_env


class LocalEnvTests(unittest.TestCase):
    def test_loads_file_without_overriding_process_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env.local").write_text(
                "DEEPSEEK_API_KEY=from-file\nDEEPSEEK_MODEL='file-model'\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "from-shell"}, clear=True):
                loaded = load_local_env(root)
                self.assertEqual(os.environ["DEEPSEEK_API_KEY"], "from-shell")
                self.assertEqual(os.environ["DEEPSEEK_MODEL"], "file-model")
                self.assertNotIn("DEEPSEEK_API_KEY", loaded)

    def test_rejects_non_assignment_lines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env.local").write_text("not-an-assignment\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "line 1"):
                load_local_env(root)

