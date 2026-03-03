import os
from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from telegraph import Telegraph
from anony import app

t = Telegraph()
t.create_account(short_name="AnonyBot")

@app.on_message(filters.command(["tgm"]))
async def tg(client, m):
    if not (m.reply_to_message and m.reply_to_message.photo):
        return await m.reply("Reply to photo (<5MB).")

    if m.reply_to_message.photo.file_size > 5*1024*1024:
        return await m.reply("Max 5MB only.")

    x = await m.reply("Uploading...")
    try:
        p = await m.reply_to_message.download()
        r = t.upload_file(p)
        link = "https://telegra.ph" + r[0]
        await x.edit(
            f"[Open Link]({link})",
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Open", url=link)]]
            ),
        )
        os.remove(p)
    except Exception as e:
        await x.edit(str(e))