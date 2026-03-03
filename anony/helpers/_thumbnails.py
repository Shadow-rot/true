import os
import math
import random
import aiohttp
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from anony import config
from anony.helpers import Track


class Thumbnail:
    def __init__(self):
        self.W, self.H = 1280, 720

        try:
            self.f_title  = ImageFont.truetype("anony/helpers/Raleway-Bold.ttf", 52)
            self.f_sub    = ImageFont.truetype("anony/helpers/Inter-Light.ttf", 27)
            self.f_small  = ImageFont.truetype("anony/helpers/Inter-Light.ttf", 19)
            self.f_tiny   = ImageFont.truetype("anony/helpers/Inter-Light.ttf", 15)
            self.f_stat   = ImageFont.truetype("anony/helpers/Raleway-Bold.ttf", 22)
            self.f_badge  = ImageFont.truetype("anony/helpers/Raleway-Bold.ttf", 14)
            self.f_rbi    = ImageFont.truetype("anony/helpers/Raleway-Bold.ttf", 12)
        except:
            self.f_title = self.f_sub = self.f_small = self.f_tiny = \
            self.f_stat  = self.f_badge = self.f_rbi = ImageFont.load_default()

    # ── Helpers ────────────────────────────────────────────────────────────

    def tsize(self, text, font):
        bb = font.getbbox(text)
        return bb[2] - bb[0], bb[3] - bb[1]

    def wrap(self, text, font, max_w):
        words, lines, cur = text.split(), [], ""
        for word in words:
            test = (cur + " " + word).strip()
            if self.tsize(test, font)[0] <= max_w:
                cur = test
            else:
                lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        return lines

    def cover_crop(self, img, tw, th):
        iw, ih = img.size
        scale  = max(tw / iw, th / ih)
        nw, nh = int(iw * scale), int(ih * scale)
        img    = img.resize((nw, nh), Image.LANCZOS)
        cx     = (nw - tw) // 2
        cy     = (nh - th) // 2
        return img.crop((cx, cy, cx + tw, cy + th))

    def radial_glow(self, canvas, cx, cy, r, color, max_alpha=50):
        g = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(g)
        for i in range(16, 0, -1):
            t  = i / 16
            sp = int(r * t)
            a  = int(max_alpha * (1 - t) ** 0.5)
            d.ellipse([cx - sp, cy - sp, cx + sp, cy + sp], fill=(*color, a))
        g = g.filter(ImageFilter.GaussianBlur(45))
        canvas.alpha_composite(g)

    def add_card_shadow(self, canvas, x, y, w, h, radius=32):
        for i in range(8, 0, -1):
            sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            e  = i * 6
            ImageDraw.Draw(sh).rounded_rectangle(
                [x - e, y + e * 0.7, x + w + e, y + h + e * 0.7],
                radius=radius + e // 2, fill=(180, 100, 60, 18)
            )
            sh = sh.filter(ImageFilter.GaussianBlur(i * 4))
            canvas.alpha_composite(sh)

    def paste_rounded(self, canvas, img, pos, radius=22):
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, img.width, img.height], radius=radius, fill=255)
        layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        layer.paste(img.convert("RGBA"), pos, mask=mask)
        canvas.alpha_composite(layer)

    def draw_eq_bars(self, canvas, cx, base_y):
        heights = [18, 32, 52, 28, 46, 60, 36, 54, 24, 42, 64, 30, 48, 40, 20, 56, 32, 16, 44, 50]
        bw, gap  = 10, 6
        total    = len(heights) * (bw + gap) - gap
        sx       = cx - total // 2

        layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        d     = ImageDraw.Draw(layer)
        for i, bar_h in enumerate(heights):
            bx = sx + i * (bw + gap)
            for row in range(bar_h):
                t  = row / bar_h
                rc = int(210 - t * 60)
                gc = int(100 - t * 40)
                bc = int(50  - t * 20)
                ac = int(210 - t * 90)
                d.rectangle([bx, base_y - bar_h + row, bx + bw, base_y - bar_h + row + 1],
                             fill=(rc, gc, bc, ac))
            d.ellipse([bx - 1, base_y - bar_h - 4, bx + bw + 1, base_y - bar_h + bw - 4],
                      fill=(220, 110, 55, 200))

        glow = layer.filter(ImageFilter.GaussianBlur(3))
        canvas.alpha_composite(glow)
        canvas.alpha_composite(layer)

    def draw_progress(self, canvas, bar_x, bar_y, bar_w, duration):
        W, H = canvas.size
        pb   = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        pd   = ImageDraw.Draw(pb)

        pd.rounded_rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + 4],
                              radius=2, fill=(200, 165, 140, 160))
        dx, my = bar_x, bar_y + 2
        for gr, a in [(20, 40), (13, 80), (8, 180)]:
            pd.ellipse([dx - gr, my - gr, dx + gr, my + gr], fill=(210, 100, 50, a))
        pd.ellipse([dx - 6, my - 6, dx + 6, my + 6], fill=(255, 255, 255, 255))
        pd.ellipse([dx - 3, my - 3, dx + 3, my + 3], fill=(210, 100, 50, 255))

        canvas.alpha_composite(pb)

        draw = ImageDraw.Draw(canvas)
        draw.text((bar_x, bar_y + 12), "0:00",
                  font=self.f_small, fill=(140, 100, 70, 200))
        dw, _ = self.tsize(duration, self.f_small)
        draw.text((bar_x + bar_w - dw, bar_y + 12), duration,
                  font=self.f_small, fill=(140, 100, 70, 200))

    async def download(self, path, url):
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

            W, H = self.W, self.H
            raw  = Image.open(temp).convert("RGB")

            # ── Background: warm skin-tone gradient ───────────────────────
            canvas = Image.new("RGBA", (W, H), (245, 225, 210, 255))

            grad = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            gd   = ImageDraw.Draw(grad)
            for y in range(H):
                t = y / H
                gd.line([(0, y), (W, y)], fill=(
                    int(250 - t * 18),
                    int(228 - t * 22),
                    int(215 - t * 25), 255
                ))
            canvas.alpha_composite(grad)

            # Diagonal warm tint
            diag = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            dd   = ImageDraw.Draw(diag)
            for x in range(W):
                dd.line([(x, 0), (x, H)], fill=(200, 140, 100, int(30 * x / W)))
            canvas.alpha_composite(diag)

            # Noise texture
            random.seed(42)
            noise = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            nd    = noise.load()
            for y in range(H):
                for x in range(W):
                    v = random.randint(0, 255)
                    nd[x, y] = (v, v // 2, 0, random.randint(0, 6))
            canvas.alpha_composite(noise)

            # Radial glows
            self.radial_glow(canvas, 230, 360, 380, (255, 180, 140), max_alpha=70)
            self.radial_glow(canvas, 850, 320, 420, (255, 210, 180), max_alpha=55)
            self.radial_glow(canvas, 640, 680, 280, (230, 150, 100), max_alpha=40)

            # ── Left glass card ───────────────────────────────────────────
            CARD_W, CARD_H = 310, 390
            card_x = 55
            card_y = (H - CARD_H) // 2 - 10
            CX     = card_x + CARD_W // 2
            CY     = card_y + CARD_H // 2

            self.add_card_shadow(canvas, card_x, card_y, CARD_W, CARD_H)

            glass = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(glass).rounded_rectangle(
                [card_x, card_y, card_x + CARD_W, card_y + CARD_H],
                radius=28, fill=(255, 248, 242, 180)
            )
            canvas.alpha_composite(glass)

            border = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(border).rounded_rectangle(
                [card_x, card_y, card_x + CARD_W, card_y + CARD_H],
                radius=28, outline=(220, 170, 130, 120), width=1
            )
            canvas.alpha_composite(border)

            # Top inner highlight
            hl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(hl).rounded_rectangle(
                [card_x + 2, card_y + 2, card_x + CARD_W - 2, card_y + 40],
                radius=26, fill=(255, 255, 255, 80)
            )
            canvas.alpha_composite(hl)

            # ── Album art inside card (cover-crop) ────────────────────────
            ART_W, ART_H = 260, 230
            art_x = card_x + (CARD_W - ART_W) // 2
            art_y = card_y + 24

            art = self.cover_crop(raw, ART_W, ART_H)
            art = ImageEnhance.Contrast(art).enhance(1.08)
            art = ImageEnhance.Sharpness(art).enhance(1.2)
            self.paste_rounded(canvas, art, (art_x, art_y), radius=14)

            # Art border
            art_border = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(art_border).rounded_rectangle(
                [art_x, art_y, art_x + ART_W, art_y + ART_H],
                radius=14, outline=(220, 170, 130, 130), width=1
            )
            canvas.alpha_composite(art_border)

            draw = ImageDraw.Draw(canvas)

            # ── Card info below art ───────────────────────────────────────
            info_y = art_y + ART_H + 18

            # Song title truncated
            card_title = song.title[:28] + ("…" if len(song.title) > 28 else "")
            ct_w, ct_h = self.tsize(card_title, self.f_tiny)
            draw.text((card_x + (CARD_W - ct_w) // 2, info_y),
                      card_title, font=self.f_tiny, fill=(80, 50, 30, 220))

            # Artist
            ca_w, ca_h = self.tsize(song.channel_name[:24], self.f_tiny)
            draw.text((card_x + (CARD_W - ca_w) // 2, info_y + ct_h + 6),
                      song.channel_name[:24], font=self.f_tiny, fill=(150, 100, 65, 180))

            # RBI label + lock
            rt, _ = self.tsize("RBI REGISTERED", self.f_rbi)
            draw.text((CX - rt // 2, card_y + CARD_H - 40),
                      "RBI REGISTERED", font=self.f_rbi, fill=(160, 100, 60, 200))
            lk_x = CX - 7
            lk_y = card_y + CARD_H - 24
            draw.rounded_rectangle([lk_x, lk_y, lk_x + 14, lk_y + 10],
                                    radius=2, fill=(180, 120, 70, 120))
            draw.arc([lk_x + 2, lk_y - 7, lk_x + 12, lk_y + 3],
                     start=0, end=180, fill=(180, 120, 70, 150), width=2)

            # ── Right text section ────────────────────────────────────────
            RX        = card_x + CARD_W + 70
            RY        = 140
            content_w = W - RX - 50

            # NOW PLAYING badge
            badge_txt = "NOW PLAYING"
            bw3, bh3  = self.tsize(badge_txt, self.f_badge)
            pad3 = 12
            bl   = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(bl).rounded_rectangle(
                [RX, RY, RX + bw3 + pad3 * 2, RY + bh3 + 10],
                radius=20, fill=(210, 100, 50, 230)
            )
            canvas.alpha_composite(bl)
            draw = ImageDraw.Draw(canvas)
            draw.text((RX + pad3, RY + 5), badge_txt,
                      font=self.f_badge, fill=(255, 255, 255, 255))

            # Title
            ty = RY + bh3 + 28
            for line in self.wrap(song.title, self.f_title, content_w)[:2]:
                lw4, lh4 = self.tsize(line, self.f_title)
                draw.text((RX + 2, ty + 2), line, font=self.f_title, fill=(180, 120, 80, 60))
                draw.text((RX,     ty),     line, font=self.f_title, fill=(60,  35,  20, 255))
                ty += lh4 + 6

            # Warm accent underline
            acc = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            al  = acc.load()
            for x in range(RX, RX + 200):
                t = (x - RX) / 200
                a = int(240 * (1 - t ** 1.4))
                for dy in range(3):
                    if ty + 12 + dy < H:
                        al[x, ty + 12 + dy] = (210, 100, 50, a)
            canvas.alpha_composite(acc)
            draw = ImageDraw.Draw(canvas)

            # Artist subtitle
            draw.text((RX, ty + 26), song.channel_name[:30],
                      font=self.f_sub, fill=(140, 90, 55, 200))

            # Stats row
            ty += 80
            stat_data = [
                (song.duration,              "Duration"),
                (str(song.view_count),        "Views"),
                ("HD",                        "Quality"),
            ]
            sx = RX
            for val, label in stat_data:
                vw, vh = self.tsize(val,   self.f_stat)
                lw5, _ = self.tsize(label, self.f_tiny)
                box_w  = max(vw, lw5) + 28
                sb     = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                ImageDraw.Draw(sb).rounded_rectangle(
                    [sx, ty, sx + box_w, ty + vh + 24],
                    radius=12, fill=(220, 190, 165, 140)
                )
                canvas.alpha_composite(sb)
                draw = ImageDraw.Draw(canvas)
                draw.text((sx + 14, ty + 6),       val,   font=self.f_stat, fill=(70, 40, 20, 230))
                draw.text((sx + 14, ty + vh + 10), label, font=self.f_tiny, fill=(130, 90, 60, 180))
                sx += box_w + 18

            # ── EQ bars ───────────────────────────────────────────────────
            eq_cx   = RX + 280
            eq_base = H - 115
            self.draw_eq_bars(canvas, eq_cx, eq_base)

            # ── Progress bar ──────────────────────────────────────────────
            self.draw_progress(canvas, 60, H - 62, W - 120, song.duration)

            # ── Top sine accent line ──────────────────────────────────────
            top_acc = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ta_d    = ImageDraw.Draw(top_acc)
            for x in range(W):
                t = x / W
                a = int(200 * math.sin(t * math.pi))
                ta_d.point((x, 0), fill=(210, 100, 50, a))
                ta_d.point((x, 1), fill=(210, 100, 50, a // 2))
            canvas.alpha_composite(top_acc)

            canvas.save(output, "PNG", optimize=True)
            os.remove(temp)
            return output

        except Exception as e:
            print("Thumbnail Error:", e)
            return config.DEFAULT_THUMB
