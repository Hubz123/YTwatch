# -*- coding: utf-8 -*-
"""Wuthering Waves — YouTube watchlist (uploads + live) + Render healthz.

Env:
- DISCORD_TOKEN (required)
- PORT (Render provides)
"""

import os
import asyncio
import logging

import discord
from discord.ext import commands
from aiohttp import web

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s:%(name)s:%(message)s",
)

log = logging.getLogger("wuthering-waves.main")


async def _start_health_server() -> None:
    logger = logging.getLogger("wuthering-waves.health")

    async def healthz(_req: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "service": "wuthering-waves"})

    async def index(_req: web.Request) -> web.Response:
        return web.Response(text="Wuthering Waves OK")

    app = web.Application()
    # Accept any method (some monitors use HEAD)
    app.router.add_route("*", "/healthz", healthz)
    app.router.add_route("*", "/", index)

    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("health server up on 0.0.0.0:%s", port)


INTENTS = discord.Intents.default()
INTENTS.guilds = True
INTENTS.messages = True
INTENTS.message_content = True


class WutheringWavesBot(commands.Bot):
    async def setup_hook(self) -> None:
        from nixe import cogs_loader
        loaded = await cogs_loader.load_all(self)
        logging.getLogger("wuthering-waves.bot").info("Loaded cogs: %s", loaded)


async def main() -> None:
    token = (os.getenv("DISCORD_TOKEN") or "").strip()
    if not token:
        raise SystemExit("DISCORD_TOKEN belum diset.")

    bot = WutheringWavesBot(command_prefix=os.getenv("COMMAND_PREFIX", "!"), intents=INTENTS)

    # health server must be up for Render free plan
    await _start_health_server()

    async with bot:
        await bot.start(token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("shutdown complete")
