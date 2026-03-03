import os
import requests
from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from anony import app


def upload_to_telegraph(file_path):
    url = "https://telegra.ph/upload"
    with open(file_path, "rb") as f:
        r = requests.post(url, files={"file": f})

    if r.status_code == 200:
        try:
            data = r.json()
            if isinstance(data, list):
                return True, "https://telegra.ph" + data[0]["src"]
        except:
            return False, "Invalid Telegraph response"
    return False, f"Error {r.status_code}"


@app.on_message(filters.command(["tgm", "telegraph"]))
async def telegraph_uploader(client, message):

    if not message.reply_to_message or not message.reply_to_message.photo:
        return await message.reply("❍ Reply to a photo under 5MB.")

    photo = message.reply_to_message.photo

    if photo.file_size > 5 * 1024 * 1024:
        return await message.reply("❍ File must be under 5MB.")

    msg = await message.reply("❍ Processing...")

    try:
        path = await message.reply_to_message.download()

        success, result = upload_to_telegraph(path)

        if success:
            await msg.edit_text(
                f"❍ | [Tap Here]({result})",
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❍ Open Link ❍", url=result)]]
                ),
            )
        else:
            await msg.edit_text(f"❍ Upload failed\n\n{result}")

        os.remove(path)

    except Exception as e:
        await msg.edit_text(f"❍ Error:\n{e}")
        try:
            os.remove(path)
        except:
            pass