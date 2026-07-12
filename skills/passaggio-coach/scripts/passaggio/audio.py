"""Audio loading and conversion. Cross-platform (Windows / macOS).

WAV / AIFF / FLAC are read directly with soundfile and need no ffmpeg. Compressed inputs
(.m4a from Voice Memos, .mp3) require ffmpeg on PATH; we detect it and give a clear error
if it is missing rather than failing obscurely.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

UNCOMPRESSED = {".wav", ".aiff", ".aif", ".flac", ".ogg"}
NEEDS_FFMPEG = {".m4a", ".mp3", ".mp4", ".aac", ".m4b"}
TARGET_SR = 44100


def ffmpeg_path() -> str | None:
    return shutil.which("ffmpeg")


def _to_mono(y: np.ndarray) -> np.ndarray:
    if y.ndim == 2:
        y = y.mean(axis=1)
    return np.ascontiguousarray(y, dtype=np.float64)


def load_audio(path, target_sr: int = TARGET_SR):
    """Return (y_mono_float64, sr). Resamples to target_sr. Handles compressed via ffmpeg."""
    path = Path(path)
    suffix = path.suffix.lower()
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")

    if suffix in UNCOMPRESSED:
        y, sr = sf.read(str(path), always_2d=False)
        y = _to_mono(np.asarray(y))
    elif suffix in NEEDS_FFMPEG:
        fp = ffmpeg_path()
        if not fp:
            raise RuntimeError(
                f"'{suffix}' input requires ffmpeg, which was not found on PATH.\n"
                "  macOS:   brew install ffmpeg\n"
                "  Windows: winget install Gyan.FFmpeg\n"
                "Or export/save the recording as WAV, which needs no ffmpeg."
            )
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td) / "conv.wav"
            _ffmpeg_to_wav(fp, path, tmp, target_sr)
            y, sr = sf.read(str(tmp), always_2d=False)
            y = _to_mono(np.asarray(y))
    else:
        raise ValueError(f"Unsupported audio format: {suffix}")

    if sr != target_sr:
        import librosa
        y = librosa.resample(y, orig_sr=sr, target_sr=target_sr)
        sr = target_sr
    return y, sr


def _ffmpeg_to_wav(fp: str, src: Path, dst: Path, sr: int, channels: int = 1) -> None:
    cmd = [fp, "-nostdin", "-y", "-i", str(src), "-ac", str(channels), "-ar", str(sr),
           "-c:a", "pcm_s16le", str(dst)]
    # stdin=DEVNULL (+ -nostdin): ffmpeg must not consume stdin, and the child must not inherit
    # the MCP server's stdin pipe (that deadlocks on Windows when ingesting under the connector).
    proc = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg conversion failed:\n{proc.stderr[-800:]}")


def convert_to_wav(src, dst, sr: int = TARGET_SR) -> Path:
    """Normalise any supported input to mono 16-bit PCM WAV @ sr (the library's stored form).

    Uses ffmpeg for compressed inputs; for uncompressed inputs falls back to a pure-Python
    path (soundfile + librosa) so no ffmpeg is needed for WAV/AIFF/FLAC.
    """
    src, dst = Path(src), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    suffix = src.suffix.lower()

    if suffix in NEEDS_FFMPEG:
        fp = ffmpeg_path()
        if not fp:
            raise RuntimeError(
                f"Converting '{suffix}' requires ffmpeg (not found on PATH). "
                "Install it (macOS: brew install ffmpeg) or provide a WAV."
            )
        _ffmpeg_to_wav(fp, src, dst, sr)
        return dst

    # Uncompressed: read, downmix, resample, write PCM_16 — no ffmpeg needed.
    y, in_sr = sf.read(str(src), always_2d=False)
    y = _to_mono(np.asarray(y))
    if in_sr != sr:
        import librosa
        y = librosa.resample(y, orig_sr=in_sr, target_sr=sr)
    peak = float(np.max(np.abs(y))) if y.size else 0.0
    if peak > 1.0:
        y = y / peak
    sf.write(str(dst), y.astype(np.float32), sr, subtype="PCM_16")
    return dst
