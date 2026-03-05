from pyrogram import types, enums
from py_yt import VideosSearch

from anony import app, logger
from anony.core.youtube import YouTube

yt = YouTube()
_meta: dict[str, dict] = {}
_fid: dict[str, str] = {}


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

    logger.info(f"[INLINE] query='{text}' from={query.from_user.id}")
    try:
        results = (await (VideosSearch(text, limit=10)).next()).get("result", [])
        logger.info(f"[INLINE] got {len(results)} results")

        answers = []
        for v in results:
            vid_id   = v.get("id", "")
            title    = v.get("title", "Unknown")
            duration = v.get("duration", "N/A")
            views    = v.get("viewCount", {}).get("short", "N/A")
            channel  = v.get("channel", {}).get("name", "Unknown")
            thumb    = (v.get("thumbnails") or [{}])[-1].get("url", "").split("?")[0]

            if not vid_id or not thumb:
                continue

            _meta[vid_id] = {"title": title, "performer": channel, "duration": duration}

            cached = vid_id in _fid or yt._check_cached_file(vid_id)
            tag = "⚡ Instant" if cached else "⬇️ Download"

            answers.append(
                types.InlineQueryResultPhoto(
                    id=vid_id,
                    photo_url=thumb,
                    thumb_url=thumb,
                    title=title[:64],
                    description=f"{tag}  •  🎵 {duration}  •  👁 {views}  •  {channel}",
                    caption=f"⏳ <b>{title[:60]}</b>…",
                    parse_mode=enums.ParseMode.HTML,
                )
            )

        if answers:
            await app.answer_inline_query(query.id, results=answers, cache_time=30)
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


@app.on_chosen_inline_result()
async def on_chosen(client, result: types.ChosenInlineResult):
    video_id   = result.result_id
    inline_mid = result.inline_message_id
    if not inline_mid:
        return

    meta      = _meta.get(video_id, {})
    title     = meta.get("title", "Unknown Title")
    performer = meta.get("performer", "Unknown Artist")

    logger.info(f"[ILDL] start video_id={video_id} title={title}")

    if video_id in _fid:
        logger.info(f"[ILDL] file_id cache hit for {video_id}")
        try:
            await client.edit_inline_media(
                inline_message_id=inline_mid,
                media=types.InputMediaAudio(
                    media=_fid[video_id],
                    title=title,
                    performer=performer,
                ),
            )
            logger.info(f"[ILDL] instant send via file_id: {title}")
        except Exception as e:
            logger.warning(f"[ILDL] file_id send failed, re-uploading: {e}")
            del _fid[video_id]
            await _download_and_send(client, video_id, inline_mid, title, performer)
        return

    await _download_and_send(client, video_id, inline_mid, title, performer)


async def _download_and_send(client, video_id: str, inline_mid: str, title: str, performer: str):
    try:
        url       = f"https://www.youtube.com/watch?v={video_id}"
        file_path = await yt.fallen.download_track(url)
        logger.info(f"[ILDL] fallen result: {file_path}")

        if not file_path:
            file_path = await yt.download(video_id, video=False)
            logger.info(f"[ILDL] ytdlp fallback: {file_path}")

        if not file_path:
            await client.edit_inline_caption(
                inline_message_id=inline_mid,
                caption="❌ <b>Download failed.</b>",
                parse_mode=enums.ParseMode.HTML,
            )
            return

        msg = await client.edit_inline_media(
            inline_message_id=inline_mid,
            media=types.InputMediaAudio(
                media=file_path,
                title=title,
                performer=performer,
            ),
        )

        if msg and hasattr(msg, "audio") and msg.audio:
            _fid[video_id] = msg.audio.file_id
            logger.info(f"[ILDL] cached file_id for {video_id}")

        logger.info(f"[ILDL] done: {title}")

    except Exception as e:
        logger.error(f"[ILDL] fatal: {e}", exc_info=True)
        try:
            await client.edit_inline_caption(
                inline_message_id=inline_mid,
                caption=f"❌ <code>{e}</code>",
                parse_mode=enums.ParseMode.HTML,
            )
        except Exception:
            pass
