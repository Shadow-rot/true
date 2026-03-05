from pyrogram import types, enums
from py_yt import VideosSearch

from anony import app
from anony.core.youtube import YouTube

yt = YouTube()


@app.on_inline_query()
async def inline_search(_, query: types.InlineQuery):
    text = query.query.strip()
    if not text:
        await app.answer_inline_query(
            query.id,
            results=[],
            switch_pm_text="Type a song name to search",
            switch_pm_parameter="start",
            cache_time=0,
        )
        return

    try:
        search = VideosSearch(text, limit=10)
        data = await search.next()
        results = data.get("result", [])

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

            answers.append(
                types.InlineQueryResultPhoto(
                    id=vid_id,
                    photo_url=thumb,
                    thumb_url=thumb,
                    title=title[:64],
                    description=f"🎵 {duration}  •  👁 {views}  •  {channel}",
                    caption=f"⏳ Downloading <b>{title[:60]}</b>…",
                    parse_mode=enums.ParseMode.HTML,
                )
            )

        if answers:
            await app.answer_inline_query(query.id, results=answers, cache_time=5)
        else:
            await app.answer_inline_query(
                query.id,
                results=[],
                switch_pm_text="No results found",
                switch_pm_parameter="start",
                cache_time=5,
            )
    except Exception as e:
        await app.answer_inline_query(
            query.id,
            results=[],
            switch_pm_text=f"Error: {str(e)[:32]}",
            switch_pm_parameter="start",
            cache_time=0,
        )


@app.on_chosen_inline_result()
async def on_chosen(client, result: types.ChosenInlineResult):
    video_id   = result.result_id
    inline_mid = result.inline_message_id
    user_id    = result.from_user.id

    if not inline_mid:
        return

    try:
        file_path = await yt.download(video_id, video=False)

        if not file_path:
            await client.edit_inline_caption(
                inline_message_id=inline_mid,
                caption="❌ Download failed. Try again.",
                parse_mode=enums.ParseMode.HTML,
            )
            return

        await client.send_audio(
            chat_id=user_id,
            audio=file_path,
        )

        await client.edit_inline_caption(
            inline_message_id=inline_mid,
            caption="✅ Sent to your DM!",
            parse_mode=enums.ParseMode.HTML,
            reply_markup=types.InlineKeyboardMarkup([[
                types.InlineKeyboardButton(
                    "📩 Open DM",
                    url=f"https://t.me/{(await client.get_me()).username}",
                )
            ]]),
        )

    except Exception as e:
        try:
            await client.edit_inline_caption(
                inline_message_id=inline_mid,
                caption=f"❌ <code>{e}</code>",
                parse_mode=enums.ParseMode.HTML,
            )
        except Exception:
            pass
