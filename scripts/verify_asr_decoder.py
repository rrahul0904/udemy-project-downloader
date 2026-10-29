#!/usr/bin/env python3
"""Fail the optional ASR image build if installed PyAV cannot decode audio.

This is a codec/dependency smoke test, not a claim of speech recognition quality.
Creates a short synthetic WAV in memory; downloads no model and uses no YouTube.
"""
from __future__ import annotations

import io
import math
import struct
import wave


def verify_decoder() -> dict[str, object]:
    import av
    from faster_whisper.audio import decode_audio

    sample_rate = 16000
    count = sample_rate // 2
    raw = b"".join(
        struct.pack("<h", round(4500 * math.sin(2 * math.pi * 440 * i / sample_rate)))
        for i in range(count)
    )
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(raw)
    buffer.seek(0)
    decoded = decode_audio(buffer, sampling_rate=sample_rate)
    if len(decoded) != count:
        raise RuntimeError(
            f"PyAV decoder returned {len(decoded)} samples, expected {count}."
        )
    return {"pyav": av.__version__, "decoded_samples": len(decoded), "status": "ok"}


if __name__ == "__main__":
    import json
    print(json.dumps(verify_decoder()))
