import os
import textwrap
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from anony import app
import asyncio
import io
import time
import subprocess
import tempfile

FONT_PATH = "./AnonXMusic/assets/default.ttf"

font_cache = {}
recent_memes = {}

MEME_STYLES = {
    "classic": {"outline": "black", "text": "white", "outline_width": 3},
    "bold": {"outline": "black", "text": "yellow", "outline_width": 4},
    "shadow": {"outline": "#00000080", "text": "white", "outline_width": 2},
    "neon": {"outline": "#ff00ff", "text": "#00ffff", "outline_width": 2},
    "fire": {"outline": "#ff0000", "text": "#ffff00", "outline_width": 3},
    "ice": {"outline": "#0000ff", "text": "#00ffff", "outline_width": 3},
    "gold": {"outline": "#8B4513", "text": "#FFD700", "outline_width": 3},
    "silver": {"outline": "#404040", "text": "#C0C0C0", "outline_width": 3},
    "toxic": {"outline": "#00FF00", "text": "#000000", "outline_width": 4},
    "rainbow": {"outline": "#FF0000", "text": "#00FF00", "outline_width": 3},
}

def load_font_cached(size):
    if size not in font_cache:
        try:
            font_cache[size] = ImageFont.truetype(FONT_PATH, size)
        except:
            font_cache[size] = ImageFont.load_default()
    return font_cache[size]


def extract_first_frame(file_path):
    try:
        output_path = os.path.join(os.path.dirname(file_path), f"frame_{int(time.time())}.jpg")

        cmd = [
            'ffmpeg',
            '-i', file_path,
            '-vframes', '1',
            '-f', 'image2',
            '-q:v', '2',
            '-y',
            output_path
        ]

        result = subprocess.run(cmd, capture_output=True, stderr=subprocess.PIPE, timeout=10)

        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return output_path

        return None
    except Exception as e:
        print(f"FFmpeg error: {e}")
        return None


async def process_media_file(file_path):
    if not os.path.exists(file_path):
        raise Exception("File not found")

    file_name = os.path.basename(file_path).lower()
    file_ext = file_name.split('.')[-1] if '.' in file_name else ''

    video_formats = ['webm', 'mp4', 'mov', 'avi', 'mkv', 'gif', 'tgs', 'flv', 'wmv']

    if file_ext in video_formats or 'video' in file_name or 'sticker' in file_name:
        frame_path = await asyncio.to_thread(extract_first_frame, file_path)
        if frame_path and os.path.exists(frame_path):
            try:
                test_img = Image.open(frame_path)
                test_img.close()
                return frame_path, True
            except Exception as e:
                if os.path.exists(frame_path):
                    os.remove(frame_path)
                raise Exception(f"Extracted frame is invalid: {str(e)}")
        else:
            raise Exception("FFmpeg failed to extract frame")

    try:
        test_img = Image.open(file_path)
        test_img.close()
        return file_path, False
    except Exception as e:
        raise Exception(f"Cannot open image file: {str(e)}")


@app.on_message(filters.command(["mmf", "meme", "memify"]))
async def mmf(_, message: Message):
    reply = message.reply_to_message

    if not reply or not (reply.photo or reply.document or reply.sticker):
        help_text = """
🎨 Advanced Meme Maker

Basic Usage:
/mmf <text> - Top text only
/mmf <top>;<bottom> - Top & bottom text

Advanced Options:
/mmf <text> | style=<style>
/mmf <text> | pos=<position>
/mmf <text> | size=<10-200>
/mmf <text> | blur=<1-10>
/mmf <text> | brightness=<0.5-2.0>
/mmf <text> | contrast=<0.5-2.0>
/mmf <text> | rotate=<degrees>
/mmf <text> | x=<pixels> | y=<pixels>

Positions: top, bottom, center, top-left, top-right, bottom-left, bottom-right

Styles: classic, bold, shadow, neon, fire, ice, gold, silver, toxic, rainbow

Examples:
/mmf When you code at 3AM | style=neon | pos=center
/mmf Hello;World | style=fire | size=80
/mmf Custom Text | x=100 | y=150 | style=gold

Quick Commands:
/quickmeme <text> - Random style
/memestyles - View all styles
        """
        return await message.reply_text(help_text)

    if len(message.text.split()) < 2:
        return await message.reply_text("Give some text! Example: /mmf hello;world")

    start_time = time.time()

    text = message.text.split(None, 1)[1]
    options = parse_options(text)

    msg = await message.reply_text("⚡ Processing...")

    try:
        file_path = await app.download_media(reply)

        meme_bytes = await asyncio.to_thread(
            create_meme_ultra_fast,
            file_path,
            options
        )

        processing_time = round((time.time() - start_time) * 1000)

        user_id = message.from_user.id
        recent_memes[user_id] = {
            "file_path": file_path,
            "original_file": file_path,
            "options": options.copy(),
            "reply_id": reply.id,
            "timestamp": time.time()
        }

        buttons = [
            [
                InlineKeyboardButton("🔄 Remake", callback_data=f"meme_remake_{user_id}"),
                InlineKeyboardButton("🎨 Styles", callback_data=f"meme_style_{user_id}")
            ],
            [
                InlineKeyboardButton("📍 Position", callback_data=f"meme_pos_{user_id}"),
                InlineKeyboardButton("🎯 Effects", callback_data=f"meme_effects_{user_id}")
            ],
            [
                InlineKeyboardButton("🔤 Font Size", callback_data=f"meme_size_{user_id}"),
                InlineKeyboardButton("🔄 Rotate", callback_data=f"meme_rotate_{user_id}")
            ]
        ]

        await message.reply_document(
            document=io.BytesIO(meme_bytes),
            file_name=f"meme.webp",
            caption=f"✅ Created in {processing_time}ms\n"
                   f"Style: {options.get('style', 'classic')}\n"
                   f"Position: {options.get('position', 'top')}\n"
                   f"Size: {options.get('font_size', 'auto')}",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    except Exception as e:
        await message.reply_text(f"❌ Failed: {e}")
    finally:
        await msg.delete()


@app.on_callback_query(filters.regex(r"^meme_remake_"))
async def handle_remake(_, callback: CallbackQuery):
    user_id = int(callback.data.split("_")[-1])

    if callback.from_user.id != user_id:
        return await callback.answer("Not your meme!", show_alert=True)

    if user_id not in recent_memes:
        return await callback.answer("Meme expired! Create new one.", show_alert=True)

    buttons = [
        [
            InlineKeyboardButton("🎨 Style", callback_data=f"meme_style_{user_id}"),
            InlineKeyboardButton("📍 Position", callback_data=f"meme_pos_{user_id}")
        ],
        [
            InlineKeyboardButton("🎯 Effects", callback_data=f"meme_effects_{user_id}"),
            InlineKeyboardButton("🔤 Size", callback_data=f"meme_size_{user_id}")
        ],
        [
            InlineKeyboardButton("🔄 Rotate", callback_data=f"meme_rotate_{user_id}"),
            InlineKeyboardButton("💫 Presets", callback_data=f"meme_quick_{user_id}")
        ],
        [InlineKeyboardButton("❌ Close", callback_data=f"meme_close_{user_id}")]
    ]

    await callback.answer("Select option:")
    await callback.message.edit_reply_markup(InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex(r"^meme_style_"))
async def handle_style_selection(_, callback: CallbackQuery):
    user_id = int(callback.data.split("_")[-1])

    if callback.from_user.id != user_id:
        return await callback.answer("Not your meme!", show_alert=True)

    buttons = []
    styles_list = list(MEME_STYLES.keys())

    for i in range(0, len(styles_list), 3):
        row = []
        for j in range(3):
            if i + j < len(styles_list):
                style = styles_list[i + j]
                row.append(InlineKeyboardButton(
                    f"{style.title()}", 
                    callback_data=f"apply_style_{user_id}_{style}"
                ))
        buttons.append(row)

    buttons.append([InlineKeyboardButton("🔙 Back", callback_data=f"meme_remake_{user_id}")])

    await callback.answer()
    await callback.message.edit_reply_markup(InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex(r"^meme_pos_"))
async def handle_position_selection(_, callback: CallbackQuery):
    user_id = int(callback.data.split("_")[-1])

    if callback.from_user.id != user_id:
        return await callback.answer("Not your meme!", show_alert=True)

    buttons = [
        [
            InlineKeyboardButton("↖️ Top-L", callback_data=f"apply_pos_{user_id}_top-left"),
            InlineKeyboardButton("⬆️ Top", callback_data=f"apply_pos_{user_id}_top"),
            InlineKeyboardButton("↗️ Top-R", callback_data=f"apply_pos_{user_id}_top-right")
        ],
        [
            InlineKeyboardButton("⬅️ Left", callback_data=f"apply_pos_{user_id}_left"),
            InlineKeyboardButton("⭕ Center", callback_data=f"apply_pos_{user_id}_center"),
            InlineKeyboardButton("➡️ Right", callback_data=f"apply_pos_{user_id}_right")
        ],
        [
            InlineKeyboardButton("↙️ Bot-L", callback_data=f"apply_pos_{user_id}_bottom-left"),
            InlineKeyboardButton("⬇️ Bottom", callback_data=f"apply_pos_{user_id}_bottom"),
            InlineKeyboardButton("↘️ Bot-R", callback_data=f"apply_pos_{user_id}_bottom-right")
        ],
        [InlineKeyboardButton("🔙 Back", callback_data=f"meme_remake_{user_id}")]
    ]

    await callback.answer()
    await callback.message.edit_reply_markup(InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex(r"^meme_effects_"))
async def handle_effects_selection(_, callback: CallbackQuery):
    user_id = int(callback.data.split("_")[-1])

    if callback.from_user.id != user_id:
        return await callback.answer("Not your meme!", show_alert=True)

    buttons = [
        [
            InlineKeyboardButton("💫 Blur 2", callback_data=f"apply_blur_{user_id}_2"),
            InlineKeyboardButton("🌫️ Blur 5", callback_data=f"apply_blur_{user_id}_5")
        ],
        [
            InlineKeyboardButton("🔆 Bright", callback_data=f"apply_brightness_{user_id}_1.5"),
            InlineKeyboardButton("🔅 Dark", callback_data=f"apply_brightness_{user_id}_0.7")
        ],
        [
            InlineKeyboardButton("📈 Hi-Cont", callback_data=f"apply_contrast_{user_id}_1.5"),
            InlineKeyboardButton("📉 Lo-Cont", callback_data=f"apply_contrast_{user_id}_0.7")
        ],
        [
            InlineKeyboardButton("🎨 Saturate", callback_data=f"apply_saturation_{user_id}_1.5"),
            InlineKeyboardButton("⚪ Desat", callback_data=f"apply_saturation_{user_id}_0.5")
        ],
        [InlineKeyboardButton("🔙 Back", callback_data=f"meme_remake_{user_id}")]
    ]

    await callback.answer()
    await callback.message.edit_reply_markup(InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex(r"^meme_size_"))
async def handle_size_selection(_, callback: CallbackQuery):
    user_id = int(callback.data.split("_")[-1])

    if callback.from_user.id != user_id:
        return await callback.answer("Not your meme!", show_alert=True)

    buttons = [
        [
            InlineKeyboardButton("Tiny 30", callback_data=f"apply_size_{user_id}_30"),
            InlineKeyboardButton("Small 50", callback_data=f"apply_size_{user_id}_50")
        ],
        [
            InlineKeyboardButton("Med 70", callback_data=f"apply_size_{user_id}_70"),
            InlineKeyboardButton("Large 90", callback_data=f"apply_size_{user_id}_90")
        ],
        [
            InlineKeyboardButton("XL 120", callback_data=f"apply_size_{user_id}_120"),
            InlineKeyboardButton("XXL 150", callback_data=f"apply_size_{user_id}_150")
        ],
        [InlineKeyboardButton("🔙 Back", callback_data=f"meme_remake_{user_id}")]
    ]

    await callback.answer()
    await callback.message.edit_reply_markup(InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex(r"^meme_rotate_"))
async def handle_rotate_selection(_, callback: CallbackQuery):
    user_id = int(callback.data.split("_")[-1])

    if callback.from_user.id != user_id:
        return await callback.answer("Not your meme!", show_alert=True)

    buttons = [
        [
            InlineKeyboardButton("15°", callback_data=f"apply_rotate_{user_id}_15"),
            InlineKeyboardButton("30°", callback_data=f"apply_rotate_{user_id}_30"),
            InlineKeyboardButton("45°", callback_data=f"apply_rotate_{user_id}_45")
        ],
        [
            InlineKeyboardButton("90°", callback_data=f"apply_rotate_{user_id}_90"),
            InlineKeyboardButton("180°", callback_data=f"apply_rotate_{user_id}_180"),
            InlineKeyboardButton("270°", callback_data=f"apply_rotate_{user_id}_270")
        ],
        [
            InlineKeyboardButton("-15°", callback_data=f"apply_rotate_{user_id}_-15"),
            InlineKeyboardButton("-30°", callback_data=f"apply_rotate_{user_id}_-30"),
            InlineKeyboardButton("-45°", callback_data=f"apply_rotate_{user_id}_-45")
        ],
        [InlineKeyboardButton("🔙 Back", callback_data=f"meme_remake_{user_id}")]
    ]

    await callback.answer()
    await callback.message.edit_reply_markup(InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex(r"^meme_quick_"))
async def handle_quick_styles(_, callback: CallbackQuery):
    user_id = int(callback.data.split("_")[-1])

    if callback.from_user.id != user_id:
        return await callback.answer("Not your meme!", show_alert=True)

    buttons = [
        [InlineKeyboardButton("🔥 Trending", callback_data=f"apply_preset_{user_id}_trending")],
        [InlineKeyboardButton("💎 Premium", callback_data=f"apply_preset_{user_id}_premium")],
        [InlineKeyboardButton("😂 Funny", callback_data=f"apply_preset_{user_id}_funny")],
        [InlineKeyboardButton("🌈 Colorful", callback_data=f"apply_preset_{user_id}_colorful")],
        [InlineKeyboardButton("🔙 Back", callback_data=f"meme_remake_{user_id}")]
    ]

    await callback.answer()
    await callback.message.edit_reply_markup(InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex(r"^apply_style_"))
async def apply_style(_, callback: CallbackQuery):
    parts = callback.data.split("_")
    user_id = int(parts[2])
    new_style = parts[3]

    if callback.from_user.id != user_id:
        return await callback.answer("Not your meme!", show_alert=True)

    if user_id not in recent_memes:
        return await callback.answer("Meme expired!", show_alert=True)

    recent_memes[user_id]["options"]["style"] = new_style
    await regenerate_and_send(callback, user_id, f"Style: {new_style}")


@app.on_callback_query(filters.regex(r"^apply_pos_"))
async def apply_position(_, callback: CallbackQuery):
    parts = callback.data.split("_")
    user_id = int(parts[2])
    new_pos = parts[3]

    if callback.from_user.id != user_id:
        return await callback.answer("Not your meme!", show_alert=True)

    if user_id not in recent_memes:
        return await callback.answer("Meme expired!", show_alert=True)

    recent_memes[user_id]["options"]["position"] = new_pos
    await regenerate_and_send(callback, user_id, f"Position: {new_pos}")


@app.on_callback_query(filters.regex(r"^apply_blur_"))
async def apply_blur(_, callback: CallbackQuery):
    parts = callback.data.split("_")
    user_id = int(parts[2])
    blur_val = int(parts[3])

    if callback.from_user.id != user_id:
        return await callback.answer("Not your meme!", show_alert=True)

    if user_id not in recent_memes:
        return await callback.answer("Meme expired!", show_alert=True)

    recent_memes[user_id]["options"]["blur"] = blur_val
    await regenerate_and_send(callback, user_id, f"Blur: {blur_val}")


@app.on_callback_query(filters.regex(r"^apply_brightness_"))
async def apply_brightness(_, callback: CallbackQuery):
    parts = callback.data.split("_")
    user_id = int(parts[2])
    bright_val = float(parts[3])

    if callback.from_user.id != user_id:
        return await callback.answer("Not your meme!", show_alert=True)

    if user_id not in recent_memes:
        return await callback.answer("Meme expired!", show_alert=True)

    recent_memes[user_id]["options"]["brightness"] = bright_val
    await regenerate_and_send(callback, user_id, f"Brightness: {bright_val}")


@app.on_callback_query(filters.regex(r"^apply_contrast_"))
async def apply_contrast(_, callback: CallbackQuery):
    parts = callback.data.split("_")
    user_id = int(parts[2])
    contrast_val = float(parts[3])

    if callback.from_user.id != user_id:
        return await callback.answer("Not your meme!", show_alert=True)

    if user_id not in recent_memes:
        return await callback.answer("Meme expired!", show_alert=True)

    recent_memes[user_id]["options"]["contrast"] = contrast_val
    await regenerate_and_send(callback, user_id, f"Contrast: {contrast_val}")


@app.on_callback_query(filters.regex(r"^apply_saturation_"))
async def apply_saturation(_, callback: CallbackQuery):
    parts = callback.data.split("_")
    user_id = int(parts[2])
    sat_val = float(parts[3])

    if callback.from_user.id != user_id:
        return await callback.answer("Not your meme!", show_alert=True)

    if user_id not in recent_memes:
        return await callback.answer("Meme expired!", show_alert=True)

    recent_memes[user_id]["options"]["saturation"] = sat_val
    await regenerate_and_send(callback, user_id, f"Saturation: {sat_val}")


@app.on_callback_query(filters.regex(r"^apply_size_"))
async def apply_size(_, callback: CallbackQuery):
    parts = callback.data.split("_")
    user_id = int(parts[2])
    new_size = int(parts[3])

    if callback.from_user.id != user_id:
        return await callback.answer("Not your meme!", show_alert=True)

    if user_id not in recent_memes:
        return await callback.answer("Meme expired!", show_alert=True)

    recent_memes[user_id]["options"]["font_size"] = new_size
    await regenerate_and_send(callback, user_id, f"Size: {new_size}")


@app.on_callback_query(filters.regex(r"^apply_rotate_"))
async def apply_rotation(_, callback: CallbackQuery):
    parts = callback.data.split("_")
    user_id = int(parts[2])
    rotation = int(parts[3])

    if callback.from_user.id != user_id:
        return await callback.answer("Not your meme!", show_alert=True)

    if user_id not in recent_memes:
        return await callback.answer("Meme expired!", show_alert=True)

    recent_memes[user_id]["options"]["rotate"] = rotation
    await regenerate_and_send(callback, user_id, f"Rotate: {rotation}°")


@app.on_callback_query(filters.regex(r"^apply_preset_"))
async def apply_preset(_, callback: CallbackQuery):
    parts = callback.data.split("_")
    user_id = int(parts[2])
    preset = parts[3]

    if callback.from_user.id != user_id:
        return await callback.answer("Not your meme!", show_alert=True)

    if user_id not in recent_memes:
        return await callback.answer("Meme expired!", show_alert=True)

    presets = {
        "trending": {"style": "fire", "brightness": 1.2, "contrast": 1.3},
        "premium": {"style": "gold", "brightness": 1.1, "saturation": 1.2},
        "funny": {"style": "bold", "rotate": 5, "font_size": 90},
        "colorful": {"style": "rainbow", "saturation": 1.5, "contrast": 1.2}
    }

    if preset in presets:
        recent_memes[user_id]["options"].update(presets[preset])
        await regenerate_and_send(callback, user_id, f"Preset: {preset.title()}")


@app.on_callback_query(filters.regex(r"^meme_close_"))
async def close_menu(_, callback: CallbackQuery):
    user_id = int(callback.data.split("_")[-1])

    if callback.from