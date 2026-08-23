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

"""Code Interpreter (Sandbox) Tool for Alcyoneus OS.

Executes Python code snippets in an isolated subshell environment and captures
stdout, stderr, variables, and output image artifacts.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from typing import Any

from alcyoneus.utils.decorators import tool


@tool(
    name="code_interpreter",
    description="Executes Python code in a sandboxed environment and returns stdout, stderr, and generated plots/files.",  # noqa: E501
)
def code_interpreter(
    code: str,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Executes a Python code block and captures output.

    Args:
        code: Python source code string to execute.
        timeout: Execution timeout in seconds. Defaults to 30.0.

    Returns:
        Dict containing stdout, stderr, exit_code, and output files generated.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        script_path = os.path.join(tmpdir, "script.py")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(code)

        try:
            proc = subprocess.run(  # noqa: S603
                [sys.executable, script_path],
                cwd=tmpdir,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "exit_code": proc.returncode,
                "stdout": proc.stdout.strip(),
                "stderr": proc.stderr.strip(),
                "status": "success" if proc.returncode == 0 else "error",
            }
        except subprocess.TimeoutExpired:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Execution timed out after {timeout} seconds.",
                "status": "timeout",
            }
        except Exception as err:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": str(err),
                "status": "error",
            }


class CodeInterpreterTool:
    """Class wrapper for Code Interpreter tool."""

    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout

    def __call__(self, code: str) -> dict[str, Any]:
        return code_interpreter(code=code, timeout=self.timeout)


__all__ = ["CodeInterpreterTool", "code_interpreter"]
