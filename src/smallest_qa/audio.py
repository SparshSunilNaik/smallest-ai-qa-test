"""Dependency-free audio inspection used for response-format assertions."""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass


@dataclass(frozen=True)
class WavInfo:
    channels: int
    sample_rate: int
    bits_per_sample: int
    audio_format: int  # 1 = PCM
    data_bytes: int
    data_offset: int
    declared_data_bytes: int

    @property
    def duration_s(self) -> float:
        frame = self.channels * self.bits_per_sample // 8
        return self.data_bytes / (frame * self.sample_rate) if frame and self.sample_rate else 0.0


class AudioFormatError(ValueError):
    pass


def parse_wav(data: bytes) -> WavInfo:
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise AudioFormatError("not a RIFF/WAVE container")
    pos = 12
    fmt = None
    while pos + 8 <= len(data):
        cid = data[pos : pos + 4]
        (size,) = struct.unpack_from("<I", data, pos + 4)
        body = pos + 8
        if cid == b"fmt ":
            if size < 16 or body + 16 > len(data):
                raise AudioFormatError("truncated fmt chunk")
            audio_format, channels, rate, _, _, bits = struct.unpack_from("<HHIIHH", data, body)
            fmt = (audio_format, channels, rate, bits)
        elif cid == b"data":
            if fmt is None:
                raise AudioFormatError("data chunk before fmt chunk")
            actual = len(data) - body
            # Streaming encoders may declare 0 or 0xFFFFFFFF; use what actually arrived.
            data_bytes = min(size, actual) if 0 < size < 0xFFFFFFFF else actual
            return WavInfo(fmt[1], fmt[2], fmt[3], fmt[0], data_bytes, body, size)
        pos = body + size + (size & 1)
    raise AudioFormatError("no data chunk found")


def looks_like_mp3(data: bytes) -> bool:
    if data[:3] == b"ID3":
        return True
    return len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0


def pcm16_rms_dbfs(pcm: bytes) -> float:
    """RMS level of little-endian signed 16-bit PCM in dBFS (-inf for digital silence)."""
    n = len(pcm) // 2
    if n == 0:
        return float("-inf")
    samples = struct.unpack(f"<{n}h", pcm[: n * 2])
    mean_sq = sum(s * s for s in samples) / n
    if mean_sq == 0:
        return float("-inf")
    return 20 * math.log10(math.sqrt(mean_sq) / 32768.0)
