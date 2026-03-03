# Modern Thumbnail Generator - Redesigned 2026

import os
import aiohttp
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
from anony import config
from anony.helpers import Track


class Thumbnail:
    def __init__(self):
        self.card_size = (960, 540)
        self.font_title = ImageFont.truetype("anony/helpers/Raleway-Bold.ttf", 48)
        self.font_info = ImageFont.truetype("anony/helpers/Inter-Light.ttf", 32)
        self.font_small = ImageFont.truetype("anony/helpers/Inter-Light.ttf", 26)

    async def save_thumb(self, path: str, url: str):
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                with open(path, "wb") as f:
                    f.write(await resp.read())

    async def generate(self, song: Track, size=(1280, 720)) -> str:
        try:
            os.makedirs("cache", exist_ok=True)
            temp = f"cache/temp_{song.id}.jpg"
            output = f"cache/{song.id}.png"

            if os.path.exists(output):
                return output

            await self.save_thumb(temp, song.thumbnail)

            # Background
            bg = Image.open(temp).convert("RGB").resize(size, Image.Resampling.LANCZOS)
            blur = bg.filter(ImageFilter.GaussianBlur(40))
            dark = ImageEnhance.Brightness(blur).enhance(0.45)
            base = dark.convert("RGBA")

            # Glass card effect
            card = ImageOps.fit(bg, self.card_size, Image.Resampling.LANCZOS)
            card = card.convert("RGBA")

            mask = Image.new("L", self.card_size, 0)
            draw_mask = ImageDraw.Draw(mask)
            draw_mask.rounded_rectangle((0, 0, *self.card_size), radius=40, fill=255)
            card.putalpha(mask)

            base.paste(card, (160, 60), card)

            draw = ImageDraw.Draw(base)

            # Song title
            title = song.title[:40]
            draw.text((100, 620), title, font=self.font_title, fill=(255, 255, 255))

            # Channel & Views
            info = f"{song.channel_name[:25]} • {song.view_count}"
            draw.text((100, 670), info, font=self.font_info, fill=(220, 220, 220))

            # Progress bar
            bar_x1, bar_y = 100, 710
            bar_x2 = 1180

            draw.rounded_rectangle(
                (bar_x1, bar_y, bar_x2, bar_y + 12),
                radius=6,
                fill=(255, 255, 255, 70),
            )

            # Fake smooth progress (10%)
            progress_width = bar_x1 + int((bar_x2 - bar_x1) * 0.15)

            draw.rounded_rectangle(
                (bar_x1, bar_y, progress_width, bar_y + 12),
                radius=6,
                fill=(0, 162, 255),
            )

            # Duration texts
            draw.text((100, 735), "0:00", font=self.font_small, fill=(255, 255, 255))
            draw.text((1120, 735), song.duration, font=self.font_small, fill=(255, 255, 255))

            base.save(output)
            os.remove(temp)

            return output

        except Exception:
            return config.DEFAULT_THUMB