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

"""SIP Telephony VoIP protocol adapter for voice AI applications."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any


logger = logging.getLogger("alcyoneus.voice.sip")


class SIPTelephonyError(Exception):
    """Base exception for SIP telephony VoIP operations."""


class SIPConfigurationError(SIPTelephonyError):
    """Raised when required SIP configuration or credentials are missing or invalid."""


class SIPCallFailedError(SIPTelephonyError):
    """Raised when initiating, updating, or terminating a SIP call fails."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        error_code: int | str | None = None,
        response_body: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.response_body = response_body


@dataclass
class SIPCallConfig:
    """Config for establishing a SIP VoIP phone call session."""

    phone_number: str
    sip_domain: str = "sip.twilio.com"
    caller_id: str | None = None
    account_sid: str | None = None
    auth_token: str | None = None
    timeout_seconds: float = 10.0
    mock: bool = False


class SIPTelephony:
    """Production-grade SIP Telephony session controller for VoIP call handling."""

    def __init__(self, config: SIPCallConfig) -> None:
        self.config = config
        self.active_call_id: str | None = None

    async def initiate_call(self) -> dict[str, Any]:
        """Initiate outbound SIP / VoIP call via Twilio / SIP REST gateway.

        Raises:
            SIPConfigurationError: If phone number or credentials are missing when mock=False.
            SIPCallFailedError: If the upstream SIP gateway fails to connect or rejects the call.
        """
        logger.info(
            "Initiating SIP call to %s via %s", self.config.phone_number, self.config.sip_domain
        )

        if not self.config.phone_number:
            raise SIPConfigurationError(
                "Cannot initiate SIP call: 'phone_number' must not be empty."
            )

        # Explicit mock mode for dev/testing
        if self.config.mock:
            mock_id = f"sip_mock_{uuid.uuid4().hex[:12]}"
            self.active_call_id = mock_id
            logger.info("Mock SIP mode enabled: generating simulated call session %s", mock_id)
            return {
                "status": "connected",
                "call_id": mock_id,
                "to": self.config.phone_number,
                "from": self.config.caller_id or "+15005550006",
                "sip_domain": self.config.sip_domain,
                "mock": True,
            }

        if not self.config.account_sid or not self.config.auth_token:
            raise SIPConfigurationError(
                "Missing required Twilio SIP credentials: 'account_sid' and 'auth_token' "
                "must be provided when mock=False."
            )

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.config.account_sid}/Calls.json"
        data = urllib.parse.urlencode(
            {
                "To": self.config.phone_number,
                "From": self.config.caller_id or "+15005550006",
                "Url": f"https://{self.config.sip_domain}/voice.xml",
            }
        ).encode("utf-8")

        auth_str = base64.b64encode(
            f"{self.config.account_sid}:{self.config.auth_token}".encode()
        ).decode()
        headers = {
            "Authorization": f"Basic {auth_str}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        def _post_call():
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")  # nosec: B310  # noqa: S310
            try:
                with urllib.request.urlopen(req, timeout=self.config.timeout_seconds) as resp:  # noqa: S310
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as err:
                body = err.read().decode("utf-8", errors="replace")
                err_msg = body
                err_code = None
                try:
                    err_json = json.loads(body)
                    err_msg = err_json.get("message", body)
                    err_code = err_json.get("code")
                except (json.JSONDecodeError, TypeError) as decode_err:
                    logger.debug("Failed to parse JSON error body: %s", decode_err)
                raise SIPCallFailedError(
                    f"SIP call to {self.config.phone_number} failed (HTTP {err.code}): {err_msg}",
                    status_code=err.code,
                    error_code=err_code,
                    response_body=body,
                ) from err
            except urllib.error.URLError as err:
                raise SIPCallFailedError(
                    f"Network error connecting to SIP gateway: {err.reason}"
                ) from err

        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, _post_call)
        call_id = res.get("sid")
        if not call_id:
            raise SIPCallFailedError(f"SIP gateway did not return a call SID: {res}")

        self.active_call_id = call_id
        return {
            "status": res.get("status", "queued"),
            "call_id": call_id,
            "to": self.config.phone_number,
            "from": self.config.caller_id or "+15005550006",
            "sip_domain": self.config.sip_domain,
            "mock": False,
        }

    async def hangup(self, call_id: str | None = None) -> dict[str, Any]:
        """Terminate active SIP call via Twilio / SIP REST gateway.

        Raises:
            SIPConfigurationError: If no active call ID or credentials exist.
            SIPCallFailedError: If the hangup request to the gateway fails.
        """
        target_call_id = call_id or self.active_call_id
        logger.info("Terminating SIP call %s to %s", target_call_id, self.config.phone_number)

        if self.config.mock:
            self.active_call_id = None
            return {
                "status": "completed",
                "call_id": target_call_id or "sip_mock_none",
                "mock": True,
            }

        if not target_call_id:
            raise SIPConfigurationError("Cannot hang up: no active SIP call ID found.")

        if not self.config.account_sid or not self.config.auth_token:
            raise SIPConfigurationError(
                "Missing required Twilio SIP credentials: 'account_sid' and 'auth_token' "
                "must be provided when mock=False."
            )

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.config.account_sid}/Calls/{target_call_id}.json"
        data = urllib.parse.urlencode({"Status": "completed"}).encode("utf-8")

        auth_str = base64.b64encode(
            f"{self.config.account_sid}:{self.config.auth_token}".encode()
        ).decode()
        headers = {
            "Authorization": f"Basic {auth_str}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        def _post_hangup():
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")  # nosec: B310  # noqa: S310
            try:
                with urllib.request.urlopen(req, timeout=self.config.timeout_seconds) as resp:  # noqa: S310
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as err:
                body = err.read().decode("utf-8", errors="replace")
                err_msg = body
                err_code = None
                try:
                    err_json = json.loads(body)
                    err_msg = err_json.get("message", body)
                    err_code = err_json.get("code")
                except (json.JSONDecodeError, TypeError) as decode_err:
                    logger.debug("Failed to parse JSON error body: %s", decode_err)
                raise SIPCallFailedError(
                    f"Failed to hang up SIP call {target_call_id} (HTTP {err.code}): {err_msg}",
                    status_code=err.code,
                    error_code=err_code,
                    response_body=body,
                ) from err
            except urllib.error.URLError as err:
                raise SIPCallFailedError(
                    f"Network error connecting to SIP gateway on hangup: {err.reason}"
                ) from err

        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, _post_hangup)
        self.active_call_id = None
        return {
            "status": res.get("status", "completed"),
            "call_id": target_call_id,
            "mock": False,
        }

    async def get_call_status(self, call_id: str | None = None) -> dict[str, Any]:
        """Fetch current SIP call status from the gateway."""
        target_call_id = call_id or self.active_call_id
        if self.config.mock:
            return {
                "status": "in-progress" if self.active_call_id else "completed",
                "call_id": target_call_id,
                "mock": True,
            }

        if not target_call_id:
            raise SIPConfigurationError("Cannot check call status: no active SIP call ID found.")

        if not self.config.account_sid or not self.config.auth_token:
            raise SIPConfigurationError(
                "Missing required Twilio SIP credentials: 'account_sid' and 'auth_token' "
                "must be provided when mock=False."
            )

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.config.account_sid}/Calls/{target_call_id}.json"
        auth_str = base64.b64encode(
            f"{self.config.account_sid}:{self.config.auth_token}".encode()
        ).decode()
        headers = {"Authorization": f"Basic {auth_str}"}

        def _get_status():
            req = urllib.request.Request(url, headers=headers, method="GET")  # nosec: B310  # noqa: S310
            try:
                with urllib.request.urlopen(req, timeout=self.config.timeout_seconds) as resp:  # noqa: S310
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as err:
                body = err.read().decode("utf-8", errors="replace")
                raise SIPCallFailedError(
                    f"Failed to get SIP call status for {target_call_id} (HTTP {err.code}): {body}",
                    status_code=err.code,
                    response_body=body,
                ) from err
            except urllib.error.URLError as err:
                raise SIPCallFailedError(
                    f"Network error connecting to SIP gateway: {err.reason}"
                ) from err

        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, _get_status)
        return {
            "status": res.get("status", "unknown"),
            "call_id": target_call_id,
            "duration": res.get("duration"),
            "mock": False,
        }


__all__ = [
    "SIPCallConfig",
    "SIPCallFailedError",
    "SIPConfigurationError",
    "SIPTelephony",
    "SIPTelephonyError",
]
