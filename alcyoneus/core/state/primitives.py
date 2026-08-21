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

"""Typed Multimodal Media and SlashCommand primitives for Alcyoneus OS.

Provides strongly-typed Pydantic V2 input models for rich content attachments
including Video, Document, Audio, Image, and SlashCommand primitives.
"""

from __future__ import annotations

import enum
import mimetypes
import pathlib
from typing import Literal, TypeVar

import pydantic


_BaseMediaT = TypeVar("_BaseMediaT", bound="_BaseMedia")


class BuiltinSlashCommandName(str, enum.Enum):
    """Built-in slash command names."""

    PLAN = "plan"


class SlashCommand(pydantic.BaseModel):
    """Represents an interactive slash command passed as input or tool call."""

    model_config = pydantic.ConfigDict(frozen=True)

    kind: Literal["slash_command"] = "slash_command"
    name: str | BuiltinSlashCommandName
    command: str = ""

    @property
    def full_command(self) -> str:
        """Returns the full slash command text, e.g. '/plan some instruction'."""
        cmd_name = self.name.value if isinstance(self.name, BuiltinSlashCommandName) else self.name
        if not cmd_name.startswith("/"):
            cmd_name = f"/{cmd_name}"
        if self.command:
            return f"{cmd_name} {self.command}"
        return cmd_name


class _BaseMedia(pydantic.BaseModel):
    """Base Pydantic model for binary media attachments."""

    model_config = pydantic.ConfigDict(frozen=True)

    data: bytes | None = None
    uri: str | None = None
    mime_type: str | None = None

    @pydantic.model_validator(mode="after")
    def _validate_source(self) -> _BaseMedia:
        if self.data is None and self.uri is None:
            raise ValueError("Media attachment must provide either data or uri.")
        return self

    @classmethod
    def from_file(
        cls: type[_BaseMediaT], path: str | pathlib.Path, mime_type: str | None = None
    ) -> _BaseMediaT:
        """Constructs a media attachment from a local file path."""
        p = pathlib.Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"Media file not found: {path}")

        if mime_type is None:
            mime_type, _ = mimetypes.guess_type(str(p))

        data = p.read_bytes()
        return cls(data=data, uri=str(p.resolve()), mime_type=mime_type)

    @classmethod
    def from_bytes(
        cls: type[_BaseMediaT], data: bytes, mime_type: str | None = None
    ) -> _BaseMediaT:
        """Constructs a media attachment from in-memory raw bytes."""
        return cls(data=data, mime_type=mime_type)


class Image(_BaseMedia):
    """Image attachment input model (PNG, JPEG, WebP, GIF, SVG)."""

    kind: Literal["image"] = "image"
    mime_type: str = "image/png"


class Audio(_BaseMedia):
    """Audio attachment input model (MP3, WAV, AAC, FLAC, OGG)."""

    kind: Literal["audio"] = "audio"
    mime_type: str = "audio/mp3"


class Video(_BaseMedia):
    """Video attachment input model (MP4, WebM, AVI, QuickTime, MOV, 3GPP, WMV, FLV)."""

    kind: Literal["video"] = "video"
    mime_type: str = "video/mp4"


class Document(_BaseMedia):
    """Document attachment input model (PDF, TXT, HTML, Markdown, CSV, DOCX)."""

    kind: Literal["document"] = "document"
    mime_type: str = "application/pdf"


__all__ = [
    "Audio",
    "BuiltinSlashCommandName",
    "Document",
    "Image",
    "SlashCommand",
    "Video",
]
