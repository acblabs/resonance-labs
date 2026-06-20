"""Small WAV/PCM decoder for the Phase 1 upload loop."""

from __future__ import annotations

import wave
from dataclasses import dataclass
from io import BytesIO

import numpy as np
import numpy.typing as npt


class WavDecodeError(ValueError):
    """Raised when an uploaded WAV cannot be decoded as PCM audio."""


@dataclass(frozen=True)
class DecodedAudio:
    """Decoded mono audio plus the original stream metadata."""

    sample_rate_hz: int
    channels: int
    sample_width_bytes: int
    frame_count: int
    samples: npt.NDArray[np.float64]

    @property
    def duration_seconds(self) -> float:
        if self.sample_rate_hz <= 0:
            return 0.0
        return self.frame_count / self.sample_rate_hz


def decode_wav_pcm(data: bytes) -> DecodedAudio:
    """Decode a PCM WAV byte string to normalized mono float samples."""

    if not data:
        raise WavDecodeError("The uploaded audio file is empty.")

    try:
        with wave.open(BytesIO(data), "rb") as reader:
            channels = reader.getnchannels()
            sample_rate_hz = reader.getframerate()
            sample_width_bytes = reader.getsampwidth()
            frame_count = reader.getnframes()
            compression = reader.getcomptype()
            raw_frames = reader.readframes(frame_count)
    except (EOFError, wave.Error) as exc:
        raise WavDecodeError(f"Could not decode WAV audio: {exc}") from exc

    if compression != "NONE":
        raise WavDecodeError("Only uncompressed PCM WAV uploads are supported in Phase 1.")
    if channels < 1:
        raise WavDecodeError("WAV audio must contain at least one channel.")
    if sample_rate_hz <= 0:
        raise WavDecodeError("WAV audio has an invalid sample rate.")
    if sample_width_bytes not in (1, 2, 3, 4):
        raise WavDecodeError(f"Unsupported PCM sample width: {sample_width_bytes} bytes.")
    if frame_count <= 0:
        raise WavDecodeError("WAV audio contains no frames.")

    interleaved = _decode_interleaved_pcm(raw_frames, sample_width_bytes)
    expected_values = frame_count * channels
    if interleaved.size != expected_values:
        raise WavDecodeError(
            f"WAV data length mismatch: expected {expected_values} samples, "
            f"decoded {interleaved.size}."
        )

    mono = _mix_to_mono(interleaved, channels)
    return DecodedAudio(
        sample_rate_hz=sample_rate_hz,
        channels=channels,
        sample_width_bytes=sample_width_bytes,
        frame_count=frame_count,
        samples=mono,
    )


def _decode_interleaved_pcm(raw_frames: bytes, sample_width_bytes: int) -> npt.NDArray[np.float64]:
    if len(raw_frames) % sample_width_bytes != 0:
        raise WavDecodeError("Malformed PCM frame data.")

    if sample_width_bytes == 1:
        samples = np.frombuffer(raw_frames, dtype=np.uint8).astype(np.float64)
        return (samples - 128.0) / 128.0

    if sample_width_bytes == 2:
        samples = np.frombuffer(raw_frames, dtype="<i2").astype(np.float64)
        return samples / 32768.0

    if sample_width_bytes == 3:
        bytes_view = np.frombuffer(raw_frames, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        samples = bytes_view[:, 0] | (bytes_view[:, 1] << 8) | (bytes_view[:, 2] << 16)
        samples = np.where(samples & 0x800000, samples - 0x1000000, samples)
        return samples.astype(np.float64) / 8388608.0

    samples = np.frombuffer(raw_frames, dtype="<i4").astype(np.float64)
    return samples / 2147483648.0


def _mix_to_mono(
    interleaved: npt.NDArray[np.float64], channels: int
) -> npt.NDArray[np.float64]:
    if channels == 1:
        return interleaved

    return interleaved.reshape(-1, channels).mean(axis=1)
