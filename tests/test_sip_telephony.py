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

"""Unit tests for production-grade SIPTelephony error handling and VoIP operations."""

import io
import json
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from alcyoneus.core.voice import (
    SIPCallConfig,
    SIPCallFailedError,
    SIPConfigurationError,
    SIPTelephony,
    SIPTelephonyError,
)


class TestSIPTelephony(unittest.IsolatedAsyncioTestCase):
    """Test suite ensuring SIPTelephony never masks errors or silently returns mock data."""

    # 1. Missing Credentials & Configuration Errors
    async def test_initiate_call_missing_credentials_raises_error(self):
        """In production (mock=False), missing credentials MUST raise SIPConfigurationError."""
        config = SIPCallConfig(phone_number="+15551234567")
        sip = SIPTelephony(config)

        with self.assertRaises(SIPConfigurationError) as ctx:
            await sip.initiate_call()

        self.assertIn("Missing required Twilio SIP credentials", str(ctx.exception))
        self.assertIsInstance(ctx.exception, SIPTelephonyError)

    async def test_initiate_call_empty_phone_number_raises_error(self):
        """Empty phone number MUST raise SIPConfigurationError."""
        config = SIPCallConfig(
            phone_number="",
            account_sid="ACtest",
            auth_token="authtoken123456",
        )
        sip = SIPTelephony(config)

        with self.assertRaises(SIPConfigurationError) as ctx:
            await sip.initiate_call()

        self.assertIn("phone_number' must not be empty", str(ctx.exception))

    # 2. Production Upstream Failures (NEVER fall back to mock)
    @patch("urllib.request.urlopen")
    async def test_initiate_call_http_error_raises_sip_call_failed(self, mock_urlopen):
        """HTTP error from Twilio gateway MUST raise SIPCallFailedError, never fake success."""
        twilio_err_body = json.dumps(
            {
                "code": 21211,
                "message": "The 'To' number is not a valid phone number.",
                "status": 400,
            }
        ).encode("utf-8")

        mock_err = urllib.error.HTTPError(
            url="https://api.twilio.com/2010-04-01/Accounts/ACtest/Calls.json",
            code=400,
            msg="Bad Request",
            hdrs={},
            fp=io.BytesIO(twilio_err_body),
        )
        mock_urlopen.side_effect = mock_err

        config = SIPCallConfig(
            phone_number="+10000000000",
            account_sid="ACtest",
            auth_token="tokentest",
        )
        sip = SIPTelephony(config)

        with self.assertRaises(SIPCallFailedError) as ctx:
            await sip.initiate_call()

        err = ctx.exception
        self.assertEqual(err.status_code, 400)
        self.assertEqual(err.error_code, 21211)
        self.assertIn("The 'To' number is not a valid phone number", str(err))

    @patch("urllib.request.urlopen")
    async def test_initiate_call_network_error_raises_sip_call_failed(self, mock_urlopen):
        """Network connectivity failure MUST raise SIPCallFailedError."""
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        config = SIPCallConfig(
            phone_number="+15551234567",
            account_sid="ACtest",
            auth_token="tokentest",
        )
        sip = SIPTelephony(config)

        with self.assertRaises(SIPCallFailedError) as ctx:
            await sip.initiate_call()

        self.assertIn("Network error connecting to SIP gateway", str(ctx.exception))

    @patch("urllib.request.urlopen")
    async def test_initiate_call_missing_sid_in_response_raises_error(self, mock_urlopen):
        """If Twilio responds without a call SID, raise SIPCallFailedError."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"status": "queued"}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        config = SIPCallConfig(
            phone_number="+15551234567",
            account_sid="ACtest",
            auth_token="tokentest",
        )
        sip = SIPTelephony(config)

        with self.assertRaises(SIPCallFailedError) as ctx:
            await sip.initiate_call()

        self.assertIn("did not return a call SID", str(ctx.exception))

    # 3. Successful Production Call
    @patch("urllib.request.urlopen")
    async def test_initiate_call_success(self, mock_urlopen):
        """Valid credentials and upstream response connect successfully."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(
            {
                "sid": "CA1234567890abcdef1234567890abcdef",
                "status": "queued",
                "to": "+15551234567",
            }
        ).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        config = SIPCallConfig(
            phone_number="+15551234567",
            account_sid="ACtest",
            auth_token="tokentest",
        )
        sip = SIPTelephony(config)
        res = await sip.initiate_call()

        self.assertEqual(res["status"], "queued")
        self.assertEqual(res["call_id"], "CA1234567890abcdef1234567890abcdef")
        self.assertEqual(res["to"], "+15551234567")
        self.assertFalse(res["mock"])
        self.assertEqual(sip.active_call_id, "CA1234567890abcdef1234567890abcdef")

    # 4. Explicit Mock Mode (Only when mock=True)
    async def test_explicit_mock_mode(self):
        """When mock=True is explicitly set, simulated call is generated with mock=True indicator."""
        config = SIPCallConfig(phone_number="+15551234567", mock=True)
        sip = SIPTelephony(config)

        res = await sip.initiate_call()
        self.assertEqual(res["status"], "connected")
        self.assertTrue(res["call_id"].startswith("sip_mock_"))
        self.assertTrue(res["mock"])
        self.assertEqual(sip.active_call_id, res["call_id"])

        # Hang up mock call
        hangup_res = await sip.hangup()
        self.assertEqual(hangup_res["status"], "completed")
        self.assertTrue(hangup_res["mock"])
        self.assertIsNone(sip.active_call_id)

    # 5. Hangup & Call Status
    async def test_hangup_without_active_call_raises_error(self):
        """In production, hanging up without an active call ID raises SIPConfigurationError."""
        config = SIPCallConfig(
            phone_number="+15551234567",
            account_sid="ACtest",
            auth_token="tokentest",
        )
        sip = SIPTelephony(config)

        with self.assertRaises(SIPConfigurationError) as ctx:
            await sip.hangup()

        self.assertIn("no active SIP call ID found", str(ctx.exception))

    @patch("urllib.request.urlopen")
    async def test_hangup_production_success(self, mock_urlopen):
        """Hangup sends termination request to Twilio API and clears active_call_id."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(
            {
                "sid": "CA1234567890abcdef",
                "status": "completed",
            }
        ).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        config = SIPCallConfig(
            phone_number="+15551234567",
            account_sid="ACtest",
            auth_token="tokentest",
        )
        sip = SIPTelephony(config)
        sip.active_call_id = "CA1234567890abcdef"

        res = await sip.hangup()
        self.assertEqual(res["status"], "completed")
        self.assertEqual(res["call_id"], "CA1234567890abcdef")
        self.assertIsNone(sip.active_call_id)

    @patch("urllib.request.urlopen")
    async def test_get_call_status_success(self, mock_urlopen):
        """Fetching status queries Twilio API and returns live call status."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(
            {
                "sid": "CA1234567890abcdef",
                "status": "in-progress",
                "duration": "45",
            }
        ).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        config = SIPCallConfig(
            phone_number="+15551234567",
            account_sid="ACtest",
            auth_token="tokentest",
        )
        sip = SIPTelephony(config)
        status = await sip.get_call_status("CA1234567890abcdef")

        self.assertEqual(status["status"], "in-progress")
        self.assertEqual(status["call_id"], "CA1234567890abcdef")
        self.assertEqual(status["duration"], "45")


if __name__ == "__main__":
    unittest.main()
