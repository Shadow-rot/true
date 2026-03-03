import os
from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from telegraph import Telegraph
from anony import app
# Create Telegraph Account
telegraph = Telegraph()
telegraph.create_account(short_name="AnonXMusicBot")


def upload_to_telegraph(file_path):
    try:
        response = telegraph.upload_file(file_path)
        return True, "https://telegra.ph" + response[0]
    except Exception as e:
        return False, str(e)


@app.on_message(filters.command(["tgm", "tgt", "telegraph"]))
async def telegraph_uploader(client, message):
    if not message.reply_to_message:
        return await message.reply_text(
            "❍ Please reply to a photo or document to upload on Telegraph."
        )

    media = message.reply_to_message

    if not (media.photo or media.document):
        return await message.reply_text(
            "❍ Only photos and documents are supported."
        )

    if media.document and media.document.file_size > 5 * 1024 * 1024:
        return await message.reply_text(
            "❍ Telegraph supports files under 5MB only."
        )

    text = await message.reply("❍ Processing...")

    async def progress(current, total):
        try:
            await text.edit_text(
                f"❍ Downloading... {current * 100 / total:.1f}%"
            )
        except:
            pass

    try:
        # Download file
        local_path = await media.download(progress=progress)

        await text.edit_text("❍ Uploading to Telegraph...")

        success, result = upload_to_telegraph(local_path)

        if success:
            await text.edit_text(
                f"❍ | [Tap the link]({result})",
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❍ Telegraph Uploader ❍", url=result)]]
                ),
            )
        else:
            await text.edit_text(
                f"❍ Upload failed\n\n❍ Reason: {result}"
            )

        os.remove(local_path)

    except Exception as e:
        await text.edit_text(
            f"❍ File upload failed\n\n❍ Reason: {e}"
        )
        try:
            os.remove(local_path)
        except:
            pass