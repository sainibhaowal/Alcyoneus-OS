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

"""Comprehensive tests for Alcyoneus CLI enhancements (Pillar 2).

Tests:
- alcyoneus version (--json, --yaml)
- alcyoneus doctor (Rich table, --json, --yaml)
- alcyoneus init (scaffolding all agent types, storages, providers)
- alcyoneus completion (--shell bash/zsh/fish)
- alcyoneus agent list (--json, --yaml)
- alcyoneus tool list (--json, --yaml)
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from click.testing import CliRunner

from alcyoneus.cli import cli
from alcyoneus.cli.doctor import (
    check_api_credentials,
    check_dependencies,
    check_docker_daemon,
    check_pty_subsystem,
    check_python_environment,
    run_diagnostics,
)
from alcyoneus.cli.scaffold import scaffold_project


@pytest.fixture
def runner():
    """Click CLI test runner fixture."""
    return CliRunner()


class TestCLIVersionCommands:
    """Test alcyoneus version command and machine-readable output flags."""

    def test_version_plain(self, runner):
        result = runner.invoke(cli, ["version"])
        assert result.exit_code == 0
        assert "Alcyoneus OS version" in result.output
        assert "1.1.0" in result.output

    def test_version_json(self, runner):
        result = runner.invoke(cli, ["version", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["name"] == "alcyoneus"
        assert data["version"] == "1.1.0"
        assert "platform" in data

    def test_version_yaml(self, runner):
        result = runner.invoke(cli, ["version", "--yaml"])
        assert result.exit_code == 0
        data = yaml.safe_load(result.output)
        assert data["name"] == "alcyoneus"
        assert data["version"] == "1.1.0"


class TestCLIDoctorDiagnostics:
    """Test alcyoneus doctor diagnostics suite."""

    def test_doctor_command_plain(self, runner):
        result = runner.invoke(cli, ["doctor"])
        assert result.exit_code == 0
        assert "System Health & Diagnostics" in result.output
        assert "Core Runtime Environment" in result.output
        assert "Python Version" in result.output

    def test_doctor_command_json(self, runner):
        result = runner.invoke(cli, ["doctor", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "python" in data
        assert "docker" in data
        assert "pty" in data
        assert "dependencies" in data
        assert "credentials" in data
        assert data["python"]["status"] in ("PASS", "FAIL")

    def test_doctor_command_yaml(self, runner):
        result = runner.invoke(cli, ["doctor", "--yaml"])
        assert result.exit_code == 0
        data = yaml.safe_load(result.output)
        assert "python" in data
        assert "dependencies" in data

    def test_diagnostic_check_functions(self):
        py_info = check_python_environment()
        assert py_info["name"] == "Python Version"
        assert py_info["status"] == "PASS"

        pty_info = check_pty_subsystem()
        assert pty_info["name"] == "PTY Subsystem"

        docker_info = check_docker_daemon()
        assert "status" in docker_info

        deps = check_dependencies()
        assert len(deps) >= 10
        pkg_names = [d["package"] for d in deps]
        assert "google-genai" in pkg_names
        assert "openai" in pkg_names

        creds = check_api_credentials()
        assert len(creds) >= 4
        var_names = [c["variable"] for c in creds]
        assert "OPENAI_API_KEY" in var_names
        assert "GEMINI_API_KEY" in var_names

    def test_run_diagnostics_aggregation(self):
        data = run_diagnostics()
        assert set(data.keys()) == {"python", "docker", "pty", "dependencies", "credentials"}


class TestCLIScaffoldAndInit:
    """Test alcyoneus init and project scaffolding."""

    @pytest.mark.parametrize("agent_type", ["react", "plan-act-reflect", "rag", "swarm", "supervisor"])
    @pytest.mark.parametrize("storage", ["memory", "sqlite", "postgres", "qdrant"])
    def test_scaffold_project_combinations(self, agent_type, storage):
        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = Path(tmpdir) / "test_proj"
            created = scaffold_project(
                target_dir=target_dir,
                project_name="test_proj",
                agent_type=agent_type,
                storage=storage,
                llm_provider="openai",
            )
            assert len(created) == 5

            # Verify files exist and have non-empty content
            agent_file = target_dir / "agent.py"
            pyproject_file = target_dir / "pyproject.toml"
            env_file = target_dir / ".env.example"
            test_file = target_dir / "tests" / "test_agent.py"
            readme_file = target_dir / "README.md"

            assert agent_file.exists() and len(agent_file.read_text()) > 50
            assert pyproject_file.exists() and "test_proj" in pyproject_file.read_text()
            assert env_file.exists() and "OPENAI_API_KEY" in env_file.read_text()
            assert test_file.exists() and "test_agent_creation" in test_file.read_text()
            assert readme_file.exists() and agent_type in readme_file.read_text()

    def test_cli_init_non_interactive(self, runner):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = str(Path(tmpdir) / "custom_agent")
            result = runner.invoke(
                cli,
                [
                    "init",
                    "custom_agent",
                    "--agent-type",
                    "react",
                    "--storage",
                    "memory",
                    "--llm-provider",
                    "gemini",
                    "--output",
                    out_path,
                ],
            )
            assert result.exit_code == 0
            assert "successfully created" in result.output
            assert (Path(out_path) / "agent.py").exists()


class TestCLICompletion:
    """Test shell tab auto-completion command."""

    def test_completion_bash_print(self, runner):
        result = runner.invoke(cli, ["completion", "--shell", "bash"])
        assert result.exit_code == 0
        assert "_ALCYONEUS_COMPLETE=bash_source" in result.output

    def test_completion_zsh_print(self, runner):
        result = runner.invoke(cli, ["completion", "--shell", "zsh"])
        assert result.exit_code == 0
        assert "_ALCYONEUS_COMPLETE=zsh_source" in result.output

    def test_completion_fish_print(self, runner):
        result = runner.invoke(cli, ["completion", "--shell", "fish"])
        assert result.exit_code == 0
        assert "_ALCYONEUS_COMPLETE=fish_source" in result.output

    def test_completion_install_mock(self, runner):
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_home = Path(tmpdir)
            fake_bashrc = fake_home / ".bashrc"
            fake_bashrc.write_text("# existing bashrc\n")

            with patch("pathlib.Path.home", return_value=fake_home):
                result = runner.invoke(cli, ["completion", "--shell", "bash", "--install"])
                assert result.exit_code == 0
                assert "Installed bash auto-completion" in result.output
                assert "_ALCYONEUS_COMPLETE=bash_source" in fake_bashrc.read_text()


class TestCLIMachineReadableOutputs:
    """Test --json and --yaml options on agent list and tool list."""

    def test_agent_list_json(self, runner):
        result = runner.invoke(cli, ["agent", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        types = [item["type"] for item in data]
        assert "react" in types
        assert "rag" in types
        assert "swarm" in types

    def test_agent_list_yaml(self, runner):
        result = runner.invoke(cli, ["agent", "list", "--yaml"])
        assert result.exit_code == 0
        data = yaml.safe_load(result.output)
        assert isinstance(data, list)
        assert len(data) >= 5

    def test_tool_list_json(self, runner):
        result = runner.invoke(cli, ["tool", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        names = [item["name"] for item in data]
        assert "calculator" in names
        assert "web_search" in names

    def test_tool_list_yaml(self, runner):
        result = runner.invoke(cli, ["tool", "list", "--yaml"])
        assert result.exit_code == 0
        data = yaml.safe_load(result.output)
        assert isinstance(data, list)
        assert len(data) >= 8


class TestCLIGraphInspect:
    """Test alcyoneus graph inspect with --json and --yaml flags."""

    def test_graph_inspect_json_and_yaml(self, runner):
        with tempfile.TemporaryDirectory() as tmpdir:
            graph_code = '''
from alcyoneus.core.graph import StateGraph
from alcyoneus.utils import START, END

def dummy_node(state):
    return state

builder = StateGraph()
builder.add_node("step1", dummy_node)
builder.add_edge(START, "step1")
builder.add_edge("step1", END)
graph = builder.compile()
'''
            graph_path = Path(tmpdir) / "sample_graph.py"
            graph_path.write_text(graph_code)

            # Plain text inspect
            res = runner.invoke(cli, ["graph", "inspect", str(graph_path)])
            assert res.exit_code == 0
            assert "Graph Inspection" in res.output
            assert "step1" in res.output

            # JSON inspect
            res_json = runner.invoke(cli, ["graph", "inspect", str(graph_path), "--json"])
            assert res_json.exit_code == 0
            data = json.loads(res_json.output)
            assert data["type"] == "CompiledGraph"
            assert "step1" in data["nodes"]
            assert data["node_count"] >= 1

            # YAML inspect
            res_yaml = runner.invoke(cli, ["graph", "inspect", str(graph_path), "--yaml"])
            assert res_yaml.exit_code == 0
            ydata = yaml.safe_load(res_yaml.output)
            assert ydata["type"] == "CompiledGraph"
            assert "step1" in ydata["nodes"]
