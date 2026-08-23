"""Local Whisper + TTS realtime provider.

Fully local realtime audio pipeline using:
- Whisper (faster-whisper) for ASR
- VAD (silero) for voice activity detection
- TTS (piper/coqui/bark) for speech synthesis
- Configurable barge-in, VAD tuning, audio routing
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any


try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]

from alcyoneus.core.realtime.base import (
    AudioDeltaEvent,
    InputTranscriptEvent,
    RealtimeConfig,
    RealtimeEvent,
    TurnCompleteEvent,
)


logger = logging.getLogger(__name__)

INPUT_SAMPLE_RATE = 16000
OUTPUT_SAMPLE_RATE = 24000


@dataclass
class AudioBuffer:
    """Thread-safe audio buffer for streaming."""

    data: bytearray = field(default_factory=bytearray)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def write(self, pcm: bytes) -> None:
        async with self._lock:
            self.data.extend(pcm)

    async def read(self, n: int) -> bytes:
        async with self._lock:
            if len(self.data) < n:
                return b""
            result = bytes(self.data[:n])
            del self.data[:n]
            return result

    async def clear(self) -> None:
        async with self._lock:
            self.data.clear()

    def __len__(self) -> int:
        return len(self.data)


class LocalWhisperTTSClient:
    """Local realtime client using Whisper (ASR) + TTS with VAD."""

    def __init__(
        self,
        whisper_model: str = "base",
        tts_engine: str = "piper",
        tts_voice: str = "en_US-lessac-medium",
        device: str = "cpu",
        vad_threshold: float = 0.5,
        vad_min_silence_ms: int = 500,
        vad_padding_ms: int = 300,
        barge_in_enabled: bool = True,
        barge_in_threshold: float = 0.01,
    ) -> None:
        self.whisper_model = whisper_model
        self.tts_engine = tts_engine
        self.tts_voice = tts_voice
        self.device = device
        self.vad_threshold = vad_threshold
        self.vad_min_silence_ms = vad_min_silence_ms
        self.vad_padding_ms = vad_padding_ms
        self.barge_in_enabled = barge_in_enabled
        self.barge_in_threshold = barge_in_threshold

        self._whisper = None
        self._tts = None
        self._vad = None
        self._input_buffer = AudioBuffer()
        self._output_buffer = AudioBuffer()
        self._config: RealtimeConfig | None = None
        self._running = False
        self._barge_in = False
        self._current_output_task: asyncio.Task | None = None

    async def _init_whisper(self) -> None:
        if self._whisper is None:
            try:
                from faster_whisper import WhisperModel

                self._whisper = WhisperModel(
                    self.whisper_model,
                    device=self.device,
                    compute_type="int8" if self.device == "cpu" else "float16",
                )
                logger.info("Loaded Whisper model: %s on %s", self.whisper_model, self.device)
            except ImportError:
                raise RuntimeError("faster-whisper required: pip install faster-whisper")

    async def _init_tts(self) -> None:
        if self._tts is None:
            if self.tts_engine == "piper":
                try:
                    import piper

                    self._tts = piper.PiperVoice.load(self.tts_voice)
                    logger.info("Loaded Piper voice: %s", self.tts_voice)
                except ImportError:
                    raise RuntimeError("piper-tts required: pip install piper-tts")
            elif self.tts_engine == "coqui":
                try:
                    from TTS.api import TTS

                    self._tts = TTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2").to(
                        self.device
                    )
                    logger.info("Loaded Coqui TTS: xtts_v2")
                except ImportError:
                    raise RuntimeError("coqui-tts required: pip install coqui-tts")
            else:
                raise ValueError(f"Unknown TTS engine: {self.tts_engine}")

    async def _init_vad(self) -> None:
        if self._vad is None:
            try:
                import torch

                model, utils = torch.hub.load(
                    repo_or_dir="snakers4/silero-vad", model="silero_vad", trust_repo=True
                )
                self._vad = (model, utils)
                logger.info("Loaded Silero VAD")
            except Exception as e:
                logger.warning("Silero VAD not available: %s", e)
                self._vad = None

    async def connect(self, config: RealtimeConfig, resume_handle: str | None = None) -> None:
        self._config = config
        await self._init_whisper()
        await self._init_tts()
        await self._init_vad()

        # Override VAD settings from config
        if config.vad.enabled:
            self.vad_threshold = float(config.vad.start_sensitivity or self.vad_threshold)
            self.vad_min_silence_ms = config.vad.silence_duration_ms or self.vad_min_silence_ms
            self.vad_padding_ms = config.vad.prefix_padding_ms or self.vad_padding_ms

        self._running = True
        self._barge_in = False
        logger.info("Local Whisper+TTS connected")

    @property
    def connected(self) -> bool:
        return self._running

    async def send_audio(self, pcm: bytes, sample_rate: int = INPUT_SAMPLE_RATE) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        await self._input_buffer.write(pcm)

    async def send_text(self, text: str) -> None:
        # Synthesize and queue for output
        await self._synthesize_and_play(text)

    async def send_image(self, data: bytes, mime_type: str = "image/jpeg") -> None:
        # Local multimodal not supported yet
        logger.warning("Image input not supported in local mode")

    async def send_activity_start(self) -> None:
        # Manual VAD: treat as push-to-talk start
        pass

    async def send_activity_end(self) -> None:
        # Process accumulated audio
        await self._process_input_buffer()

    async def send_tool_response(self, call_id: str, name: str, result: Any) -> None:
        # Local tool responses handled by graph, not here
        pass

    async def reseed_history(self, messages: list[Any]) -> None:
        # Not applicable for local stateless
        pass

    async def _process_input_buffer(self) -> None:
        """Process buffered audio through VAD and Whisper."""
        audio_data = await self._input_buffer.read(len(self._input_buffer))
        if not audio_data:
            return

        # Convert to float32 numpy array for VAD
        audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

        # VAD detection
        is_speech = await self._run_vad(audio_np)

        if is_speech or not self._config.vad.enabled:
            # Transcribe with Whisper
            transcript = await self._transcribe(audio_data)
            if transcript:
                yield InputTranscriptEvent(text=transcript, finished=True)
                # If tools configured, could trigger tool call here
        else:
            logger.debug("VAD: no speech detected")

    async def _run_vad(self, audio: Any) -> bool:
        if self._vad is None:
            return True  # No VAD = treat as speech
        try:
            model, (get_speech_timestamps, _, _, _, _) = self._vad
            import torch

            tensor = torch.from_numpy(audio).unsqueeze(0)
            timestamps = get_speech_timestamps(tensor, model, sampling_rate=INPUT_SAMPLE_RATE)
            return len(timestamps) > 0
        except Exception:
            return True

    async def _transcribe(self, audio_data: bytes) -> str:
        if self._whisper is None:
            return ""
        try:
            # Write to temp file for faster-whisper
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                import wave

                with wave.open(f, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(INPUT_SAMPLE_RATE)
                    wf.writeframes(audio_data)
                temp_path = f.name

            segments, _ = self._whisper.transcribe(temp_path, language="en", beam_size=1)
            text = " ".join(seg.text for seg in segments).strip()
            os.unlink(temp_path)
            return text
        except Exception as e:
            logger.error("Whisper transcription failed: %s", e)
            return ""

    async def _synthesize_and_play(self, text: str) -> None:
        """Synthesize text to speech and emit AudioDeltaEvents."""
        if not text.strip():
            return

        try:
            if self.tts_engine == "piper":
                # Piper streaming synthesis
                audio_chunks = []
                for chunk in self._tts.synthesize_stream_raw(text):
                    audio_chunks.append(chunk)
                audio_data = b"".join(audio_chunks)
            elif self.tts_engine == "coqui":
                # Coqui synthesis
                wav = self._tts.tts(text=text, speaker_wav=None, language="en")
                audio_data = (np.array(wav) * 32767).astype(np.int16).tobytes()
            else:
                return

            # Emit as AudioDeltaEvents in chunks
            chunk_size = 4096
            for i in range(0, len(audio_data), chunk_size):
                chunk = audio_data[i : i + chunk_size]
                yield AudioDeltaEvent(data=chunk, sample_rate=OUTPUT_SAMPLE_RATE)

            yield TurnCompleteEvent()
        except Exception as e:
            logger.error("TTS synthesis failed: %s", e)

    async def receive(self) -> AsyncIterator[RealtimeEvent]:
        if not self.connected:
            raise RuntimeError("Not connected")

        # Start background processing
        process_task = asyncio.create_task(self._process_loop())

        try:
            while self._running:
                # Check output buffer
                output = await self._output_buffer.read(4096)
                if output:
                    yield AudioDeltaEvent(data=output, sample_rate=OUTPUT_SAMPLE_RATE)
                else:
                    await asyncio.sleep(0.01)
        finally:
            process_task.cancel()

    async def _process_loop(self) -> None:
        """Background loop processing input buffer."""
        while self._running:
            await asyncio.sleep(0.1)
            if len(self._input_buffer) > INPUT_SAMPLE_RATE * 2:  # 2 seconds
                async for event in self._process_input_buffer():
                    if event:
                        # Handle transcript
                        pass

    async def close(self) -> None:
        self._running = False
        await self._input_buffer.clear()
        await self._output_buffer.clear()
        if self._current_output_task:
            self._current_output_task.cancel()
        logger.info("Local Whisper+TTS closed")


__all__ = ["LocalWhisperTTSClient"]
