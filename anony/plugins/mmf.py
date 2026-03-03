from io import BytesIO
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from anony import app
from httpx import AsyncClient, Timeout
import json

fetch = AsyncClient(
    http2=True,
    verify=False,
    headers={
        "Accept-Language": "en-US,en;q=0.9",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    },
    timeout=Timeout(30),
)

class QuotlyException(Exception):
    pass

QUOTE_APIS = [
    "https://bot.lyo.su/quote/generate",
    "https://qoute-api-bice.vercel.app/generate",
]

async def get_message_sender_id(ctx: Message):
    if ctx.forward_date:
        return (
            1 if ctx.forward_sender_name
            else ctx.forward_from.id if ctx.forward_from
            else ctx.forward_from_chat.id if ctx.forward_from_chat
            else 1
        )
    return ctx.from_user.id if ctx.from_user else ctx.sender_chat.id if ctx.sender_chat else 1

async def get_message_sender_name(ctx: Message):
    if ctx.forward_date:
        if ctx.forward_sender_name:
            return ctx.forward_sender_name
        elif ctx.forward_from:
            return f"{ctx.forward_from.first_name} {ctx.forward_from.last_name}".strip() if ctx.forward_from.last_name else ctx.forward_from.first_name
        elif ctx.forward_from_chat:
            return ctx.forward_from_chat.title
        return ""
    
    if ctx.from_user:
        return f"{ctx.from_user.first_name} {ctx.from_user.last_name}".strip() if ctx.from_user.last_name else ctx.from_user.first_name
    return ctx.sender_chat.title if ctx.sender_chat else ""

async def get_message_sender_username(ctx: Message):
    if ctx.forward_date:
        if ctx.forward_from and ctx.forward_from.username:
            return ctx.forward_from.username
        elif ctx.forward_from_chat and ctx.forward_from_chat.username:
            return ctx.forward_from_chat.username
        return ""
    
    if ctx.from_user and ctx.from_user.username:
        return ctx.from_user.username
    return ctx.sender_chat.username if ctx.sender_chat and ctx.sender_chat.username else ""

async def get_message_sender_photo(ctx: Message):
    photo_data = None
    
    if ctx.forward_date:
        if ctx.forward_from and ctx.forward_from.photo:
            photo_data = ctx.forward_from.photo
        elif ctx.forward_from_chat and ctx.forward_from_chat.photo:
            photo_data = ctx.forward_from_chat.photo
    else:
        if ctx.from_user and ctx.from_user.photo:
            photo_data = ctx.from_user.photo
        elif ctx.sender_chat and ctx.sender_chat.photo:
            photo_data = ctx.sender_chat.photo
    
    if photo_data:
        return {
            "small_file_id": photo_data.small_file_id,
            "small_photo_unique_id": photo_data.small_photo_unique_id,
            "big_file_id": photo_data.big_file_id,
            "big_photo_unique_id": photo_data.big_photo_unique_id,
        }
    return ""

async def get_text_or_caption(ctx: Message):
    if ctx.text:
        return ctx.text
    elif ctx.caption:
        return ctx.caption
    elif ctx.sticker:
        return ctx.sticker.emoji or "[Sticker]"
    elif ctx.photo:
        return "[Photo]"
    elif ctx.video:
        return "[Video]"
    elif ctx.audio:
        return "[Audio]"
    elif ctx.voice:
        return "[Voice Message]"
    elif ctx.document:
        return "[Document]"
    elif ctx.animation:
        return "[GIF]"
    return "[Message]"

async def generate_quote_with_api(api_url: str, payload: dict) -> bytes:
    try:
        response = await fetch.post(api_url, json=payload)
        
        if response.status_code == 200:
            content_type = response.headers.get('content-type', '')
            
            if 'image' in content_type or api_url.endswith('.png'):
                return response.content
            else:
                data = response.json()
                if 'result' in data and 'image' in data['result']:
                    import base64
                    return base64.b64decode(data['result']['image'])
                elif 'image' in data:
                    import base64
                    return base64.b64decode(data['image'])
                elif 'ok' in data and not data['ok']:
                    raise QuotlyException(f"API Error: {data.get('error', 'Unknown error')}")
                else:
                    return response.content
        else:
            raise QuotlyException(f"HTTP {response.status_code}")
    except Exception as e:
        raise QuotlyException(f"{api_url}: {str(e)}")

async def pyrogram_to_quotly(messages, is_reply):
    if not isinstance(messages, list):
        messages = [messages]
    
    payload = {
        "type": "quote",
        "format": "webp",
        "backgroundColor": "#1b1429",
        "messages": [],
    }
    
    for message in messages:
        entities_list = []
        
        if message.entities:
            entities_list = [
                {
                    "type": entity.type.name.lower(),
                    "offset": entity.offset,
                    "length": entity.length,
                }
                for entity in message.entities
            ]
        elif message.caption_entities:
            entities_list = [
                {
                    "type": entity.type.name.lower(),
                    "offset": entity.offset,
                    "length": entity.length,
                }
                for entity in message.caption_entities
            ]
        
        message_dict = {
            "chatId": await get_message_sender_id(message),
            "text": await get_text_or_caption(message),
            "avatar": True,
            "from": {
                "id": await get_message_sender_id(message),
                "name": await get_message_sender_name(message),
                "username": await get_message_sender_username(message),
                "type": message.chat.type.name.lower(),
                "photo": await get_message_sender_photo(message),
            },
            "entities": entities_list,
            "replyMessage": {}
        }
        
        if message.reply_to_message and is_reply:
            message_dict["replyMessage"] = {
                "name": await get_message_sender_name(message.reply_to_message),
                "text": await get_text_or_caption(message.reply_to_message),
                "chatId": await get_message_sender_id(message.reply_to_message),
            }
        
        payload["messages"].append(message_dict)
    
    last_error = None
    for api_url in QUOTE_APIS:
        try:
            result = await generate_quote_with_api(api_url, payload)
            return result
        except QuotlyException as e:
            last_error = str(e)
            continue
    
    raise QuotlyException(f"All APIs failed. Last error: {last_error}")

def parse_arguments(text):
    args = text.split()[1:]
    is_reply = False
    count = 1
    
    for arg in args:
        if arg.lower() == 'r':
            is_reply = True
        else:
            try:
                num = int(arg)
                if 1 <= num <= 10:
                    count = num
            except ValueError:
                continue
    
    return is_reply, count

@app.on_message(filters.command("q") & filters.reply)
async def quotly_handler(client: Client, ctx: Message):
    is_reply, count = parse_arguments(ctx.text)
    
    if count < 1 or count > 10:
        return await ctx.reply_text(
            "<b>⚠️ Invalid Range</b>\n<i>Please use 1-10 messages</i>",
            parse_mode=enums.ParseMode.HTML
        )
    
    processing_msg = await ctx.reply_text(
        "<b>⏳ Generating Quote...</b>",
        parse_mode=enums.ParseMode.HTML
    )
    
    try:
        if count == 1:
            messages = [ctx.reply_to_message]
        else:
            message_ids = list(range(
                ctx.reply_to_message.id,
                ctx.reply_to_message.id + count
            ))
            
            fetched_messages = await client.get_messages(
                chat_id=ctx.chat.id,
                message_ids=message_ids,
                replies=-1,
            )
            
            messages = [msg for msg in fetched_messages if not msg.empty]
        
        if not messages:
            await processing_msg.delete()
            return await ctx.reply_text(
                "<b>❌ No Valid Messages</b>\n<i>Could not fetch messages</i>",
                parse_mode=enums.ParseMode.HTML
            )
        
        quote_image = await pyrogram_to_quotly(messages, is_reply=is_reply)
        
        bio_sticker = BytesIO(quote_image)
        bio_sticker.name = "quote.webp"
        
        await ctx.reply_sticker(
            sticker=bio_sticker,
            reply_to_message_id=ctx.reply_to_message.id
        )
        
    except QuotlyException as e:
        await ctx.reply_text(
            f"<b>⚠️ Quote Generation Failed</b>\n<code>{str(e)}</code>",
            parse_mode=enums.ParseMode.HTML
        )
    except Exception as e:
        await ctx.reply_text(
            f"<b>❌ Error Occurred</b>\n<code>{str(e)}</code>",
            parse_mode=enums.ParseMode.HTML
        )
    finally:
        try:
            await processing_msg.delete()
        except:
            pass