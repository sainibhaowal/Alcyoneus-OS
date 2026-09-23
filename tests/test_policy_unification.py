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

"""Comprehensive test suite for unified policy engine and ToolNode integration."""

import tempfile
from pathlib import Path

import pytest

from alcyoneus import (
    Decision,
    Policy,
    PolicyAction,
    PolicyConfig,
    PolicyEngine,
    ToolExecutionPolicy,
    ToolNode,
    allow,
    allow_all,
    ask_user,
    deny,
    deny_all,
    workspace_only,
)
from alcyoneus.core.graph.tool_node.policy import (
    Decision as ToolNodeDecision,
)
from alcyoneus.core.graph.tool_node.policy import (
    Policy as ToolNodePolicy,
)
from alcyoneus.core.graph.tool_node.policy import (
    PolicyAction as ToolNodePolicyAction,
)
from alcyoneus.core.graph.tool_node.policy import (
    PolicyConfig as ToolNodePolicyConfig,
)
from alcyoneus.core.graph.tool_node.policy import (
    PolicyEngine as ToolNodePolicyEngine,
)
from alcyoneus.core.graph.tool_node.policy import (
    allow as tool_node_allow,
)


# Dummy tools for testing
def read_file(path: str) -> str:
    """Read contents of a file."""
    return f"content of {path}"


def delete_file(path: str) -> str:
    """Delete a file."""
    return f"deleted {path}"


def dangerous_operation(target: str) -> str:
    """A dangerous tool requiring confirmation."""
    return f"operated on {target}"


class TestDecisionAndPolicyActionInteroperability:
    """Tests bidirectional equality and string matching between Decision and PolicyAction."""

    def test_decision_and_action_equality(self):
        assert Decision.APPROVE == PolicyAction.ALLOW
        assert PolicyAction.ALLOW == Decision.APPROVE
        assert Decision.DENY == PolicyAction.DENY
        assert PolicyAction.DENY == Decision.DENY
        assert Decision.ASK_USER == PolicyAction.ASK_USER
        assert PolicyAction.ASK_USER == Decision.ASK_USER

    def test_string_matching(self):
        assert Decision.APPROVE == "APPROVE"
        assert Decision.APPROVE == "ALLOW"
        assert Decision.APPROVE == "allow"
        assert PolicyAction.ALLOW == "allow"
        assert PolicyAction.ALLOW == "approve"
        assert PolicyAction.ALLOW == "APPROVE"

        assert Decision.DENY == "DENY"
        assert Decision.DENY == "deny"
        assert PolicyAction.DENY == "deny"
        assert PolicyAction.DENY == "DENY"

        assert Decision.ASK_USER == "ASK_USER"
        assert Decision.ASK_USER == "ask_user"
        assert PolicyAction.ASK_USER == "ask_user"
        assert PolicyAction.ASK_USER == "ASK_USER"

    def test_import_path_identity(self):
        assert Decision is ToolNodeDecision
        assert Policy is ToolNodePolicy
        assert PolicyAction is ToolNodePolicyAction
        assert PolicyConfig is ToolNodePolicyConfig
        assert PolicyEngine is ToolNodePolicyEngine


class TestUnifiedPolicyModel:
    """Tests the unified Policy dataclass features."""

    def test_single_tool_and_multi_tool(self):
        p1 = allow("read_file")
        assert p1.tool == "read_file"
        assert p1.tool_names == ("read_file",)
        assert p1.decision == Decision.APPROVE
        assert p1.action == PolicyAction.ALLOW

        p2 = tool_node_allow(["read_file", "view_file"])
        assert p2.tool_names == ("read_file", "view_file")
        assert p2.matches("read_file")
        assert p2.matches("view_file")
        assert not p2.matches("write_file")

    def test_predicate_harmonization(self):
        pred = lambda args: args.get("safe", False) is True  # noqa: E731
        p = Policy(tool="test_tool", when=pred)
        assert p.when is pred
        assert p.argument_predicate is pred
        assert p.matches("test_tool", args={"safe": True})
        assert not p.matches("test_tool", args={"safe": False})

    def test_mcp_and_user_context_filtering(self):
        p = tool_node_allow(
            "custom_tool",
            mcp_server_names=["server_a"],
            user_ids=["user_123"],
            tenant_ids=["tenant_456"],
        )
        assert p.matches(
            "custom_tool",
            mcp_server_name="server_a",
            context={"user_id": "user_123", "tenant_id": "tenant_456"},
        )
        assert not p.matches(
            "custom_tool",
            mcp_server_name="server_b",
            context={"user_id": "user_123", "tenant_id": "tenant_456"},
        )
        assert not p.matches(
            "custom_tool",
            mcp_server_name="server_a",
            context={"user_id": "other_user", "tenant_id": "tenant_456"},
        )

    def test_priority_tiers(self):
        p_spec_deny = deny("specific_tool")
        assert p_spec_deny.priority_tier == 1

        p_spec_ask = ask_user("specific_tool")
        assert p_spec_ask.priority_tier == 2

        p_spec_allow = allow("specific_tool")
        assert p_spec_allow.priority_tier == 3

        p_prefix_deny = deny("prefix/*")
        assert p_prefix_deny.priority_tier == 4

        p_prefix_ask = ask_user("prefix/*")
        assert p_prefix_ask.priority_tier == 5

        p_prefix_allow = allow("prefix/*")
        assert p_prefix_allow.priority_tier == 6

        p_glob_deny = deny_all()
        assert p_glob_deny.priority_tier == 7

        p_glob_ask = ask_user("*")
        assert p_glob_ask.priority_tier == 8

        p_glob_allow = allow_all()
        assert p_glob_allow.priority_tier == 9


class TestPolicyEngineAndConfig:
    """Tests PolicyEngine and PolicyConfig evaluation."""

    @pytest.mark.asyncio
    async def test_async_and_sync_evaluation(self):
        engine = PolicyEngine(
            [
                deny("dangerous_tool"),
                allow_all(),
            ]
        )

        # Async evaluate
        dec, pol = await engine.evaluate("dangerous_tool", {})
        assert dec == Decision.DENY
        assert dec == PolicyAction.DENY

        dec, pol = await engine.evaluate("read_file", {})
        assert dec == Decision.APPROVE
        assert dec == PolicyAction.ALLOW

        # Sync evaluate
        dec_sync, _ = engine.evaluate_sync("dangerous_tool", {})
        assert dec_sync == Decision.DENY

        dec_sync, _ = engine.evaluate_sync("read_file", {})
        assert dec_sync == Decision.APPROVE

    def test_policy_config_compatibility(self):
        cfg = PolicyConfig(
            policies=[deny("delete_file")],
            default_action=PolicyAction.ALLOW,
        )
        dec, _ = cfg.evaluate_sync("delete_file", {})
        assert dec == PolicyAction.DENY

        dec, _ = cfg.evaluate_sync("read_file", {})
        assert dec == PolicyAction.ALLOW


class TestToolNodeUnifiedPolicyIntegration:
    """Tests ToolNode executing with unified PolicyEngine, PolicyConfig, and raw policy lists."""

    @pytest.mark.asyncio
    async def test_tool_node_with_policy_engine(self):
        engine = PolicyEngine(
            [
                deny("delete_file"),
                allow("read_file"),
            ]
        )
        node = ToolNode([read_file, delete_file], policy=engine)

        # Allowed tool succeeds
        msg = await node.invoke(
            name="read_file",
            args={"path": "test.txt"},
            tool_call_id="call_1",
        )
        assert msg.metadata["tool_call_id"] == "call_1"
        assert not getattr(msg.content[0], "is_error", False)

        # Denied tool returns safety error block
        denied_msg = await node.invoke(
            name="delete_file",
            args={"path": "test.txt"},
            tool_call_id="call_2",
        )
        assert "denied by safety policy" in denied_msg.content[0].message

    @pytest.mark.asyncio
    async def test_tool_node_with_policy_list(self):
        policies = [
            deny("delete_file"),
            allow("read_file"),
        ]
        # Pass raw list to policy=
        node = ToolNode([read_file, delete_file], policy=policies)

        denied_msg = await node.invoke(
            name="delete_file",
            args={"path": "test.txt"},
            tool_call_id="call_deny",
        )
        assert "denied by safety policy" in denied_msg.content[0].message

    @pytest.mark.asyncio
    async def test_tool_node_with_policy_config(self):
        cfg = PolicyConfig(
            policies=[deny("delete_file")],
            default_action=PolicyAction.ALLOW,
        )
        # Pass to policy_config=
        node = ToolNode([read_file, delete_file], policy_config=cfg)

        denied_msg = await node.invoke(
            name="delete_file",
            args={"path": "test.txt"},
            tool_call_id="call_cfg",
        )
        assert "denied by safety policy" in denied_msg.content[0].message

    @pytest.mark.asyncio
    async def test_tool_node_with_ask_user_handler(self):
        approved = False

        async def custom_handler(tool_name: str, args: dict) -> bool:
            return approved

        policies = [
            ask_user("dangerous_operation", handler=custom_handler),
            allow_all(),
        ]
        node = ToolNode([dangerous_operation], policy=policies)

        # 1. When user rejects
        approved = False
        rej_msg = await node.invoke(
            name="dangerous_operation",
            args={"target": "database"},
            tool_call_id="call_ask_1",
        )
        assert "not approved by user" in rej_msg.content[0].message

        # 2. When user approves
        approved = True
        appr_msg = await node.invoke(
            name="dangerous_operation",
            args={"target": "database"},
            tool_call_id="call_ask_2",
        )
        assert "not approved by user" not in str(appr_msg.content)

    @pytest.mark.asyncio
    async def test_tool_node_with_workspace_only_sandboxing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            allowed_dir = Path(tmpdir).resolve()
            policies = workspace_only([allowed_dir])
            node = ToolNode([read_file], policy=policies)

            # Inside workspace -> allowed
            inside_path = str(allowed_dir / "safe.txt")
            ok_msg = await node.invoke(
                name="read_file",
                args={"path": inside_path},
                tool_call_id="call_ws_1",
            )
            assert not getattr(ok_msg.content[0], "is_error", False)

            # Outside workspace -> denied
            bad_msg = await node.invoke(
                name="read_file",
                args={"path": "/etc/shadow"},
                tool_call_id="call_ws_2",
            )
            assert "denied by safety policy" in bad_msg.content[0].message

    def test_tool_execution_policy_parameter(self):
        exec_pol = ToolExecutionPolicy(timeout=15.0, max_retries=2, retry_on_failure=True)
        node = ToolNode([read_file], policy=exec_pol)
        assert node._execution_policy is exec_pol
