from __future__ import annotations

import asyncio
from typing import Optional

from pyrogram import types, enums
from py_yt import VideosSearch

from anony import app
from anony.core.fallen_api import FallenApi

fallen = FallenApi()

_meta: dict[str, dict] = {}
_fid:  dict[str, str]  = {}
_lock: dict[str, asyncio.Lock] = {}
_pre:  set[str] = set()  # video_ids already being pre-fetched


def _get_lock(video_id: str) -> asyncio.Lock:
    if video_id not in _lock:
        _lock[video_id] = asyncio.Lock()
    return _lock[video_id]


def _is_cached(video_id: str) -> bool:
    return video_id in _fid or bool(fallen._check_cached_file(video_id))


async def _prefetch(video_id: str) -> None:
    """Download and cache a track silently in the background."""
    if video_id in _pre or _is_cached(video_id):
        return
    _pre.add(video_id)
    try:
        async with _get_lock(video_id):
            if _is_cached(video_id):
                return
            url = f"https://www.youtube.com/watch?v={video_id}"
            await fallen.download_track(url)
    except Exception:
        pass
    finally:
        _pre.discard(video_id)


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
        ids_to_prefetch: list[str] = []

        for v in results:
            vid_id   = v.get("id", "")
            title    = v.get("title", "Unknown")
            duration = v.get("duration", "N/A")
            views    = v.get("viewCount", {}).get("short", "N/A")
            channel  = v.get("channel", {}).get("name", "Unknown")

            if not vid_id:
                continue

            _meta[vid_id] = {
                "title":     title,
                "performer": channel,
                "duration":  duration,
            }

            tag = "⚡" if _is_cached(vid_id) else "⬇️"
            ids_to_prefetch.append(vid_id)

            answers.append(
                types.InlineQueryResultArticle(
                    id=vid_id,
                    title=f"{tag} {title[:60]}",
                    description=f"🎵 {duration}  •  👁 {views}  •  {channel}",
                    input_message_content=types.InputTextMessageContent(
                        message_text=(
                            f"⏳ <b>{title[:60]}</b>\n"
                            f"<i>Preparing audio…</i>"
                        ),
                        parse_mode=enums.ParseMode.HTML,
                        disable_web_page_preview=True,
                    ),
                )
            )

        if answers:
            # Reply to user instantly, then fire background prefetch for all results
            await app.answer_inline_query(query.id, results=answers, cache_time=0)
            for vid_id in ids_to_prefetch:
                asyncio.create_task(_prefetch(vid_id))
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


@app.on_chosen_inline_result()
async def on_chosen(client, result: types.ChosenInlineResult):
    video_id   = result.result_id
    inline_mid = result.inline_message_id
    if not inline_mid:
        return

    meta      = _meta.get(video_id, {})
    title     = meta.get("title", "Unknown Title")
    performer = meta.get("performer", "Unknown Artist")

    # Fast path: Telegram file_id already in memory
    if video_id in _fid:
        if await _send_via_file_id(client, video_id, inline_mid, title, performer):
            return

    async with _get_lock(video_id):
        # Re-check after lock — prefetch may have landed while we waited
        if video_id in _fid:
            if await _send_via_file_id(client, video_id, inline_mid, title, performer):
                return

        await _download_and_send(client, video_id, inline_mid, title, performer)


async def _send_via_file_id(
    client, video_id: str, inline_mid: str, title: str, performer: str
) -> bool:
    try:
        await client.edit_inline_media(
            inline_message_id=inline_mid,
            media=types.InputMediaAudio(
                media=_fid[video_id],
                title=title,
                performer=performer,
            ),
        )
        return True
    except Exception:
        _fid.pop(video_id, None)
        return False


async def _download_and_send(
    client, video_id: str, inline_mid: str, title: str, performer: str
) -> None:
    url = f"https://www.youtube.com/watch?v={video_id}"

    try:
        # 1. FallenApi — CDN / Telegram fast path
        file_path: Optional[str] = await fallen.download_track(url)

        # 2. yt-dlp fallback (lazy import to avoid circular at startup)
        if not file_path:
            from anony.core.youtube import YouTube
            file_path = await YouTube().download(video_id, video=False)

        if not file_path:
            await _edit_caption(client, inline_mid, "❌ <b>Download failed.</b>")
            return

        msg = await client.edit_inline_media(
            inline_message_id=inline_mid,
            media=types.InputMediaAudio(
                media=file_path,
                title=title,
                performer=performer,
            ),
        )

        # Persist file_id for zero-cost future delivery
        if msg and hasattr(msg, "audio") and msg.audio:
            _fid[video_id] = msg.audio.file_id

    except Exception as e:
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
