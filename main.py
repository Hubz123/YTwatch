# -*- coding: utf-8 -*-
"""
Wuthering Waves — YouTube Watchlist only (Render Free ready)

Runs:
- Discord bot (loads ONLY YouTube watchlist cog)
- Lightweight /healthz HTTP endpoint on $PORT (Render requirement)
"""
from __future__ import annotations

import os
import asyncio
import logging
from logging.config import dictConfig

import discord
from discord.ext import commands

from aiohttp import web


def setup_logging() -> None:
    level = os.getenv("LOG_LEVEL", os.getenv("PYTHON_LOGLEVEL", "INFO")).upper()
    dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"std": {"format": "%(asctime)s %(levelname)s:%(name)s:%(message)s"}},
        "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "std", "level": level}},
        "root": {"handlers": ["console"], "level": level},
    })
    try:
        # discord.py helper (optional)
        if hasattr(discord.utils, "setup_logging"):
            discord.utils.setup_logging(level=(logging.DEBUG if level == "DEBUG" else logging.INFO))
    except Exception:
        pass


async def start_health_server() -> tuple[web.AppRunner, web.TCPSite]:
    app = web.Application()

    async def healthz(_req: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "service": "wuthering-waves"})

    async def index(_req: web.Request) -> web.Response:
        return web.Response(text="Wuthering Waves OK")

    app.router.add_get("/healthz", healthz)
    app.router.add_get("/", index)

    runner = web.AppRunner(app, access_log=None)
    await runner.setup()

    port = int(os.getenv("PORT", "8080"))
    host = os.getenv("HOST", "0.0.0.0")
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
    logging.getLogger("wuthering-waves.health").info("health server up on %s:%s", host, port)
    return runner, site


class WutheringWavesBot(commands.Bot):
    async def setup_hook(self) -> None:
        from nixe import cogs_loader
        loaded = await cogs_loader.load_all(self)
        logging.getLogger("wuthering-waves.bot").info("Loaded cogs: %s", loaded)


async def main() -> None:
    setup_logging()
    log = logging.getLogger("wuthering-waves.main")

    token = (os.getenv("DISCORD_TOKEN") or "").strip()
    if not token:
        raise SystemExit("DISCORD_TOKEN belum diset.")

    intents = discord.Intents.default()
    intents.guilds = True
    intents.messages = True
    intents.message_content = True

    bot = WutheringWavesBot(command_prefix=os.getenv("COMMAND_PREFIX", "!"), intents=intents)

    runner = None
    try:
        runner, _site = await start_health_server()
        async with bot:
            await bot.start(token)
    finally:
        if runner is not None:
            try:
                await runner.cleanup()
            except Exception:
                pass
        log.info("shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
