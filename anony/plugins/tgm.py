import os
import requests
from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from anony import app


@app.on_message(filters.command(["catbox", "upload", "tgm"]))
async def catbox_upload(_, m):

    if not m.reply_to_message:
        return await m.reply("Reply to a file (Max 200MB).")

    msg = await m.reply("Uploading...")

    try:
        path = await m.reply_to_message.download()

        if os.path.getsize(path) > 200 * 1024 * 1024:
            os.remove(path)
            return await msg.edit("File must be under 200MB.")

        with open(path, "rb") as f:
            r = requests.post(
                "https://catbox.moe/user/api.php",
                data={"reqtype": "fileupload"},
                files={"fileToUpload": f},
            )

        os.remove(path)

        if r.status_code == 200:
            link = r.text.strip()

            await msg.edit_text(
                link,
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton("Copy", copy_text=link)
                        ]
                    ]
                ),
            )
        else:
            await msg.edit(f"Upload failed\n{r.status_code}")

    except Exception as e:
        await msg.edit(str(e))