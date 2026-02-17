# -*- coding: utf-8 -*-
"""Cogs loader — HARD allowlist for YouTube watchlist only."""

from __future__ import annotations

import logging
from typing import List

log = logging.getLogger("nixe.cogs_loader")

COGS_ONLY = [
    "nixe.cogs.a00_env_hybrid_overlay",
    "nixe.cogs.a21_youtube_wuwa_live_announce",
]


async def load_all(bot) -> List[str]:
    loaded: List[str] = []
    for name in COGS_ONLY:
        try:
            await bot.load_extension(name)
            loaded.append(name)
        except Exception as e:
            log.critical("Failed to load cog %s: %r", name, e, exc_info=True)
            raise
    return loaded
