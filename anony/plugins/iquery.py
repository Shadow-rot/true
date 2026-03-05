import logging
from pyrogram import types, enums
from py_yt import VideosSearch

from anony import app, logger
from anony.core.youtube import YouTube

yt = YouTube()


@app.on_inline_query()
async def inline_search(_, query: types.InlineQuery):
    text = query.query.strip()
    logger.info(f"[INLINE] query='{text}' from={query.from_user.id}")

    if not text:
        await app.answer_inline_query(
            query.id,
            results=[],
            switch_pm_text="🎵 Type a song name to search",
            switch_pm_parameter="start",
            cache_time=0,
        )
        return

    try:
        search = VideosSearch(text, limit=10)
        data = await search.next()
        results = data.get("result", [])
        logger.info(f"[INLINE] got {len(results)} results")

        answers = []
        for v in results:
            vid_id   = v.get("id", "")
            title    = v.get("title", "Unknown")
            duration = v.get("duration", "N/A")
            views    = v.get("viewCount", {}).get("short", "N/A")
            channel  = v.get("channel", {}).get("name", "Unknown")
            thumbs   = v.get("thumbnails") or [{}]
            thumb    = thumbs[-1].get("url", "").split("?")[0]

            if not vid_id or not thumb:
                logger.warning(f"[INLINE] skipping result missing id or thumb: {v}")
                continue

            answers.append(
                types.InlineQueryResultPhoto(
                    id=vid_id,
                    photo_url=thumb,
                    thumb_url=thumb,
                    title=title[:64],
                    description=f"🎵 {duration}  •  👁 {views}  •  {channel}",
                    caption=(
                        f"<b>🎵 {title[:60]}</b>\n"
                        f"⏱ {duration}  •  {channel}\n\n"
                        f"<i>Tap the button to download as MP3</i>"
                    ),
                    parse_mode=enums.ParseMode.HTML,
                    reply_markup=types.InlineKeyboardMarkup([[
                        types.InlineKeyboardButton("⬇️ Download MP3", callback_data=f"ildl:{vid_id}")
                    ]])
                )
            )

        if answers:
            await app.answer_inline_query(query.id, results=answers, cache_time=5)
            logger.info(f"[INLINE] answered with {len(answers)} results")
        else:
            await app.answer_inline_query(
                query.id, results=[],
                switch_pm_text="❌ No results found",
                switch_pm_parameter="start",
                cache_time=5,
            )

    except Exception as e:
        logger.error(f"[INLINE] search error: {e}", exc_info=True)
        try:
            await app.answer_inline_query(
                query.id, results=[],
                switch_pm_text="⚠️ Search failed, try again",
                switch_pm_parameter="start",
                cache_time=0,
            )
        except Exception:
            pass


@app.on_callback_query(filters=None)
async def inline_download(client, cb: types.CallbackQuery):
    if not cb.data or not cb.data.startswith("ildl:"):
        return

    video_id    = cb.data.split(":", 1)[1]
    inline_mid  = cb.inline_message_id

    logger.info(f"[ILDL] video_id={video_id} inline_mid={inline_mid} user={cb.from_user.id}")

    if not inline_mid:
        await cb.answer("❌ Cannot process this request.", show_alert=True)
        return

    await cb.answer("⏳ Downloading, please wait…", show_alert=False)

    try:
        await client.edit_inline_caption(
            inline_message_id=inline_mid,
            caption="⏳ <b>Downloading MP3…</b>",
            parse_mode=enums.ParseMode.HTML,
        )
    except Exception as e:
        logger.warning(f"[ILDL] could not edit caption to downloading: {e}")

    try:
        file_path = await yt.download(video_id, video=False)
        logger.info(f"[ILDL] download result: {file_path}")

        if not file_path:
            await client.edit_inline_caption(
                inline_message_id=inline_mid,
                caption="❌ <b>Download failed.</b> Try again.",
                parse_mode=enums.ParseMode.HTML,
            )
            return

        await client.edit_inline_media(
            inline_message_id=inline_mid,
            media=types.InputMediaAudio(media=file_path),
        )
        logger.info(f"[ILDL] edit_inline_media success for {video_id}")

    except Exception as e:
        logger.error(f"[ILDL] error: {e}", exc_info=True)
        try:
            await client.edit_inline_caption(
                inline_message_id=inline_mid,
                caption=f"❌ <code>{e}</code>",
                parse_mode=enums.ParseMode.HTML,
            )
        except Exception:
            pass
