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

"""Comprehensive test suite for all Alcyoneus OS enterprise features."""

import asyncio
import unittest

import alcyoneus as alc
from alcyoneus.core.guardrails import (
    GuardrailFunctionOutput,
    InputGuardrail,
    InputGuardrailTripwireTriggered,
    OutputGuardrail,
    OutputGuardrailTripwireTriggered,
    ToolGuardrailFunctionOutput,
    ToolInputGuardrail,
    ToolOutputGuardrail,
    input_guardrail,
    output_guardrail,
    tool_input_guardrail,
    tool_output_guardrail,
)
from alcyoneus.core.hooks import (
    AgentHooks,
    AgentSession,
    HookContext,
    OperationContext,
    RunHooks,
    SessionContext,
    SessionContinuationMode,
    StateStore,
    TurnContext,
    agent_session,
)
from alcyoneus.core.llm import ModelRetrySettings, RetryDecision, default_retry_policy
from alcyoneus.core.mcp import MCPManager, MCPServerStdio, MCPServerStreamableHTTP
from alcyoneus.core.state.run_state import RunState
from alcyoneus.core.tracing import (
    AgentSpanData,
    FunctionSpanData,
    Span,
    Trace,
    agent_span,
    function_span,
    trace,
)
from alcyoneus.core.voice import (
    AudioInput,
    OpenAISTTModel,
    OpenAITTSModel,
    StreamedAudioResult,
    VoicePipeline,
)
from alcyoneus.prebuilt.tools import (
    ApplyPatchTool,
    CustomTool,
    ProgrammaticToolCallingTool,
    ShellTool,
    ToolSearchTool,
    tool_namespace,
)
from alcyoneus.runtime.adapters.llm import AnyLLMConverter, LiteLLMConverter, MultiProvider
from alcyoneus.sandbox import (
    BaseSandbox,
    CloudflareSandbox,
    DockerSandbox,
    E2BSandbox,
    ExecResult,
    LocalSandbox,
    ModalSandbox,
    SandboxConfig,
    SandboxManifest,
)
from alcyoneus.storage import (
    EncryptedSession,
    MongoDBSession,
    RedisSession,
    SQLAlchemySession,
    SQLiteSession,
    Session,
)


class TestAllNewFeatures(unittest.IsolatedAsyncioTestCase):

    # 1. Guardrails
    async def test_input_guardrail_pass(self):
        @input_guardrail
        def check_safe(ctx, agent, input_data):
            return GuardrailFunctionOutput(output_info="ok", tripwire_triggered=False)

        res = await check_safe.run(agent=None, input_data="hello")
        self.assertFalse(res.output.tripwire_triggered)

    async def test_input_guardrail_tripwire(self):
        @input_guardrail
        def check_unsafe(ctx, agent, input_data):
            return GuardrailFunctionOutput(output_info="unsafe", tripwire_triggered=True)

        res = await check_unsafe.run(agent=None, input_data="bad prompt")
        self.assertTrue(res.output.tripwire_triggered)

    # 2. Tracing
    async def test_tracing_spans(self):
        with trace("test_trace") as tr:
            with agent_span("test_agent"):
                with function_span("test_tool"):
                    pass
        self.assertEqual(len(tr.spans), 2)
        self.assertEqual(tr.name, "test_trace")

    # 3. Model Providers & Retry
    async def test_multi_provider(self):
        mp = MultiProvider()
        conv, model = mp.resolve_converter("google/gemini-1.5-pro")
        self.assertEqual(model, "gemini-1.5-pro")

    async def test_retry_policy(self):
        settings = ModelRetrySettings(max_retries=3)
        self.assertEqual(settings.max_retries, 3)

    # 4. Voice Pipeline
    async def test_voice_pipeline(self):
        stt = OpenAISTTModel()
        tts = OpenAITTSModel()
        pipeline = VoicePipeline(stt_model=stt, tts_model=tts)
        res = await pipeline.run(b"fake audio", agent=lambda text: f"Echo: {text}")
        self.assertIn("Echo:", res.transcript)

    # 5. Sandboxes
    async def test_local_sandbox(self):
        async with LocalSandbox() as sb:
            res = await sb.exec("echo 'hello sandbox'")
            self.assertTrue(res.success)
            self.assertIn("hello sandbox", res.stdout)

    # 6. Session Backends
    async def test_sessions(self):
        session = Session("sess1")
        await session.add_items(["msg1", "msg2"])
        items = await session.get_items()
        self.assertEqual(len(items), 2)

        inner_session = Session("sess2")
        enc_session = EncryptedSession(inner_session, "secret_key_1234567890")
        await enc_session.add_items(["secret message"])
        dec_items = await enc_session.get_items()
        self.assertIn("secret message", dec_items)

    # 7. Advanced Tools
    async def test_advanced_tools(self):
        patch_tool = ApplyPatchTool()
        res = patch_tool.apply_patch("--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n")
        self.assertTrue(res.success)

        def sample_tool():
            return "ok"

        ns_tools = tool_namespace("my_namespace", [sample_tool])
        self.assertTrue(ns_tools[0].__name__.startswith("my_namespace__"))

    # 8. MCP Server Management
    async def test_mcp_manager(self):
        mgr = MCPManager()
        server = MCPServerStdio("test_stdio", "echo")
        mgr.add_server(server)
        self.assertIn("test_stdio", mgr.servers)

    # 9. Lifecycle Hooks & Sessions
    async def test_agent_session(self):
        async with agent_session("s123") as sess:
            self.assertEqual(sess.session_id, "s123")

        state = RunState(run_id="r1", active_agent_name="agent_a")
        json_str = state.to_json()
        restored = RunState.from_json(json_str)
        self.assertEqual(restored.run_id, "r1")


    # 10. Extensions, Mounts, Dapr & Realtime Filtering
    async def test_codex_and_extensions(self):
        from alcyoneus.extensions.experimental import CodexAgent, HostedMultiAgentManager
        from alcyoneus.sandbox.mounts import S3Mount
        from alcyoneus.storage.sessions import DaprSession
        from alcyoneus.core.realtime.tool_filtering import RealtimeToolFilter

        codex = CodexAgent()
        turn_res = await codex.run_turn("Refactor python module")
        self.assertEqual(turn_res["status"], "success")

        mgr = HostedMultiAgentManager()
        inv_res = await mgr.invoke_agent("a1", {})
        self.assertEqual(inv_res["status"], "success")

        mount = S3Mount(container_path="/mnt/s3", bucket_name="my-bucket")
        self.assertEqual(mount.bucket_name, "my-bucket")

        dapr = DaprSession("dapr_sess")
        await dapr.add_items(["item1"])

        filter_tool = RealtimeToolFilter(allowed_tools=["tool_a"])
        self.assertTrue(filter_tool.is_allowed("tool_a"))
        self.assertFalse(filter_tool.is_allowed("tool_b"))


if __name__ == "__main__":
    unittest.main()
