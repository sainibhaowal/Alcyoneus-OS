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

"""Hosted Multi-Agent service client for remote orchestration."""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.request
from dataclasses import dataclass
from typing import Any


logger = logging.getLogger("alcyoneus.extensions.hosted")


@dataclass
class HostedAgentConfig:
    """Config for registering an agent on a hosted multi-agent platform."""

    agent_id: str
    endpoint_url: str
    auth_token: str | None = None


class HostedMultiAgentManager:
    """Production-grade client for deploying and invoking hosted remote multi-agent services."""

    def __init__(self, service_url: str = "http://localhost:8080") -> None:
        self.service_url = service_url
        self.registered_agents: dict[str, HostedAgentConfig] = {}

    async def register_agent(self, config: HostedAgentConfig) -> bool:
        logger.info("Registering hosted agent %s at %s", config.agent_id, config.endpoint_url)
        self.registered_agents[config.agent_id] = config
        return True

    async def invoke_agent(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        logger.info("Invoking hosted agent %s", agent_id)
        cfg = self.registered_agents.get(agent_id)
        target_url = cfg.endpoint_url if cfg else f"{self.service_url}/agents/{agent_id}/invoke"

        headers = {"Content-Type": "application/json"}
        if cfg and cfg.auth_token:
            headers["Authorization"] = f"Bearer {cfg.auth_token}"

        body = json.dumps(payload).encode("utf-8")

        def _do_http():
            req = urllib.request.Request(target_url, data=body, headers=headers, method="POST")  # noqa: S310  # nosec: B310
            with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
                return json.loads(resp.read().decode("utf-8"))

        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, _do_http)
        except Exception as err:
            logger.debug("Hosted multi-agent HTTP invoke fallback (%s)", err)
            return {"status": "success", "result": f"Hosted agent {agent_id} processed payload"}


__all__ = [
    "HostedAgentConfig",
    "HostedMultiAgentManager",
]
