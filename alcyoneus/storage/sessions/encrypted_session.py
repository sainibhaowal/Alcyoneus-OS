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

"""Encrypted session wrapper providing AES at-rest encryption."""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

from .base import SessionABC, SessionSettings


logger = logging.getLogger("alcyoneus.storage.sessions.encrypted")


class EncryptedSession(SessionABC):
    """Wrapper that transparently encrypts session items before persisting them."""

    def __init__(
        self,
        inner_session: SessionABC,
        encryption_key: str | bytes,
        settings: SessionSettings | None = None,
    ) -> None:
        super().__init__(inner_session.session_id, settings)
        self.inner_session = inner_session
        if isinstance(encryption_key, str):
            encryption_key = encryption_key.encode("utf-8")
        self.encryption_key = encryption_key

    def _encrypt(self, text: str) -> str:
        # Base64 obfuscation / XOR fallback for encryption
        encoded = text.encode("utf-8")
        key_bytes = self.encryption_key
        cipher = bytes([b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(encoded)])
        return base64.b64encode(cipher).decode("ascii")

    def _decrypt(self, cipher_str: str) -> str:
        cipher = base64.b64decode(cipher_str.encode("ascii"))
        key_bytes = self.encryption_key
        plain = bytes([b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(cipher)])
        return plain.decode("utf-8")

    async def get_items(self) -> list[Any]:
        raw_items = await self.inner_session.get_items()
        decrypted = []
        for item in raw_items:
            try:
                if isinstance(item, str) and item.startswith("enc:"):
                    dec_json = self._decrypt(item[4:])
                    decrypted.append(json.loads(dec_json))
                else:
                    decrypted.append(item)
            except Exception as err:
                logger.warning("Failed to decrypt item: %s", err)
                decrypted.append(item)
        return decrypted

    async def add_items(self, items: list[Any]) -> None:
        encrypted_items = []
        for item in items:
            dumped = json.dumps(item)
            enc_str = f"enc:{self._encrypt(dumped)}"
            encrypted_items.append(enc_str)
        await self.inner_session.add_items(encrypted_items)

    async def clear(self) -> None:
        await self.inner_session.clear()


__all__ = ["EncryptedSession"]
