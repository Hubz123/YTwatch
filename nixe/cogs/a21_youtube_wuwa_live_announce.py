# -*- coding: utf-8 -*-
"""YouTube watch (uploads + live) for a single channel, with strict no-dupe.

Behavior:
- Poll YouTube RSS feed for channel_id.
- Announce only *new* items:
  - If ONLY_NEW_AFTER_BOOT=1: skip items published before bot boot time.
  - If ANNOUNCE_MAX_AGE_MINUTES is set: skip items older than that many minutes.
- De-duplicate by videoId (title edits will NOT re-announce).
- Message format (2 lines) so Discord auto-embeds YouTube preview:
    <@USER_ID> {title}
    {url}

Env (defaults chosen to match your requirements):
- NIXE_YT_CHANNEL_ID                 (default UC60o6OxOsqZpTq7xca8IL4w)
- NIXE_YT_ANNOUNCE_CHANNEL_ID        (default 1472521135680786606)
- NIXE_YT_NOTIFY_USER_ID             (default 1473338687428235397)  # user mention (NOT role)
- NIXE_YT_ANNOUNCE_ENABLE            (default 1)
- NIXE_YT_POLL_SECONDS               (default 60)
- NIXE_YT_ONLY_NEW_AFTER_BOOT         (default 1)
- NIXE_YT_ANNOUNCE_MAX_AGE_MINUTES    (default 10)
- NIXE_YT_STATE_PATH                  (default data/youtube_wuwa_state.json)
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import os
from dataclasses import dataclass
from typing import Optional, Set, Tuple

import aiohttp
import discord
from discord.ext import commands, tasks
from xml.etree import ElementTree as ET

log = logging.getLogger(__name__)

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
}

@dataclass(frozen=True)
class FeedItem:
    video_id: str
    title: str
    url: str
    published: dt.datetime  # aware UTC


def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool01(name: str, default: int) -> bool:
    return (os.getenv(name, str(default)).strip() == "1")


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _parse_rfc3339(ts: str) -> Optional[dt.datetime]:
    ts = (ts or "").strip()
    if not ts:
        return None
    # example: 2026-02-18T10:09:00+00:00 or 2026-02-18T10:09:00Z
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return dt.datetime.fromisoformat(ts).astimezone(dt.timezone.utc)
    except Exception:
        return None


def _load_state(path: str) -> Set[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        ids = obj.get("announced_video_ids", [])
        if isinstance(ids, list):
            return {str(x) for x in ids}
    except FileNotFoundError:
        pass
    except Exception as e:
        log.warning("[yt] state read failed: %s (%r)", path, e)
    return set()


def _save_state(path: str, announced: Set[str]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"announced_video_ids": sorted(announced)}, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


async def _fetch_feed(session: aiohttp.ClientSession, channel_id: str) -> Tuple[int, str]:
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
        text = await resp.text()
        return resp.status, text


def _parse_feed(xml_text: str) -> list[FeedItem]:
    items: list[FeedItem] = []
    root = ET.fromstring(xml_text)
    for entry in root.findall("atom:entry", NS):
        vid = entry.findtext("yt:videoId", default="", namespaces=NS).strip()
        title = entry.findtext("atom:title", default="", namespaces=NS).strip()
        published_s = entry.findtext("atom:published", default="", namespaces=NS).strip()
        published = _parse_rfc3339(published_s) or _utcnow()
        link_el = entry.find("atom:link[@rel='alternate']", NS)
        href = ""
        if link_el is not None:
            href = (link_el.attrib.get("href") or "").strip()
        if not href and vid:
            href = f"https://www.youtube.com/watch?v={vid}"
        if vid:
            items.append(FeedItem(video_id=vid, title=title or "(untitled)", url=href, published=published))
    # newest first
    items.sort(key=lambda x: x.published, reverse=True)
    return items


class YouTubeWatchCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        self.channel_id = os.getenv("NIXE_YT_CHANNEL_ID", "UC60o6OxOsqZpTq7xca8IL4w").strip()
        self.announce_channel_id = int(os.getenv("NIXE_YT_ANNOUNCE_CHANNEL_ID", "1472521135680786606").strip())
        self.notify_user_id = int(os.getenv("NIXE_YT_NOTIFY_USER_ID", "1473338687428235397").strip())

        self.enabled = _env_bool01("NIXE_YT_ANNOUNCE_ENABLE", 1)
        self.poll_seconds = max(20, _env_int("NIXE_YT_POLL_SECONDS", 60))
        self.only_new_after_boot = _env_bool01("NIXE_YT_ONLY_NEW_AFTER_BOOT", 1)
        self.max_age_minutes = max(1, _env_int("NIXE_YT_ANNOUNCE_MAX_AGE_MINUTES", 10))

        self.state_path = os.getenv("NIXE_YT_STATE_PATH", "data/youtube_wuwa_state.json").strip()
        self.announced: Set[str] = _load_state(self.state_path)

        self.boot_time = _utcnow()

        self.session: Optional[aiohttp.ClientSession] = None

        log.info(
            "[yt] config: enabled=%s channel_id=%s announce_channel_id=%s notify_user_id=%s poll=%ss only_new_after_boot=%s max_age_min=%s state=%s announced=%s",
            self.enabled, self.channel_id, self.announce_channel_id, self.notify_user_id,
            self.poll_seconds, self.only_new_after_boot, self.max_age_minutes, self.state_path, len(self.announced)
        )

        self.poll_loop.change_interval(seconds=self.poll_seconds)
        self.poll_loop.start()

        # Force check once after bot is ready (so you don't have to wait a full interval)
        self.bot.loop.create_task(self._force_check_on_ready())

    async def cog_unload(self):
        self.poll_loop.cancel()
        if self.session and not self.session.closed:
            await self.session.close()

    async def _force_check_on_ready(self) -> None:
        try:
            await self.bot.wait_until_ready()
            # slight delay so gateway settle
            await asyncio.sleep(2)
            log.info("[yt] force-check on boot: starting")
            await self._check_once()
        except Exception:
            log.exception("[yt] force-check failed")

    def _should_skip(self, item: FeedItem) -> Tuple[bool, str]:
        if item.video_id in self.announced:
            return True, "duplicate(videoId)"
        age_min = int((_utcnow() - item.published).total_seconds() / 60)
        if age_min > self.max_age_minutes:
            return True, f"stale(age_min={age_min} > {self.max_age_minutes})"
        if self.only_new_after_boot and item.published < self.boot_time:
            return True, "before_boot"
        return False, f"ok(age_min={age_min})"

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self.session and not self.session.closed:
            return self.session
        self.session = aiohttp.ClientSession(headers={"User-Agent": "WutheringWavesBot/1.0"})
        return self.session

    async def _check_once(self) -> None:
        if not self.enabled:
            log.info("[yt] announce disabled (NIXE_YT_ANNOUNCE_ENABLE!=1)")
            return

        session = await self._ensure_session()

        status, text = await _fetch_feed(session, self.channel_id)
        log.info("[yt] rss fetch status=%s bytes=%s", status, len(text or ""))
        if status != 200 or not text:
            log.warning("[yt] rss fetch failed status=%s", status)
            return

        try:
            items = _parse_feed(text)
        except Exception as e:
            log.warning("[yt] rss parse failed: %r", e, exc_info=True)
            return

        if not items:
            log.info("[yt] rss parse ok but no entries")
            return

        newest = items[0]
        log.info("[yt] newest: vid=%s published=%s title=%s", newest.video_id, newest.published.isoformat(), (newest.title[:80]))

        # Announce the newest item that passes gates (newest-first)
        for item in items:
            skip, reason = self._should_skip(item)
            log.info("[yt] consider vid=%s => %s", item.video_id, reason)
            if skip:
                continue
            await self._announce(item)
            break

    async def _announce(self, item: FeedItem) -> None:
        ch = self.bot.get_channel(self.announce_channel_id)
        if ch is None:
            # try fetch
            try:
                ch = await self.bot.fetch_channel(self.announce_channel_id)
            except Exception:
                log.exception("[yt] cannot fetch announce channel id=%s", self.announce_channel_id)
                return
        if not isinstance(ch, (discord.TextChannel, discord.Thread)):
            log.warning("[yt] announce channel is not text/thread: %r", ch)
            return

        mention = f"<@{self.notify_user_id}>"
        msg = f"{mention} {item.title}\n{item.url}"
        try:
            await ch.send(msg, allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False))
        except Exception:
            log.exception("[yt] send failed to channel=%s", self.announce_channel_id)
            return

        self.announced.add(item.video_id)
        try:
            _save_state(self.state_path, self.announced)
        except Exception:
            log.exception("[yt] failed saving state")
        log.info("[yt] announced: vid=%s", item.video_id)

    @tasks.loop(seconds=60)
    async def poll_loop(self) -> None:
        try:
            await self._check_once()
        except Exception:
            log.exception("[yt] poll loop error")


async def setup(bot: commands.Bot):
    await bot.add_cog(YouTubeWatchCog(bot))
