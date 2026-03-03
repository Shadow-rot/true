import os
import aiohttp
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from anony import config
from anony.helpers import Track


class Thumbnail:
    def __init__(self):
        self.size = (1280, 720)
        self.card_size = (800, 450)

        # Safe font loading
        try:
            self.font_big = ImageFont.truetype("anony/helpers/Raleway-Bold.ttf", 55)
            self.font_mid = ImageFont.truetype("anony/helpers/Inter-Light.ttf", 30)
            self.font_small = ImageFont.truetype("anony/helpers/Inter-Light.ttf", 25)
        except:
            self.font_big = ImageFont.load_default()
            self.font_mid = ImageFont.load_default()
            self.font_small = ImageFont.load_default()

    async def download(self, path, url):
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                with open(path, "wb") as f:
                    f.write(await resp.read())

    async def generate(self, song: Track):
        try:
            os.makedirs("cache", exist_ok=True)

            temp = f"cache/{song.id}_temp.jpg"
            output = f"cache/{song.id}.png"

            if os.path.exists(output):
                return output

            await self.download(temp, song.thumbnail)

            # Background
            bg = Image.open(temp).convert("RGB").resize(self.size)
            bg = bg.filter(ImageFilter.GaussianBlur(30))
            bg = ImageEnhance.Brightness(bg).enhance(0.4)

            canvas = bg.convert("RGBA")

            # Center card
            thumb = Image.open(temp).convert("RGB")
            thumb = thumb.resize(self.card_size)

            card_x = (self.size[0] - self.card_size[0]) // 2
            card_y = 80

            canvas.paste(thumb, (card_x, card_y))

            draw = ImageDraw.Draw(canvas)

            # Title
            title = song.title[:40]
            w, h = draw.textsize(title, font=self.font_big)
            draw.text(((1280 - w) // 2, 560), title, font=self.font_big, fill="white")

            # Channel + views
            info = f"{song.channel_name[:25]} • {song.view_count}"
            w2, _ = draw.textsize(info, font=self.font_mid)
            draw.text(((1280 - w2) // 2, 620), info, font=self.font_mid, fill="white")

            # Progress bar
            bar_w = 900
            bar_x = (1280 - bar_w) // 2
            bar_y = 670

            draw.rectangle((bar_x, bar_y, bar_x + bar_w, bar_y + 10), fill=(255, 255, 255, 80))
            draw.rectangle((bar_x, bar_y, bar_x + int(bar_w * 0.25), bar_y + 10), fill=(0, 200, 255))

            # Time text
            draw.text((bar_x - 60, bar_y - 5), "0:00", font=self.font_small, fill="white")
            draw.text((bar_x + bar_w + 10, bar_y - 5), song.duration, font=self.font_small, fill="white")

            canvas.save(output)
            os.remove(temp)

            return output

        except Exception as e:
            print("Thumbnail Error:", e)
            return config.DEFAULT_THUMB