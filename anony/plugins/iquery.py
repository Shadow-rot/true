from __future__ import annotations

import asyncio
from typing import Optional

from pyrogram import types, enums
from py_yt import VideosSearch

from anony import app, logger
from anony.core.fallen_api import FallenApi

# ── Shared state ──────────────────────────────────────────────────────────────
fallen = FallenApi()

_meta: dict[str, dict]  = {}   # vid_id → {title, performer, duration}
_fid:  dict[str, str]   = {}   # vid_id → telegram file_id  (persistent cache)
_lock: dict[str, asyncio.Lock] = {}  # per-video download lock (deduplicate)


def _get_lock(video_id: str) -> asyncio.Lock:
    if video_id not in _lock:
        _lock[video_id] = asyncio.Lock()
    return _lock[video_id]


def _is_cached(video_id: str) -> bool:
    """True when we already have a Telegram file_id OR a local file on disk."""
    return video_id in _fid or bool(fallen._check_cached_file(video_id))


# ── Inline search ─────────────────────────────────────────────────────────────
@app.on_inline_query()
async def inline_search(_, query: types.InlineQuery):
    text = query.query.strip()
    uid  = query.from_user.id

    if not text:
        await app.answer_inline_query(
            query.id, results=[],
            switch_pm_text="🎵 Type a song name to search",
            switch_pm_parameter="start",
            cache_time=0,
        )
        return

    logger.info(f"[INLINE] query='{text}' from={uid}")

    try:
        raw     = await VideosSearch(text, limit=10).next()
        results = raw.get("result", [])
        logger.info(f"[INLINE] {len(results)} results for '{text}'")

        answers: list[types.InlineQueryResultArticle] = []

        for v in results:
            vid_id   = v.get("id", "")
            title    = v.get("title", "Unknown")
            duration = v.get("duration", "N/A")
            views    = v.get("viewCount", {}).get("short", "N/A")
            channel  = v.get("channel", {}).get("name", "Unknown")

            if not vid_id:
                continue

            # Store meta for chosen-result handler
            _meta[vid_id] = {
                "title":     title,
                "performer": channel,
                "duration":  duration,
            }

            tag = "⚡" if _is_cached(vid_id) else "⬇️"

            answers.append(
                types.InlineQueryResultArticle(
                    id=vid_id,
                    title=f"{tag} {title[:60]}",
                    description=f"🎵 {duration}  •  👁 {views}  •  {channel}",
                    input_message_content=types.InputTextMessageContent(
                        message_text=(
                            f"⏳ <b>{title[:60]}</b>\n"
                            f"<i>Downloading…</i>"
                        ),
                        parse_mode=enums.ParseMode.HTML,
                        disable_web_page_preview=True,
                    ),
                )
            )

        if answers:
            await app.answer_inline_query(query.id, results=answers, cache_time=0)
        else:
            await app.answer_inline_query(
                query.id, results=[],
                switch_pm_text="❌ No results found",
                switch_pm_parameter="start",
                cache_time=5,
            )

    except Exception as e:
        logger.error(f"[INLINE] error: {e}", exc_info=True)
        try:
            await app.answer_inline_query(
                query.id, results=[],
                switch_pm_text="⚠️ Search failed",
                switch_pm_parameter="start",
                cache_time=0,
            )
        except Exception:
            pass


# ── Chosen result handler ─────────────────────────────────────────────────────
@app.on_chosen_inline_result()
async def on_chosen(client, result: types.ChosenInlineResult):
    video_id   = result.result_id
    inline_mid = result.inline_message_id
    if not inline_mid:
        return

    meta      = _meta.get(video_id, {})
    title     = meta.get("title", "Unknown Title")
    performer = meta.get("performer", "Unknown Artist")

    logger.info(f"[ILDL] chosen video_id={video_id} title='{title}'")

    # ── Fast path: already have Telegram file_id ──────────────────────────────
    if video_id in _fid:
        if await _send_via_file_id(client, video_id, inline_mid, title, performer):
            return
        # file_id stale — fall through to re-download

    # ── Serialise parallel downloads for the same video ───────────────────────
    async with _get_lock(video_id):
        # Re-check after acquiring lock (another coroutine may have finished)
        if video_id in _fid:
            if await _send_via_file_id(client, video_id, inline_mid, title, performer):
                return

        await _download_and_send(client, video_id, inline_mid, title, performer)


# ── Helpers ───────────────────────────────────────────────────────────────────
async def _send_via_file_id(
    client,
    video_id: str,
    inline_mid: str,
    title: str,
    performer: str,
) -> bool:
    """Try to send audio using a cached Telegram file_id. Returns True on success."""
    try:
        await client.edit_inline_media(
            inline_message_id=inline_mid,
            media=types.InputMediaAudio(
                media=_fid[video_id],
                title=title,
                performer=performer,
            ),
        )
        logger.info(f"[ILDL] ⚡ instant send via file_id: '{title}'")
        return True
    except Exception as e:
        logger.warning(f"[ILDL] file_id stale, evicting ({e})")
        _fid.pop(video_id, None)
        return False


async def _download_and_send(
    client,
    video_id: str,
    inline_mid: str,
    title: str,
    performer: str,
) -> None:
    url = f"https://www.youtube.com/watch?v={video_id}"

    try:
        # ── 1. FallenApi (fast CDN / Telegram source) ─────────────────────
        file_path: Optional[str] = await fallen.download_track(url)
        logger.info(f"[ILDL] fallen → {file_path!r}")

        # ── 2. yt-dlp fallback (lazy import keeps startup fast) ───────────
        if not file_path:
            from anony.core.youtube import YouTube  # local import avoids circular
            file_path = await YouTube().download(video_id, video=False)
            logger.info(f"[ILDL] yt-dlp fallback → {file_path!r}")

        if not file_path:
            await _edit_caption(client, inline_mid, "❌ <b>Download failed.</b>")
            return

        # ── 3. Upload audio ───────────────────────────────────────────────
        msg = await client.edit_inline_media(
            inline_message_id=inline_mid,
            media=types.InputMediaAudio(
                media=file_path,
                title=title,
                performer=performer,
            ),
        )

        # Cache file_id for instant future delivery
        if msg and hasattr(msg, "audio") and msg.audio:
            _fid[video_id] = msg.audio.file_id
            logger.info(f"[ILDL] ✅ cached file_id for '{title}'")

        logger.info(f"[ILDL] done: '{title}'")

    except Exception as e:
        logger.error(f"[ILDL] fatal: {e}", exc_info=True)
        await _edit_caption(client, inline_mid, f"❌ <code>{e}</code>")


async def _edit_caption(client, inline_mid: str, text: str) -> None:
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
