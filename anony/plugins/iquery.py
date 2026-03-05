from pyrogram import types, enums
from py_yt import VideosSearch

from anony import app
from anony.core.youtube import YouTube

yt = YouTube()


@app.on_inline_query(~app.bl_users)
async def inline_query_handler(_, query: types.InlineQuery):
    text = query.query.strip()
    if not text:
        return
    try:
        search = VideosSearch(text, limit=15)
        results = (await search.next()).get("result", [])
        answers = []
        for video in results:
            vid_id   = video.get("id", "")
            title    = video.get("title", "Unknown")
            duration = video.get("duration", "N/A")
            views    = video.get("viewCount", {}).get("short", "N/A")
            channel  = video.get("channel", {}).get("name", "Unknown")
            thumb    = video.get("thumbnails", [{}])[-1].get("url", "").split("?")[0]
            if not vid_id:
                continue
            answers.append(
                types.InlineQueryResultPhoto(
                    id=vid_id,
                    photo_url=thumb,
                    title=title,
                    description=f"{duration} · {views} · {channel}",
                    caption=f"⏳ Downloading <b>{title[:60]}</b>…",
                    parse_mode=enums.ParseMode.HTML,
                    reply_markup=types.InlineKeyboardMarkup([[]]),
                )
            )
        if answers:
            await app.answer_inline_query(query.id, results=answers, cache_time=10)
    except Exception:
        pass


@app.on_chosen_inline_result()
async def on_chosen(client, result: types.ChosenInlineResult):
    video_id   = result.result_id
    inline_mid = result.inline_message_id
    if not inline_mid:
        return
    try:
        file_path = await yt.download(video_id, video=False)
        if not file_path:
            await client.edit_inline_caption(
                inline_message_id=inline_mid,
                caption="❌ Download failed.",
                parse_mode=enums.ParseMode.HTML,
            )
            return

        sent = await client.send_audio(
            chat_id=result.from_user.id,
            audio=file_path,
        )
        await client.edit_inline_caption(
            inline_message_id=inline_mid,
            caption=f"✅ Sent to your DM.",
            parse_mode=enums.ParseMode.HTML,
            reply_markup=types.InlineKeyboardMarkup([[
                types.InlineKeyboardButton("🎵 Open", url=f"https://t.me/{(await client.get_me()).username}")
            ]])
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
