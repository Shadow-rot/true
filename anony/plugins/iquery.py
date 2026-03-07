from __future__ import annotations

import asyncio
import urllib.parse
import re
import uuid
from pathlib import Path
from typing import Optional

from pyrogram import types, enums
from py_yt import VideosSearch
import aiohttp

from anony import app, config

# ── Persistent HTTP session (created once, reused forever) ────────────────────
_connector = aiohttp.TCPConnector(
    limit=50,                # max simultaneous connections
    ttl_dns_cache=300,       # cache DNS for 5 min
    use_dns_cache=True,
    keepalive_timeout=60,
)
_session: Optional[aiohttp.ClientSession] = None

def _get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            connector=_connector,
            connector_owner=False,
            timeout=aiohttp.ClientTimeout(total=20, connect=5),
            headers={
                "X-API-Key": config.API_KEY,
                "Accept":    "application/json",
            },
        )
    return _session

# ── Download dir ──────────────────────────────────────────────────────────────
_DL_DIR = Path("downloads")
_DL_DIR.mkdir(exist_ok=True)

_API_BASE = None   # resolved once below

def _api_base() -> str:
    global _API_BASE
    if _API_BASE is None:
        _API_BASE = config.API_URL.rstrip("/")
    return _API_BASE

# ── In-memory caches ──────────────────────────────────────────────────────────
_meta: dict[str, dict]        = {}
_fid:  dict[str, str]         = {}   # vid_id → telegram file_id
_path: dict[str, str]         = {}   # vid_id → local file path
_lock: dict[str, asyncio.Lock] = {}
_pre:  set[str]               = set()

_EXT_RE   = re.compile(r'\.(\w{2,4})(?:\?|$)')
_VID_RE   = re.compile(
    r'(?:youtube\.com/(?:watch\?v=|shorts/|embed/)|youtu\.be/)([A-Za-z0-9_-]{11})'
)

def _get_lock(vid: str) -> asyncio.Lock:
    if vid not in _lock:
        _lock[vid] = asyncio.Lock()
    return _lock[vid]

def _disk_cached(vid: str) -> Optional[str]:
    for ext in ("webm", "mp3", "m4a", "opus", "mp4"):
        p = _DL_DIR / f"{vid}.{ext}"
        if p.is_file():
            return str(p)
    return None

def _is_ready(vid: str) -> bool:
    return vid in _fid or vid in _path or bool(_disk_cached(vid))

# ── Core: direct API call ─────────────────────────────────────────────────────
async def _api_get_track(yt_url: str) -> Optional[str]:
    """
    Hit /api/track directly and return a CDN/download URL.
    Single attempt, no retries — speed over resilience for prefetch.
    """
    endpoint = f"{_api_base()}/api/track?url={urllib.parse.quote(yt_url, safe='')}"
    try:
        async with _get_session().get(endpoint) as resp:
            if resp.status != 200:
                return None
            data = await resp.json(content_type=None)
            return data.get("cdnurl") or data.get("url") or None
    except Exception:
        return None

async def _download_cdn(cdn_url: str, vid: str) -> Optional[str]:
    """Stream CDN URL straight to disk using the shared session."""
    m   = _EXT_RE.search(cdn_url)
    ext = m.group(1) if m else "mp3"
    out = _DL_DIR / f"{vid}.{ext}"

    if out.is_file():
        return str(out)

    try:
        async with _get_session().get(cdn_url) as resp:
            if resp.status != 200:
                return None
            with open(out, "wb") as f:
                async for chunk in resp.content.iter_chunked(128 * 1024):
                    if chunk:
                        f.write(chunk)
        return str(out)
    except Exception:
        out.unlink(missing_ok=True)
        return None

async def _fetch_and_store(vid: str) -> Optional[str]:
    """Full pipeline: cache check → API → CDN download. Returns local path."""
    # 1. memory path cache
    if vid in _path:
        return _path[vid]

    # 2. disk cache
    cached = _disk_cached(vid)
    if cached:
        _path[vid] = cached
        return cached

    # 3. FallenAPI → CDN download
    url     = f"https://www.youtube.com/watch?v={vid}"
    cdn_url = await _api_get_track(url)
    if not cdn_url:
        return None

    # Handle Telegram message links (t.me/channel/msg_id)
    tg = re.match(r"https?://t\.me/([^/]+)/(\d+)", cdn_url)
    if tg:
        chat, msg_id = tg.groups()
        try:
            msg  = await app.get_messages(chat_id=chat, message_ids=int(msg_id))
            dest = str(_DL_DIR / f"{vid}.mp3")
            fp   = await msg.download(file_name=dest)
            if fp:
                _path[vid] = fp
            return fp
        except Exception:
            return None

    # CDN download
    fp = await _download_cdn(cdn_url, vid)
    if fp:
        _path[vid] = fp
    return fp

# ── Background prefetch ───────────────────────────────────────────────────────
async def _prefetch(vid: str) -> None:
    if vid in _pre or _is_ready(vid):
        return
    _pre.add(vid)
    try:
        async with _get_lock(vid):
            if _is_ready(vid):
                return
            await _fetch_and_store(vid)
    except Exception:
        pass
    finally:
        _pre.discard(vid)

# ── Inline search ─────────────────────────────────────────────────────────────
@app.on_inline_query()
async def inline_search(_, query: types.InlineQuery):
    text = query.query.strip()

    if not text:
        await app.answer_inline_query(
            query.id, results=[],
            switch_pm_text="🎵 Type a song name to search",
            switch_pm_parameter="start",
            cache_time=0,
        )
        return

    try:
        raw     = await VideosSearch(text, limit=10).next()
        results = raw.get("result", [])

        answers: list[types.InlineQueryResultArticle] = []
        to_fetch: list[str] = []

        for v in results:
            vid      = v.get("id", "")
            title    = v.get("title", "Unknown")
            duration = v.get("duration", "N/A")
            views    = v.get("viewCount", {}).get("short", "N/A")
            channel  = v.get("channel", {}).get("name", "Unknown")
            if not vid:
                continue

            _meta[vid] = {"title": title, "performer": channel}
            tag = "⚡" if _is_ready(vid) else "⬇️"
            to_fetch.append(vid)

            answers.append(
                types.InlineQueryResultArticle(
                    id=vid,
                    title=f"{tag} {title[:60]}",
                    description=f"🎵 {duration}  •  👁 {views}  •  {channel}",
                    input_message_content=types.InputTextMessageContent(
                        message_text=f"⏳ <b>{title[:60]}</b>\n<i>Preparing…</i>",
                        parse_mode=enums.ParseMode.HTML,
                        disable_web_page_preview=True,
                    ),
                )
            )

        if answers:
            # Send results first — user sees them instantly
            await app.answer_inline_query(query.id, results=answers, cache_time=0)
            # Fire all prefetches concurrently
            asyncio.gather(*[_prefetch(vid) for vid in to_fetch], return_exceptions=True)
        else:
            await app.answer_inline_query(
                query.id, results=[],
                switch_pm_text="❌ No results found",
                switch_pm_parameter="start",
                cache_time=5,
            )
    except Exception:
        try:
            await app.answer_inline_query(
                query.id, results=[],
                switch_pm_text="⚠️ Search failed",
                switch_pm_parameter="start",
                cache_time=0,
            )
        except Exception:
            pass

# ── Chosen result ─────────────────────────────────────────────────────────────
@app.on_chosen_inline_result()
async def on_chosen(client, result: types.ChosenInlineResult):
    vid        = result.result_id
    inline_mid = result.inline_message_id
    if not inline_mid:
        return

    meta      = _meta.get(vid, {})
    title     = meta.get("title", "Unknown Title")
    performer = meta.get("performer", "Unknown Artist")

    # ── instant path: telegram file_id ────────────────────────────────────────
    if vid in _fid:
        if await _send_fid(client, vid, inline_mid, title, performer):
            return

    # ── serialise: if prefetch is running, wait on same lock ──────────────────
    async with _get_lock(vid):
        if vid in _fid:
            if await _send_fid(client, vid, inline_mid, title, performer):
                return

        # File may already be on disk from prefetch
        fp = _path.get(vid) or _disk_cached(vid)

        # If not ready yet, download now (with yt-dlp fallback)
        if not fp:
            fp = await _fetch_and_store(vid)

        if not fp:
            # Last resort: yt-dlp
            try:
                from anony.core.youtube import YouTube
                fp = await YouTube().download(vid, video=False)
            except Exception:
                pass

        if not fp:
            await _edit_caption(client, inline_mid, "❌ <b>Download failed.</b>")
            return

        await _upload(client, vid, inline_mid, fp, title, performer)

async def _send_fid(client, vid, inline_mid, title, performer) -> bool:
    try:
        await client.edit_inline_media(
            inline_message_id=inline_mid,
            media=types.InputMediaAudio(media=_fid[vid], title=title, performer=performer),
        )
        return True
    except Exception:
        _fid.pop(vid, None)
        return False

async def _upload(client, vid, inline_mid, fp, title, performer) -> None:
    try:
        msg = await client.edit_inline_media(
            inline_message_id=inline_mid,
            media=types.InputMediaAudio(media=fp, title=title, performer=performer),
        )
        if msg and hasattr(msg, "audio") and msg.audio:
            _fid[vid] = msg.audio.file_id
    except Exception as e:
        await _edit_caption(client, inline_mid, f"❌ <code>{e}</code>")

async def _edit_caption(client, inline_mid, text) -> None:
    try:
        await client.edit_inline_caption(
            inline_message_id=inline_mid,
            caption=text,
            parse_mode=enums.ParseMode.HTML,
        )
    except Exception:
        pass


# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic
