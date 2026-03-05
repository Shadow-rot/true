from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from pyrogram import Client, filters, enums
from pyrogram import raw
from pyrogram.errors import StickersetInvalid, BadRequest
from pyrogram.types import Message
from anony import app


async def _text_on_sticker(data: bytes, text: str) -> BytesIO:
    img = Image.open(BytesIO(data)).convert("RGBA")
    w, h = img.size
    draw = ImageDraw.Draw(img)
    fs = max(28, w // 7)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", fs)
    except Exception:
        font = ImageFont.load_default()
    lines, cur = [], ""
    for word in text.split():
        test = f"{cur} {word}".strip()
        bb = draw.textbbox((0, 0), test, font=font)
        if (bb[2] - bb[0]) > w * 0.88 and cur:
            lines.append(cur)
            cur = word
        else:
            cur = test
    if cur:
        lines.append(cur)
    full = "\n".join(lines)
    bb = draw.textbbox((0, 0), full, font=font)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    tx = (w - tw) / 2
    ty = h - th - 20
    for ox, oy in ((-2, -2), (2, -2), (-2, 2), (2, 2), (0, -2), (0, 2), (-2, 0), (2, 0)):
        draw.multiline_text((tx + ox, ty + oy), full, font=font, fill=(0, 0, 0, 255), align="center")
    draw.multiline_text((tx, ty), full, font=font, fill=(255, 255, 255, 255), align="center")
    out = BytesIO()
    img.save(out, "WEBP")
    out.seek(0)
    out.name = "sticker.webp"
    return out


async def _to_webp(data: bytes) -> BytesIO:
    img = Image.open(BytesIO(data)).convert("RGBA")
    img.thumbnail((512, 512), Image.LANCZOS)
    canvas = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    offset = ((512 - img.width) // 2, (512 - img.height) // 2)
    canvas.paste(img, offset)
    out = BytesIO()
    canvas.save(out, "WEBP")
    out.seek(0)
    out.name = "sticker.webp"
    return out


async def _upload_sticker(client: Client, buf: BytesIO, mime: str, fname: str) -> raw.types.InputDocument:
    uploaded = await client.save_file(buf)
    r = await client.invoke(
        raw.functions.messages.UploadMedia(
            peer=raw.types.InputPeerSelf(),
            media=raw.types.InputMediaUploadedDocument(
                file=uploaded,
                mime_type=mime,
                attributes=[raw.types.DocumentAttributeFilename(file_name=fname)],
            ),
        )
    )
    d = r.document
    return raw.types.InputDocument(id=d.id, access_hash=d.access_hash, file_reference=d.file_reference)


@app.on_message(filters.command("mmf") & filters.reply)
async def mmf_cmd(client: Client, ctx: Message):
    text = " ".join(ctx.text.split()[1:])
    if not text:
        return await ctx.reply_text("❌ Usage: <code>/mmf your text</code>", parse_mode=enums.ParseMode.HTML)
    replied = ctx.reply_to_message
    if not any([replied.sticker, replied.photo, replied.document]):
        return await ctx.reply_text("❌ Reply to a sticker or photo.", parse_mode=enums.ParseMode.HTML)
    st = await ctx.reply_text("⏳", parse_mode=enums.ParseMode.HTML)
    try:
        f = await client.download_media(replied, in_memory=True)
        buf = await _text_on_sticker(f.getvalue(), text)
        await ctx.reply_sticker(buf)
    except Exception as e:
        print(e)
        await ctx.reply_text(f"⚠️ <code>{e}</code>", parse_mode=enums.ParseMode.HTML)
    finally:
        try:
            await st.delete()
        except Exception:
            pass


@app.on_message(filters.command("kang") & filters.reply)
async def kang_cmd(client: Client, ctx: Message):
    replied = ctx.reply_to_message
    if not any([replied.sticker, replied.photo, replied.document, replied.animation, replied.video]):
        return await ctx.reply_text("❌ Reply to a sticker or media.", parse_mode=enums.ParseMode.HTML)
    st = await ctx.reply_text("⏳ Kanging…", parse_mode=enums.ParseMode.HTML)
    try:
        me = await client.get_me()
        emoji = "🎭"
        is_animated = is_video = False

        if replied.sticker:
            emoji = replied.sticker.emoji or "🎭"
            is_animated = replied.sticker.is_animated
            is_video = replied.sticker.is_video

        pack_type = "a" if is_animated else ("v" if is_video else "s")
        pack_name = f"kang{me.id}{pack_type}"
        pack_title = f"{me.first_name[:32]}'s Pack"

        f = await client.download_media(replied, in_memory=True)
        data = f.getvalue()

        if is_animated:
            buf = BytesIO(data)
            buf.seek(0)
            buf.name = "sticker.tgs"
            mime, fname = "application/x-tgsticker", "sticker.tgs"
        elif is_video:
            buf = BytesIO(data)
            buf.seek(0)
            buf.name = "sticker.webm"
            mime, fname = "video/webm", "sticker.webm"
        else:
            buf = await _to_webp(data)
            mime, fname = "image/webp", "sticker.webp"

        doc = await _upload_sticker(client, buf, mime, fname)
        user_peer = await client.resolve_peer(me.id)
        item = raw.types.InputStickerSetItem(document=doc, emoji=emoji)

        try:
            await client.invoke(
                raw.functions.stickers.AddStickerToSet(
                    stickerset=raw.types.InputStickerSetShortName(short_name=pack_name),
                    sticker=item,
                )
            )
            msg = "Added to"
        except (StickersetInvalid, BadRequest):
            await client.invoke(
                raw.functions.stickers.CreateStickerSet(
                    user_id=user_peer,
                    title=pack_title,
                    short_name=pack_name,
                    stickers=[item],
                )
            )
            msg = "Created"

        await ctx.reply_text(
            f"✅ {msg}: <a href='https://t.me/addstickers/{pack_name}'>Open Pack</a>",
            parse_mode=enums.ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except Exception as e:
        print(e)
        await ctx.reply_text(f"⚠️ <code>{e}</code>", parse_mode=enums.ParseMode.HTML)
    finally:
        try:
            await st.delete()
        except Exception:
            pass
