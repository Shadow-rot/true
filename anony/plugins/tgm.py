import os
import requests
from PIL import Image
from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from anony import app


def upload_to_telegraph(path):
    with open(path, "rb") as f:
        r = requests.post(
            "https://telegra.ph/upload",
            files={"file": ("image.jpg", f, "image/jpeg")},
        )

    if r.status_code == 200:
        data = r.json()
        if isinstance(data, list) and "src" in data[0]:
            return True, "https://telegra.ph" + data[0]["src"]

    return False, f"Telegraph Error {r.status_code}: {r.text}"


@app.on_message(filters.command(["tgm", "telegraph"]))
async def telegraph_uploader(client, message):

    if not message.reply_to_message or not message.reply_to_message.photo:
        return await message.reply("❍ Reply to a photo (max 5MB).")

    msg = await message.reply("❍ Processing...")

    try:
        # Download original
        original = await message.reply_to_message.download()

        # Force clean re-encode
        img = Image.open(original).convert("RGB")

        clean_path = "clean_image.jpg"
        img.save(clean_path, "JPEG", quality=90, optimize=True)

        os.remove(original)

        # Check size
        if os.path.getsize(clean_path) > 5 * 1024 * 1024:
            os.remove(clean_path)
            return await msg.edit("❍ Image exceeds 5MB after processing.")

        success, result = upload_to_telegraph(clean_path)

        if success:
            await msg.edit_text(
                f"❍ | [Open Link]({result})",
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❍ Open Telegraph ❍", url=result)]]
                ),
            )
        else:
            await msg.edit(result)

        os.remove(clean_path)

    except Exception as e:
        await msg.edit(f"❍ Error:\n{e}")