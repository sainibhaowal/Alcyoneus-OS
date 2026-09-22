# Voice & SIP Telephony — Production Guide

> **Deploy real-time AI voice agents connected to VoIP and the Public Switched Telephone Network (PSTN).**

---

## Overview

Alcyoneus OS provides native VoIP and SIP telephony primitives, enabling conversational AI agents to place and manage telephone calls with enterprise gateways (Twilio, FreeSWITCH, Asterisk):

```
Agent StateGraph ──► SIPTelephony Session ──► SIP Gateway (Twilio / PBX) ──► PSTN Phone
       ▲                                              │
       └────────────── Real-time Audio / Events ◄─────┘
```

---

## 1. Quick Start: Outbound SIP Call

```python
import asyncio
from alcyoneus.core.voice.sip import SIPTelephony, SIPCallConfig

async def main():
    config = SIPCallConfig(
        phone_number="+14155552671",
        caller_id="+15005550006",
        sip_domain="sip.twilio.com",
        account_sid=os.getenv("TWILIO_ACCOUNT_SID", "ACtest"),
        auth_token=os.getenv("TWILIO_AUTH_TOKEN", "mock_token"),
        timeout_seconds=15.0,
    )

    telephony = SIPTelephony(config)

    # 1. Initiate outbound call
    call_info = await telephony.initiate_call()
    print(f"Call initiated: {call_info['call_id']}, status={call_info['status']}")

    # 2. Check call status
    status = await telephony.get_call_status()
    print(f"Current status: {status['status']}")

    # 3. Terminate call
    hangup_info = await telephony.hangup()
    print(f"Call finished: status={hangup_info['status']}")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 2. Configuration Options

The `SIPCallConfig` dataclass accepts:

| Field | Type | Default | Description |
|---|---|---|---|
| `phone_number` | `str` | *required* | Destination E.164 phone number or SIP URI. |
| `sip_domain` | `str` | `"sip.twilio.com"` | Upstream SIP trunk or PBX domain. |
| `caller_id` | `str \| None` | `None` | Verified caller ID phone number presented to callee. |
| `account_sid` | `str \| None` | `None` | Twilio / SIP provider account identifier. |
| `auth_token` | `str \| None` | `None` | SIP provider authentication token / secret. |
| `timeout_seconds` | `float` | `10.0` | Gateway HTTP request timeout in seconds. |
| `mock` | `bool` | `False` | When `True`, generates deterministic simulated sessions without making network calls. |

---

## 3. Testing with Mock Mode

For CI/CD pipelines, unit tests, and local development without incurring telephony carrier costs, enable `mock=True`:

```python
from alcyoneus.core.voice.sip import SIPTelephony, SIPCallConfig

# No API credentials needed in mock mode
config = SIPCallConfig(phone_number="+15550001234", mock=True)
telephony = SIPTelephony(config)

call = await telephony.initiate_call()
assert call["mock"] is True
assert call["status"] == "connected"

status = await telephony.get_call_status()
assert status["status"] == "in-progress"

hangup = await telephony.hangup()
assert hangup["status"] == "completed"
```

---

## 4. Integrating with Agent StateGraph

You can trigger telephone calls directly as a tool or as a graph node:

```python
from alcyoneus.core import StateGraph, AgentState
from alcyoneus.core.voice.sip import SIPTelephony, SIPCallConfig
from alcyoneus.utils.decorators import tool

@tool
async def place_phone_call(to_number: str, message: str) -> str:
    """Places an automated outbound voice call to a user."""
    config = SIPCallConfig(
        phone_number=to_number,
        account_sid=os.getenv("TWILIO_ACCOUNT_SID"),
        auth_token=os.getenv("TWILIO_AUTH_TOKEN"),
    )
    telephony = SIPTelephony(config)
    result = await telephony.initiate_call()
    return f"Call placed successfully. Call SID: {result['call_id']}"
```

---

## 5. Error Handling

Alcyoneus provides a clear exception hierarchy:

* `SIPTelephonyError` — Base class for all voice/SIP exceptions.
* `SIPConfigurationError` — Raised when `phone_number` or required credentials are empty in non-mock mode.
* `SIPCallFailedError` — Raised when the upstream SIP gateway returns an HTTP error or rejects the call. Contains `.status_code`, `.error_code`, and `.response_body`.

```python
from alcyoneus.core.voice.sip import (
    SIPTelephony, SIPCallConfig,
    SIPConfigurationError, SIPCallFailedError,
)

try:
    telephony = SIPTelephony(config)
    await telephony.initiate_call()
except SIPConfigurationError as err:
    print(f"Missing config: {err}")
except SIPCallFailedError as err:
    print(f"Call failed (HTTP {err.status_code}, code {err.error_code}): {err}")
```
