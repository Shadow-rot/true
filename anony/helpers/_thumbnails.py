import os
import aiohttp
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from anony import config
from anony.helpers import Track


class Thumbnail:
    def __init__(self):
        self.size = (1280, 720)

        try:
            self.font_title  = ImageFont.truetype("anony/helpers/Raleway-Bold.ttf", 52)
            self.font_artist = ImageFont.truetype("anony/helpers/Inter-Light.ttf", 28)
            self.font_small  = ImageFont.truetype("anony/helpers/Inter-Light.ttf", 22)
        except:
            self.font_title  = ImageFont.load_default()
            self.font_artist = ImageFont.load_default()
            self.font_small  = ImageFont.load_default()

    # ── Helpers ────────────────────────────────────────────────────────────

    def text_size(self, text, font):
        bbox = font.getbbox(text)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]

    def add_vignette(self, canvas: Image.Image) -> Image.Image:
        w, h = canvas.size
        vignette = Image.new("L", (w, h), 0)
        draw = ImageDraw.Draw(vignette)
        steps = min(w, h) // 2
        for i in range(steps):
            alpha = int(255 * (i / steps) ** 0.6)
            draw.ellipse([i, i, w - i, h - i], fill=alpha)
        vignette = vignette.filter(ImageFilter.GaussianBlur(55))
        black = Image.new("RGBA", (w, h), (0, 0, 0, 255))
        black.paste(canvas, mask=vignette)
        return black

    def add_gradient(self, canvas: Image.Image, start_y: int, end_alpha: int = 220):
        w, h = canvas.size
        grad = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(grad)
        for y in range(start_y, h):
            t = (y - start_y) / max(h - start_y, 1)
            a = int(end_alpha * (t ** 0.7))
            draw.line([(0, y), (w, y)], fill=(0, 0, 0, a))
        canvas.alpha_composite(grad)

    def paste_rounded(self, canvas: Image.Image, img: Image.Image, pos: tuple, radius: int = 22):
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, img.width, img.height], radius=radius, fill=255)
        canvas.paste(img, pos, mask=mask)

    def add_shadow(self, canvas: Image.Image, rect, radius: int = 22, layers: int = 5):
        for i in range(layers, 0, -1):
            s = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            d = ImageDraw.Draw(s)
            exp = i * 4
            d.rounded_rectangle(
                [rect[0] - exp, rect[1] + exp * 0.6,
                 rect[2] + exp, rect[3] + exp * 0.6],
                radius=radius + exp // 2, fill=(0, 0, 0, 35)
            )
            s = s.filter(ImageFilter.GaussianBlur(i * 2))
            canvas.alpha_composite(s)

    def add_glow(self, canvas: Image.Image, cx: int, cy: int, r: int, color=(0, 190, 255)):
        glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(glow)
        for i in range(3):
            spread = r + i * 30
            alpha = 40 - i * 12
            d.ellipse([cx - spread, cy - spread, cx + spread, cy + spread],
                      fill=(*color, alpha))
        glow = glow.filter(ImageFilter.GaussianBlur(25))
        canvas.alpha_composite(glow)

    def draw_eq_bars(self, draw: ImageDraw.Draw, cx: int, y: int, color=(0, 190, 255, 100)):
        heights = [18, 32, 48, 28, 44, 36, 52, 22, 40, 30, 46, 20, 38, 50, 26]
        bar_w, gap = 5, 5
        total = len(heights) * (bar_w + gap) - gap
        sx = cx - total // 2
        for i, h in enumerate(heights):
            bx = sx + i * (bar_w + gap)
            draw.rectangle([bx, y - h, bx + bar_w, y], fill=color)

    def draw_progress(self, canvas: Image.Image, bar_x, bar_y, bar_w, progress=0.0):
        bar_h = 5
        layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)

        # Track bg
        d.rounded_rectangle(
            [bar_x, bar_y, bar_x + bar_w, bar_y + bar_h],
            radius=3, fill=(255, 255, 255, 45)
        )
        # Filled portion
        fill_w = max(bar_h, int(bar_w * progress))
        d.rounded_rectangle(
            [bar_x, bar_y, bar_x + fill_w, bar_y + bar_h],
            radius=3, fill=(0, 190, 255, 255)
        )
        # Glowing dot at progress head
        dot_x = bar_x + fill_w
        dot_r = 7
        mid_y = bar_y + bar_h // 2
        for gr, a in [(14, 55), (10, 100), (7, 255)]:
            d.ellipse([dot_x - gr, mid_y - gr, dot_x + gr, mid_y + gr],
                      fill=(0, 190, 255, a))
        d.ellipse([dot_x - 4, mid_y - 4, dot_x + 4, mid_y + 4],
                  fill=(255, 255, 255, 255))

        canvas.alpha_composite(layer)

    async def download(self, path: str, url: str):
        async with aiohttp.ClientSession() as s:
            async with s.get(url) as r:
                with open(path, "wb") as f:
                    f.write(await r.read())

    # ── Main ───────────────────────────────────────────────────────────────

    async def generate(self, song: Track):
        try:
            os.makedirs("cache", exist_ok=True)
            temp   = f"cache/{song.id}_temp.jpg"
            output = f"cache/{song.id}.png"

            if os.path.exists(output):
                return output

            await self.download(temp, song.thumbnail)

            # ── Background ────────────────────────────────────────────────
            raw = Image.open(temp).convert("RGB")

            bg = raw.resize(self.size, Image.LANCZOS)
            bg = bg.filter(ImageFilter.GaussianBlur(45))
            bg = ImageEnhance.Brightness(bg).enhance(0.22)
            bg = ImageEnhance.Saturation(bg).enhance(1.8)
            canvas = bg.convert("RGBA")

            # Cinematic vignette
            canvas = self.add_vignette(canvas)

            # Bottom readability gradient
            self.add_gradient(canvas, start_y=360, end_alpha=210)

            # ── Album Art ─────────────────────────────────────────────────
            art_size = 360
            art_x = (1280 - art_size) // 2
            art_y = 68
            art_rect = [art_x, art_y, art_x + art_size, art_y + art_size]
            cx, cy = art_x + art_size // 2, art_y + art_size // 2

            # Glow behind art
            self.add_glow(canvas, cx, cy, art_size // 2 + 20, color=(0, 190, 255))

            # Drop shadow
            self.add_shadow(canvas, art_rect, radius=24, layers=6)

            # Album art
            art = raw.resize((art_size, art_size), Image.LANCZOS)
            art = ImageEnhance.Contrast(art).enhance(1.12)
            art = ImageEnhance.Sharpness(art).enhance(1.2)
            self.paste_rounded(canvas, art, (art_x, art_y), radius=22)

            # Subtle border ring
            ring = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            ImageDraw.Draw(ring).rounded_rectangle(
                [art_x - 1, art_y - 1, art_x + art_size + 1, art_y + art_size + 1],
                radius=23, outline=(255, 255, 255, 35), width=2
            )
            canvas.alpha_composite(ring)

            draw = ImageDraw.Draw(canvas)

            # ── Title ─────────────────────────────────────────────────────
            title = song.title[:34] + ("…" if len(song.title) > 34 else "")
            tw, _ = self.text_size(title, self.font_title)
            tx = (1280 - tw) // 2
            draw.text((tx + 2, 462), title, font=self.font_title, fill=(0, 0, 0, 140))
            draw.text((tx,     460), title, font=self.font_title, fill=(255, 255, 255, 255))

            # ── Artist ────────────────────────────────────────────────────
            artist = song.channel_name[:32] + ("…" if len(song.channel_name) > 32 else "")
            aw, _ = self.text_size(artist, self.font_artist)
            draw.text(((1280 - aw) // 2, 524), artist,
                      font=self.font_artist, fill=(160, 200, 255, 210))

            # ── Views ─────────────────────────────────────────────────────
            views = f"♪  {song.view_count} views"
            vw, _ = self.text_size(views, self.font_small)
            draw.text(((1280 - vw) // 2, 558), views,
                      font=self.font_small, fill=(110, 110, 130, 180))

            # ── Equalizer bars (decorative) ───────────────────────────────
            self.draw_eq_bars(draw, 640, 598, color=(0, 190, 255, 65))

            # ── Progress Bar ──────────────────────────────────────────────
            bar_w = 800
            bar_x = (1280 - bar_w) // 2
            bar_y = 618
            self.draw_progress(canvas, bar_x, bar_y, bar_w, progress=0.0)

            draw = ImageDraw.Draw(canvas)

            # Time labels
            draw.text((bar_x, bar_y + 16), "0:00",
                      font=self.font_small, fill=(110, 110, 130, 180))
            dur_w, _ = self.text_size(song.duration, self.font_small)
            draw.text((bar_x + bar_w - dur_w, bar_y + 16), song.duration,
                      font=self.font_small, fill=(110, 110, 130, 180))

            canvas.save(output, "PNG", optimize=True)
            os.remove(temp)
            return output

        except Exception as e:
            print("Thumbnail Error:", e)
            return config.DEFAULT_THUMB
