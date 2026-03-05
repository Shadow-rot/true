from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from pyrogram import Client, filters, enums, raw
from pyrogram.types import Message
from anony import app


async def _text_on_image(data: bytes, text: str) -> bytes:
    img = Image.open(BytesIO(data)).convert("RGBA")
    w, h = img.size
    draw = ImageDraw.Draw(img)
    fs = max(24, w // 8)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", fs)
    except Exception:
        font = ImageFont.load_default()
    lines, line = [], ""
    for word in text.split():
        test = f"{line} {word}".strip()
        if draw.textlength(test, font=font) > w * 0.85 and line:
            lines.append(line)
            line = word
        else:
            line = test
    if line:
        lines.append(line)
    full = "\n".join(lines)
    bb = draw.textbbox((0, 0), full, font=font)
    tx = (w - (bb[2] - bb[0])) / 2
    ty = h - (bb[3] - bb[1]) - 15
    for ox, oy in ((-2, -2), (2, -2), (-2, 2), (2, 2)):
        draw.text((tx + ox, ty + oy), full, font=font, fill=(0, 0, 0, 255), align="center")
    draw.text((tx, ty), full, font=font, fill=(255, 255, 255, 255), align="center")
    out = BytesIO()
    img.save(out, "WEBP")
    return out.getvalue()


async def _to_webp(data: bytes) -> BytesIO:
    img = Image.open(BytesIO(data)).convert("RGBA")
    img.thumbnail((512, 512), Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, "WEBP")
    buf.seek(0)
    buf.name = "s.webp"
    return buf


async def _upload_doc(client: Client, buf: BytesIO, mime: str, fname: str) -> raw.types.InputDocument:
    saved = await client.save_file(buf)
    r = await client.invoke(
        raw.functions.messages.UploadMedia(
            peer=raw.types.InputPeerSelf(),
            media=raw.types.InputMediaUploadedDocument(
                file=saved,
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
        return await ctx.reply_text("Usage: <code>/mmf your text</code>", parse_mode=enums.ParseMode.HTML)
    replied = ctx.reply_to_message
    if not any([replied.sticker, replied.photo, replied.document]):
        return await ctx.reply_text("❌ Reply to a sticker or image.", parse_mode=enums.ParseMode.HTML)
    st = await ctx.reply_text("⏳", parse_mode=enums.ParseMode.HTML)
    try:
        f = await client.download_media(replied, in_memory=True)
        result = await _text_on_image(bytes(f.getbuffer()), text)
        buf = BytesIO(result)
        buf.name = "sticker.webp"
        await ctx.reply_sticker(buf)
    except Exception as e:
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
            s = replied.sticker
            emoji = s.emoji or "🎭"
            is_animated = s.is_animated
            is_video = s.is_video

        pack_suffix = "a" if is_animated else ("v" if is_video else "s")
        pack_name = f"kang{me.id}{pack_suffix}"
        pack_title = f"{me.first_name}'s Kang Pack"

        f = await client.download_media(replied, in_memory=True)
        data = bytes(f.getbuffer())

        if is_animated:
            buf = BytesIO(data)
            buf.name = "sticker.tgs"
            mime, fname = "application/x-tgsticker", "sticker.tgs"
        elif is_video:
            buf = BytesIO(data)
            buf.name = "sticker.webm"
            mime, fname = "video/webm", "sticker.webm"
        else:
            buf = await _to_webp(data)
            mime, fname = "image/webp", "sticker.webp"

        doc = await _upload_doc(client, buf, mime, fname)
        item = raw.types.InputStickerSetItem(document=doc, emoji=emoji)

        try:
            await client.invoke(
                raw.functions.stickers.AddStickerToSet(
                    stickerset=raw.types.InputStickerSetShortName(short_name=pack_name),
                    sticker=item,
                )
            )
            action = "Added to"
        except raw.errors.StickersetInvalid:
            kwargs = dict(
                user_id=raw.types.InputUserSelf(),
                title=pack_title,
                short_name=pack_name,
                stickers=[item],
            )
            if is_animated:
                kwargs["animated"] = True
            elif is_video:
                kwargs["videos"] = True
            await client.invoke(raw.functions.stickers.CreateStickerSet(**kwargs))
            action = "Created"

        await ctx.reply_text(
            f"✅ {action}: <a href='https://t.me/addstickers/{pack_name}'>Open Pack</a>",
            parse_mode=enums.ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except Exception as e:
        await ctx.reply_text(f"⚠️ <code>{e}</code>", parse_mode=enums.ParseMode.HTML)
    finally:
        try:
            await st.delete()
        except Exception:
            pass
