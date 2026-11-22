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


# ----------------------------------------------------------------------------- Phase 2 analysis

def pcm16_samples(pcm: bytes) -> list[int]:
    n = len(pcm) // 2
    return list(struct.unpack(f"<{n}h", pcm[: n * 2]))


def analyze_pcm16(pcm: bytes, sample_rate: int, silence_threshold: int = 500, frame_ms: int = 20) -> dict:
    """Machine-verifiable integrity metrics. These say nothing about pronunciation or naturalness."""
    samples = pcm16_samples(pcm)
    if not samples:
        return {"samples": 0}
    peak = max(abs(s) for s in samples)
    clipped = sum(1 for s in samples if abs(s) >= 32767)
    frame = max(1, sample_rate * frame_ms // 1000)
    voiced = [max(abs(s) for s in samples[i : i + frame]) > silence_threshold for i in range(0, len(samples), frame)]
    first = next((i for i, v in enumerate(voiced) if v), None)
    last = next((i for i in range(len(voiced) - 1, -1, -1) if voiced[i]), None)
    longest_gap = gap = 0
    if first is not None:
        for v in voiced[first : last + 1]:
            gap = 0 if v else gap + 1
            longest_gap = max(longest_gap, gap)
    return {
        "samples": len(samples),
        "duration_s": round(len(samples) / sample_rate, 3),
        "rms_dbfs": round(pcm16_rms_dbfs(pcm), 1) if peak else None,
        "peak": peak,
        "clipped_fraction": round(clipped / len(samples), 5),
        "leading_silence_ms": None if first is None else first * frame_ms,
        "trailing_silence_ms": None if last is None else (len(voiced) - 1 - last) * frame_ms,
        "longest_internal_silence_ms": longest_gap * frame_ms,
        "all_silent": first is None,
    }


def mulaw_to_pcm16(data: bytes) -> bytes:
    """ITU-T G.711 mu-law decode."""
    out = bytearray()
    for b in data:
        u = ~b & 0xFF
        sign, exponent, mantissa = u & 0x80, (u >> 4) & 0x07, u & 0x0F
        magnitude = ((mantissa << 3) + 0x84) << exponent
        value = (magnitude - 0x84) * (-1 if sign else 1)
        out += struct.pack("<h", max(-32768, min(32767, value)))
    return bytes(out)


def pcm16_to_wav(pcm: bytes, sample_rate: int, channels: int = 1) -> bytes:
    header = struct.pack("<4sI4s4sIHHIIHH4sI", b"RIFF", 36 + len(pcm), b"WAVE", b"fmt ", 16, 1, channels,
                         sample_rate, sample_rate * channels * 2, channels * 2, 16, b"data", len(pcm))
    return header + pcm


def wav_pcm16(data: bytes) -> tuple[bytes, int]:
    info = parse_wav(data)
    if info.bits_per_sample != 16 or info.channels != 1 or info.audio_format != 1:
        raise AudioFormatError(f"expected mono 16-bit PCM, got {info}")
    return data[info.data_offset : info.data_offset + info.data_bytes], info.sample_rate


def resample_linear(pcm: bytes, src_rate: int, dst_rate: int) -> bytes:
    s = pcm16_samples(pcm)
    if not s or src_rate == dst_rate:
        return pcm
    n_out = int(len(s) * dst_rate / src_rate)
    out = []
    for i in range(n_out):
        x = i * src_rate / dst_rate
        j = int(x)
        frac = x - j
        a, b = s[min(j, len(s) - 1)], s[min(j + 1, len(s) - 1)]
        out.append(int(round(a + (b - a) * frac)))
    return struct.pack(f"<{len(out)}h", *out)


def add_white_noise(pcm: bytes, snr_db: float, seed: int) -> bytes:
    """Add seeded Gaussian noise at the given SNR relative to the signal RMS (deterministic)."""
    import random

    s = pcm16_samples(pcm)
    rms = math.sqrt(sum(v * v for v in s) / len(s))
    noise_rms = rms / (10 ** (snr_db / 20))
    rng = random.Random(seed)
    out = [max(-32768, min(32767, int(v + rng.gauss(0, noise_rms)))) for v in s]
    return struct.pack(f"<{len(out)}h", *out)


def noise_only(seconds: float, rate: int, dbfs: float, seed: int) -> bytes:
    import random

    rng = random.Random(seed)
    sigma = 32768 * 10 ** (dbfs / 20)
    n = int(seconds * rate)
    out = [max(-32768, min(32767, int(rng.gauss(0, sigma)))) for _ in range(n)]
    return struct.pack(f"<{n}h", *out)


def silence_pcm(seconds: float, rate: int) -> bytes:
    return b"\x00\x00" * int(seconds * rate)
