import os
import aiohttp
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageEnhance
from anony import config
from anony.helpers import Track


class Thumbnail:
    def __init__(self):
        self.size = (1280, 720)
        self.card_size = (820, 460)

        self.font_big = ImageFont.truetype("anony/helpers/Raleway-Bold.ttf", 60)
        self.font_mid = ImageFont.truetype("anony/helpers/Inter-Light.ttf", 34)
        self.font_small = ImageFont.truetype("anony/helpers/Inter-Light.ttf", 28)

    async def download(self, path: str, url: str):
        async with aiohttp.ClientSession() as s:
            async with s.get(url) as r:
                with open(path, "wb") as f:
                    f.write(await r.read())

    async def generate(self, song: Track) -> str:
        try:
            os.makedirs("cache", exist_ok=True)

            temp = f"cache/temp_{song.id}.jpg"
            output = f"cache/{song.id}.png"

            if os.path.exists(output):
                return output

            await self.download(temp, song.thumbnail)

            # Background
            bg = Image.open(temp).convert("RGB").resize(self.size, Image.Resampling.LANCZOS)
            blur = bg.filter(ImageFilter.GaussianBlur(35))
            dark = ImageEnhance.Brightness(blur).enhance(0.35)
            canvas = dark.convert("RGBA")

            # Center Card
            thumb = Image.open(temp).convert("RGB")
            card = ImageOps.fit(thumb, self.card_size, Image.Resampling.LANCZOS)

            mask = Image.new("L", self.card_size, 0)
            draw_mask = ImageDraw.Draw(mask)
            draw_mask.rounded_rectangle((0, 0, *self.card_size), 45, fill=255)
            card.putalpha(mask)

            pos = ((self.size[0] - self.card_size[0]) // 2, 90)
            canvas.paste(card, pos, card)

            draw = ImageDraw.Draw(canvas)

            # Title Centered
            title = song.title[:35]
            w, h = draw.textbbox((0, 0), title, font=self.font_big)[2:]
            draw.text(((1280 - w) // 2, 580), title, font=self.font_big, fill="white")

            # Channel + Views
            info = f"{song.channel_name[:25]} • {song.view_count}"
            w2, _ = draw.textbbox((0, 0), info, font=self.font_mid)[2:]
            draw.text(((1280 - w2) // 2, 645), info, font=self.font_mid, fill=(220, 220, 220))

            # Modern Progress Bar
            bar_width = 900
            bar_height = 14
            bar_x = (1280 - bar_width) // 2
            bar_y = 690

            draw.rounded_rectangle(
                (bar_x, bar_y, bar_x + bar_width, bar_y + bar_height),
                radius=7,
                fill=(255, 255, 255, 60)
            )

            # Progress (fake 20%)
            progress = int(bar_width * 0.2)

            draw.rounded_rectangle(
                (bar_x, bar_y, bar_x + progress, bar_y + bar_height),
                radius=7,
                fill=(0, 200, 255)
            )

            # Duration Text
            draw.text((bar_x - 70, 685), "0:00", font=self.font_small, fill="white")
            draw.text((bar_x + bar_width + 15, 685), song.duration, font=self.font_small, fill="white")

            canvas.save(output)
            os.remove(temp)

            return output

        except Exception:
            return config.DEFAULT_THUMB