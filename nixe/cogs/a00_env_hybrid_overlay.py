# -*- coding: utf-8 -*-
# a00_env_hybrid_overlay.py — safe env merge
from __future__ import annotations
import os, json, logging
from pathlib import Path
from typing import Dict, Any

log = logging.getLogger(__name__)

def _should_skip(v: Any) -> bool:
    if v is None:
        return True
    s = str(v).strip()
    return s == "" or s.lower() in {"none", "null"}

def _merge_env_from_json(path: str, *, prefer_env: bool = True) -> Dict[str, str]:
    p = Path(path)
    if not p.exists():
        log.warning("[env-hybrid] json not found: %s", p)
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("[env-hybrid] json read error: %r", e)
        return {}
    exported: Dict[str, str] = {}
    for k, v in (data or {}).items():
        if _should_skip(v):
            continue  # don't overwrite with empty/"None"
        if prefer_env and k in os.environ and str(os.environ[k]).strip() != "":
            continue  # keep .env/Render value
        os.environ[k] = str(v)
        exported[k] = str(v)
    return exported

async def setup(bot):
    # Allow override path via ENV_HYBRID_JSON_PATH, default to nixe/config/runtime_env.json
    # Allow override path via NIXE_RUNTIME_ENV_PATH or ENV_HYBRID_JSON_PATH, default to nixe/config/runtime_env.json
    path = os.getenv("NIXE_RUNTIME_ENV_PATH") or os.getenv("ENV_HYBRID_JSON_PATH") or "nixe/config/runtime_env.json"
    prefer_env = (os.getenv("ENV_HYBRID_PREFER_ENV", "1") == "1")
    exported = _merge_env_from_json(path, prefer_env=prefer_env)
    # LPG key rename compatibility:
    # - Preferred: LPG_API_*
    # - Legacy: GEMINI_* (historically used for LPG Groq keys in this repo)
    # This DOES NOT modify any JSON; it only mirrors env vars at runtime.

    # Short preview (sensitive keys redacted)
    preview = {k: ("***" if "KEY" in k or "TOKEN" in k else v) for k, v in list(exported.items())[:7]}
    log.warning("[env-hybrid] exported %d key(s) from %s; prefer_env=%s; preview=%s",
                len(exported), path, prefer_env, preview)
