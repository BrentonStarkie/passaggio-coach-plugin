"""Take library: config, index, and ingest under <takes_dir>/.passaggio/.

Pure-Python, cross-platform. The eventual MCP `takes-server` is a thin wrapper over this
module — its tools (list_takes, ingest_take, analyze_take, get_take, compare_takes,
annotate_take, set_profile) map 1:1 to methods here.

Layout:
  <takes_dir>/
  ├── <raw recordings, untouched>
  └── .passaggio/
      ├── config.json
      ├── library.json
      └── takes/<id>/{audio.wav, metrics.json, pitch.png, spectrogram.png, session.md}
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Optional

import soundfile as sf

from . import audio

DEFAULT_SR = 44100


def default_takes_dir() -> Path:
    return Path.home() / "VoiceTakes"


def _read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


class Store:
    def __init__(self, takes_dir=None):
        self.takes_dir = Path(takes_dir).expanduser() if takes_dir else default_takes_dir()
        self.pdir = self.takes_dir / ".passaggio"
        self.config_path = self.pdir / "config.json"
        self.library_path = self.pdir / "library.json"
        self.takes_root = self.pdir / "takes"

    # ---- setup -------------------------------------------------------------
    def ensure(self) -> "Store":
        self.takes_root.mkdir(parents=True, exist_ok=True)
        if not self.config_path.exists():
            _write_json(self.config_path, {
                "takes_dir": str(self.takes_dir),
                "voice_type": None,
                "passaggio_override": None,
                "sample_rate": DEFAULT_SR,
            })
        if not self.library_path.exists():
            _write_json(self.library_path, {"takes": []})
        return self

    # ---- config / profile --------------------------------------------------
    @property
    def config(self) -> dict:
        return _read_json(self.config_path, {
            "takes_dir": str(self.takes_dir), "voice_type": None,
            "passaggio_override": None, "sample_rate": DEFAULT_SR,
        })

    def profile(self) -> dict:
        c = self.config
        return {"voice_type": c.get("voice_type"),
                "passaggio_override": c.get("passaggio_override")}

    def set_profile(self, voice_type=None, passaggio_override=None) -> dict:
        c = self.config
        if voice_type is not None:
            c["voice_type"] = voice_type or None
        if passaggio_override is not None:
            c["passaggio_override"] = passaggio_override or None
        _write_json(self.config_path, c)
        return c

    # ---- library index -----------------------------------------------------
    def library(self) -> dict:
        return _read_json(self.library_path, {"takes": []})

    def _save_library(self, lib) -> None:
        _write_json(self.library_path, lib)

    def take_dir(self, take_id: str) -> Path:
        return self.takes_root / take_id

    def get_take(self, take_id: str) -> Optional[dict]:
        for t in self.library().get("takes", []):
            if t["id"] == take_id:
                return t
        return None

    def list_takes(self, status: Optional[str] = None, tag: Optional[str] = None) -> list:
        takes = self.library().get("takes", [])
        if status:
            takes = [t for t in takes if t.get("status") == status]
        if tag:
            takes = [t for t in takes if tag in (t.get("tags") or [])]
        return sorted(takes, key=lambda t: t.get("date", ""))

    def _new_id(self, when: _dt.datetime) -> str:
        base = "take-" + when.strftime("%Y-%m-%d-%H%M")
        existing = {t["id"] for t in self.library().get("takes", [])}
        if base not in existing:
            return base
        i = 2
        while f"{base}-{i}" in existing:
            i += 1
        return f"{base}-{i}"

    # ---- ingest ------------------------------------------------------------
    def ingest(self, src_path, take_id: Optional[str] = None,
               when_iso: Optional[str] = None, sr: int = DEFAULT_SR) -> dict:
        """Convert a raw recording to normalised mono 16-bit WAV, copy into the library,
        validate duration, and index it. Returns the library record (with warnings)."""
        self.ensure()
        src = Path(src_path).expanduser()
        if not src.exists():
            raise FileNotFoundError(f"Recording not found: {src}")

        when = _dt.datetime.fromisoformat(when_iso) if when_iso else _dt.datetime.now()
        take_id = take_id or self._new_id(when)
        tdir = self.take_dir(take_id)
        tdir.mkdir(parents=True, exist_ok=True)
        wav = tdir / "audio.wav"
        audio.convert_to_wav(src, wav, sr=sr)

        info = sf.info(str(wav))
        duration = float(info.frames) / float(info.samplerate)
        warnings = []
        if duration < 5.0:
            warnings.append(f"Very short take ({duration:.1f}s < 5s) — may be too little to analyse.")
        elif duration > 60.0:
            warnings.append(f"Long take ({duration:.1f}s > 60s) — expected ~20s.")
        elif not (15.0 <= duration <= 25.0):
            warnings.append(f"Take is {duration:.1f}s; the sweet spot is ~15-25s.")

        record = {
            "id": take_id,
            "date": when.isoformat(timespec="seconds"),
            "source_file": str(src),
            "audio": str(wav.relative_to(self.pdir)).replace("\\", "/"),
            "status": "ingested",
            "duration_s": round(duration, 2),
            "tags": [],
            "notes": "",
            "headline": {},
            "warnings": warnings,
        }
        lib = self.library()
        lib["takes"] = [t for t in lib.get("takes", []) if t["id"] != take_id] + [record]
        self._save_library(lib)
        return record

    # ---- analysis + annotation --------------------------------------------
    def register_analysis(self, take_id: str, metrics: dict) -> dict:
        tdir = self.take_dir(take_id)
        _write_json(tdir / "metrics.json", metrics)
        lib = self.library()
        rec = None
        for t in lib.get("takes", []):
            if t["id"] == take_id:
                t["status"] = "analysed"
                t["headline"] = metrics.get("headline", {})
                t["voice_type_at_analysis"] = (metrics.get("zone") or {}).get("source")
                rec = t
                break
        self._save_library(lib)
        return rec or {}

    def annotate_take(self, take_id: str, notes: Optional[str] = None,
                      tags: Optional[list] = None, summary: Optional[str] = None) -> dict:
        lib = self.library()
        rec = None
        for t in lib.get("takes", []):
            if t["id"] == take_id:
                if notes is not None:
                    t["notes"] = notes
                if tags is not None:
                    t["tags"] = sorted(set((t.get("tags") or []) + list(tags)))
                rec = t
                break
        if rec is None:
            raise KeyError(f"No take with id {take_id}")
        self._save_library(lib)
        if summary:
            self.append_session(take_id, summary)
        return rec

    def append_session(self, take_id: str, markdown: str) -> Path:
        path = self.take_dir(take_id) / "session.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(markdown.rstrip() + "\n\n")
        return path
