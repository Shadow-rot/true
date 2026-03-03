import os
import requests
from PIL import Image
from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from anony import app


def upload_to_telegraph(file_path):
    with open(file_path, "rb") as f:
        r = requests.post("https://telegra.ph/upload", files={"file": f})

    if r.status_code == 200:
        data = r.json()
        return True, "https://telegra.ph" + data[0]["src"]

    return False, f"Error {r.status_code}"


@app.on_message(filters.command(["tgm", "telegraph"]))
async def telegraph_uploader(client, message):

    if not message.reply_to_message or not message.reply_to_message.photo:
        return await message.reply("❍ Reply to a photo under 5MB.")

    msg = await message.reply("❍ Processing...")

    try:
        # Download
        path = await message.reply_to_message.download()

        # Convert to JPG (fix 400 error)
        img = Image.open(path).convert("RGB")
        new_path = path + ".jpg"
        img.save(new_path, "JPEG", quality=95)

        os.remove(path)

        if os.path.getsize(new_path) > 5 * 1024 * 1024:
            os.remove(new_path)
            return await msg.edit("❍ File exceeds 5MB after conversion.")

        success, result = upload_to_telegraph(new_path)

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

        os.remove(new_path)

    except Exception as e:
        await msg.edit_text(f"❍ Error:\n{e}")