from io import BytesIO
import base64
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from anony import app
from httpx import AsyncClient, Timeout

fetch = AsyncClient(
    http2=True,
    verify=False,
    headers={
        "Accept-Language": "en-US,en;q=0.9",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    },
    timeout=Timeout(30),
)

# ── Color Themes ──────────────────────────────────────────────────────────────
THEMES = {
    "default":  "#1b1429",  # Dark Purple
    "black":    "#000000",
    "white":    "#ffffff",
    "red":      "#1a0000",
    "blue":     "#00001a",
    "green":    "#001a00",
    "cyan":     "#001a1a",
    "magenta":  "#1a001a",
    "yellow":   "#1a1a00",
    "orange":   "#1a0d00",
    "pink":     "#1a0010",
    "teal":     "#00141a",
    "indigo":   "#0d0021",
    "violet":   "#150021",
    "brown":    "#120800",
    "gray":     "#111111",
    # RGB vivid
    "rgb_red":     "#FF0000",
    "rgb_green":   "#00FF00",
    "rgb_blue":    "#0000FF",
    "rgb_cyan":    "#00FFFF",
    "rgb_magenta": "#FF00FF",
    "rgb_yellow":  "#FFFF00",
    "rgb_white":   "#FFFFFF",
    "rgb_orange":  "#FF8000",
    "rgb_pink":    "#FF69B4",
    "rgb_lime":    "#7FFF00",
    "rgb_sky":     "#87CEEB",
    "rgb_gold":    "#FFD700",
    "rgb_purple":  "#800080",
    "rgb_maroon":  "#800000",
    "rgb_navy":    "#000080",
}

APIS = [
    "https://bot.lyo.su/quote/generate",
    "https://qoute-api-bice.vercel.app/generate",
]

HELP_TEXT = """<b>🎨 Quote Command — /q</b>

<b>Usage:</b>
• <code>/q</code> — Quote replied message
• <code>/q r</code> — Include reply context
• <code>/q 2</code> — Quote next 2 messages (max 4)
• <code>/q r 3</code> — 3 messages with reply context
• <code>/q [color]</code> — Use a color theme

<b>🎨 Available Colors:</b>
<code>black, white, red, blue, green, cyan, magenta,
yellow, orange, pink, teal, indigo, violet, brown,
gray, rgb_red, rgb_green, rgb_blue, rgb_cyan,
rgb_magenta, rgb_yellow, rgb_white, rgb_orange,
rgb_pink, rgb_lime, rgb_sky, rgb_gold, rgb_purple,
rgb_maroon, rgb_navy</code>

<b>Example:</b> <code>/q r 3 blue</code>"""


# ── Helpers ───────────────────────────────────────────────────────────────────
def _photo_dict(photo):
    if not photo:
        return ""
    return {
        "small_file_id":        photo.small_file_id,
        "small_photo_unique_id": photo.small_photo_unique_id,
        "big_file_id":          photo.big_file_id,
        "big_photo_unique_id":   photo.big_photo_unique_id,
    }

async def _sender_id(msg: Message) -> int:
    if msg.forward_date:
        if msg.forward_sender_name: return 1
        if msg.forward_from:        return msg.forward_from.id
        if msg.forward_from_chat:   return msg.forward_from_chat.id
        return 1
    if msg.from_user:   return msg.from_user.id
    if msg.sender_chat: return msg.sender_chat.id
    return 1

async def _sender_name(msg: Message) -> str:
    if msg.forward_date:
        if msg.forward_sender_name: return msg.forward_sender_name
        if msg.forward_from:
            u = msg.forward_from
            return f"{u.first_name} {u.last_name}".strip() if u.last_name else u.first_name
        if msg.forward_from_chat:   return msg.forward_from_chat.title
        return ""
    if msg.from_user:
        u = msg.from_user
        return f"{u.first_name} {u.last_name}".strip() if u.last_name else u.first_name
    return msg.sender_chat.title if msg.sender_chat else ""

async def _sender_username(msg: Message) -> str:
    if msg.forward_date:
        if msg.forward_from and msg.forward_from.username:         return msg.forward_from.username
        if msg.forward_from_chat and msg.forward_from_chat.username: return msg.forward_from_chat.username
        return ""
    if msg.from_user and msg.from_user.username:   return msg.from_user.username
    if msg.sender_chat and msg.sender_chat.username: return msg.sender_chat.username
    return ""

async def _sender_photo(msg: Message):
    if msg.forward_date:
        if msg.forward_from and msg.forward_from.photo:         return _photo_dict(msg.forward_from.photo)
        if msg.forward_from_chat and msg.forward_from_chat.photo: return _photo_dict(msg.forward_from_chat.photo)
    else:
        if msg.from_user and msg.from_user.photo:   return _photo_dict(msg.from_user.photo)
        if msg.sender_chat and msg.sender_chat.photo: return _photo_dict(msg.sender_chat.photo)
    return ""

def _text(msg: Message) -> str:
    if msg.text:      return msg.text
    if msg.caption:   return msg.caption
    if msg.sticker:   return msg.sticker.emoji or "🎭"
    if msg.photo:     return "🖼 Photo"
    if msg.video:     return "🎬 Video"
    if msg.audio:     return "🎵 Audio"
    if msg.voice:     return "🎤 Voice"
    if msg.document:  return "📄 Document"
    if msg.animation: return "🎞 GIF"
    return "💬 Message"

def _entities(msg: Message) -> list:
    src = msg.entities or msg.caption_entities or []
    return [{"type": e.type.name.lower(), "offset": e.offset, "length": e.length} for e in src]

def _parse_args(text: str):
    """Returns (is_reply, count, color_hex)."""
    parts  = text.split()[1:]
    is_reply = False
    count    = 1
    color    = THEMES["default"]

    for p in parts:
        low = p.lower()
        if low == "r":
            is_reply = True
        elif low in THEMES:
            color = THEMES[low]
        elif low.startswith("#") and len(low) in (4, 7):
            color = low
        else:
            try:
                n = int(p)
                if 1 <= n <= 4:
                    count = n
            except ValueError:
                pass

    return is_reply, count, color


# ── Core Builder ──────────────────────────────────────────────────────────────
async def build_quote(messages: list, is_reply: bool, bg: str) -> bytes:
    payload = {
        "type": "quote",
        "format": "webp",
        "backgroundColor": bg,
        "messages": [],
    }

    for msg in messages:
        entry = {
            "chatId": await _sender_id(msg),
            "text":   _text(msg),
            "avatar": True,
            "from": {
                "id":       await _sender_id(msg),
                "name":     await _sender_name(msg),
                "username": await _sender_username(msg),
                "type":     msg.chat.type.name.lower(),
                "photo":    await _sender_photo(msg),
            },
            "entities":    _entities(msg),
            "replyMessage": {},
        }

        if is_reply and msg.reply_to_message:
            r = msg.reply_to_message
            entry["replyMessage"] = {
                "name":   await _sender_name(r),
                "text":   _text(r),
                "chatId": await _sender_id(r),
            }

        payload["messages"].append(entry)

    last_err = "No APIs tried"
    for url in APIS:
        try:
            resp = await fetch.post(url, json=payload)
            if resp.status_code != 200:
                last_err = f"HTTP {resp.status_code} from {url}"
                continue

            ct = resp.headers.get("content-type", "")
            if "image" in ct:
                return resp.content

            data = resp.json()
            img  = (data.get("result") or {}).get("image") or data.get("image")
            if img:
                return base64.b64decode(img)
            last_err = data.get("error", "Unexpected response")
        except Exception as e:
            last_err = str(e)

    raise RuntimeError(f"All APIs failed — {last_err}")


# ── Handler ───────────────────────────────────────────────────────────────────
@app.on_message(filters.command("q") & filters.reply)
async def quote_cmd(client: Client, ctx: Message):
    is_reply, count, color = _parse_args(ctx.text)

    # Show help when /q help or /q colors
    if any(w in ctx.text.lower() for w in ("help", "colors", "colour")):
        return await ctx.reply_text(HELP_TEXT, parse_mode=enums.ParseMode.HTML)

    status = await ctx.reply_text("⏳ <b>Generating quote…</b>", parse_mode=enums.ParseMode.HTML)

    try:
        if count == 1:
            msgs = [ctx.reply_to_message]
        else:
            ids = list(range(ctx.reply_to_message.id, ctx.reply_to_message.id + count))
            fetched = await client.get_messages(ctx.chat.id, ids, replies=-1)
            msgs = [m for m in fetched if not m.empty]

        if not msgs:
            await status.delete()
            return await ctx.reply_text("❌ <b>No valid messages found.</b>", parse_mode=enums.ParseMode.HTML)

        image = await build_quote(msgs, is_reply, color)

        buf = BytesIO(image)
        buf.name = "quote.webp"
        await ctx.reply_sticker(sticker=buf, reply_to_message_id=ctx.reply_to_message.id)

    except Exception as e:
        await ctx.reply_text(
            f"⚠️ <b>Failed:</b> <code>{e}</code>",
            parse_mode=enums.ParseMode.HTML
        )
    finally:
        try: await status.delete()
        except: pass
