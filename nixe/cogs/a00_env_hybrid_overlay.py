# -*- coding: utf-8 -*-
"""Minimal env overlay.
Keep as no-op to avoid runtime_env.json warnings/noise.
"""

from __future__ import annotations

import logging
from discord.ext import commands

log = logging.getLogger(__name__)


class EnvHybridOverlay(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        log.info("[env-hybrid] overlay active (no-op)")


async def setup(bot: commands.Bot):
    await bot.add_cog(EnvHybridOverlay(bot))
