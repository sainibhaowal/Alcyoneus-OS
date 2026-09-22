# Copyright 2026 Alcyoneus Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Unit tests for CLI version consistency and clean root workspace."""

import unittest
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

import alcyoneus
from alcyoneus.cli import _get_version, cli


class TestCLIVersionAndRootHygiene(unittest.TestCase):
    """Ensure dynamic version resolution matches pyproject.toml and root is clean."""

    def test_package_version_exported(self):
        """Ensure alcyoneus.__version__ is exported and matches 1.2.0."""
        self.assertTrue(hasattr(alcyoneus, "__version__"))
        self.assertEqual(alcyoneus.__version__, "1.2.0")

    def test_cli_version_option(self):
        """Ensure CLI --version output dynamically reports 1.2.0."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("1.2.0", result.output)
        self.assertIn("alcyoneus", result.output)

    def test_get_version_fallback(self):
        """Ensure _get_version gracefully falls back to default if metadata missing."""
        with patch(
            "importlib.metadata.version",
            side_effect=ImportError("Package not found"),
        ):
            version = _get_version()
            self.assertEqual(version, "1.2.0")

    def test_stray_root_files_absent(self):
        """Ensure stray files 'file.py' and 'check code.md' are not present in root."""
        root = Path(__file__).resolve().parents[1]
        self.assertFalse(
            (root / "file.py").exists(),
            "file.py should not exist in workspace root",
        )
        self.assertFalse(
            (root / "check code.md").exists(),
            "check code.md should not exist in workspace root",
        )


if __name__ == "__main__":
    unittest.main()
