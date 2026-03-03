# Copyright (c) 2025 AnonymousX1025
# Licensed under the MIT License.
# This file is part of AnonXMusic

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
            self.f_h1    = ImageFont.truetype("anony/helpers/Raleway-Bold.ttf",  50)
            self.f_sub   = ImageFont.truetype("anony/helpers/Inter-Light.ttf",   24)
            self.f_small = ImageFont.truetype("anony/helpers/Inter-Light.ttf",   16)
            self.f_micro = ImageFont.truetype("anony/helpers/Inter-Light.ttf",   13)
            self.f_card  = ImageFont.truetype("anony/helpers/Inter-Light.ttf",   14)
            self.f_badge = ImageFont.truetype("anony/helpers/Raleway-Bold.ttf",  13)
            self.f_stat  = ImageFont.truetype("anony/helpers/Raleway-Bold.ttf",  19)
        except Exception:
            self.f_h1 = self.f_sub = self.f_small = self.f_micro = \
            self.f_card = self.f_badge = self.f_stat = ImageFont.load_default()

    # ── Helpers ────────────────────────────────────────────────────────────

    def ts(self, text, font):
        bb = font.getbbox(text)
        return bb[2] - bb[0], bb[3] - bb[1]

    def wrap(self, text, font, max_w):
        words, lines, cur = text.split(), [], ""
        for word in words:
            test = (cur + " " + word).strip()
            if self.ts(test, font)[0] <= max_w:
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

    def paste_rounded(self, canvas, img, pos, radius=20):
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [0, 0, img.width, img.height], radius=radius, fill=255
        )
        layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        layer.paste(img.convert("RGBA"), pos, mask=mask)
        canvas.alpha_composite(layer)

    def bloom(self, canvas, cx, cy, r, color, alpha=60):
        g = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(g)
        for i in range(22, 0, -1):
            t  = i / 22
            sp = int(r * t)
            a  = int(alpha * (1 - t) ** 0.35)
            d.ellipse([cx - sp, cy - sp, cx + sp, cy + sp], fill=(*color, a))
        g = g.filter(ImageFilter.GaussianBlur(55))
        canvas.alpha_composite(g)

    # ── Background ─────────────────────────────────────────────────────────

    def build_background(self, W, H):
        random.seed(42)
        canvas = Image.new("RGBA", (W, H), (242, 233, 220, 255))

        # Gradient
        grad = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd   = ImageDraw.Draw(grad)
        for y in range(H):
            t = y / H
            gd.line([(0, y), (W, y)], fill=(
                int(242 - t * 22), int(233 - t * 30), int(220 - t * 35), 255
            ))
        canvas.alpha_composite(grad)

        # Horizontal warmth
        warm = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        wd   = ImageDraw.Draw(warm)
        for x in range(W):
            wd.line([(x, 0), (x, H)], fill=(205, 145, 85, int(16 * x / W)))
        canvas.alpha_composite(warm)

        # Grain
        noise = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        nd    = noise.load()
        for y in range(H):
            for x in range(W):
                v = random.randint(0, 255)
                nd[x, y] = (v, int(v * 0.7), int(v * 0.42), random.randint(0, 5))
        canvas.alpha_composite(noise)

        # Vignette
        vig = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        for i in range(100):
            t = (100 - i) / 100
            a = int(38 * t ** 2.2)
            ImageDraw.Draw(vig).rectangle(
                [i, i, W - i, H - i], outline=(140, 105, 65, a), width=1
            )
        canvas.alpha_composite(vig)

        # Blooms
        self.bloom(canvas, -80,  -60, 600, (255, 228, 175), alpha=72)
        self.bloom(canvas,  870,  300, 480, (255, 215, 165), alpha=42)
        self.bloom(canvas,  380,  720, 340, (218, 178, 120), alpha=22)

        # Dust
        dust = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        dd   = ImageDraw.Draw(dust)
        for _ in range(90):
            px = random.randint(0, W)
            py = random.randint(0, H)
            pr = random.uniform(0.3, 1.8)
            v  = random.randint(215, 255)
            dd.ellipse(
                [px - pr, py - pr, px + pr, py + pr],
                fill=(v, int(v * 0.8), int(v * 0.5), random.randint(5, 22))
            )
        dust = dust.filter(ImageFilter.GaussianBlur(0.8))
        canvas.alpha_composite(dust)

        return canvas

    # ── Card ───────────────────────────────────────────────────────────────

    def draw_card(self, canvas, cx0, cy0, CW, CH):
        # 3-layer shadow
        for sp, oy_f, alph in [(60, 1.1, 10), (28, 0.65, 16), (12, 0.32, 22)]:
            sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            e  = sp
            oy = int(e * oy_f)
            ImageDraw.Draw(sh).rounded_rectangle(
                [cx0 - e, cy0 + oy, cx0 + CW + e, cy0 + CH + oy],
                radius=34 + e // 2, fill=(100, 72, 40, alph)
            )
            sh = sh.filter(ImageFilter.GaussianBlur(sp // 2 + 6))
            canvas.alpha_composite(sh)

        # Glass body
        card = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ImageDraw.Draw(card).rounded_rectangle(
            [cx0, cy0, cx0 + CW, cy0 + CH], radius=28, fill=(253, 249, 243, 210)
        )
        canvas.alpha_composite(card)

        # White border
        brd = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ImageDraw.Draw(brd).rounded_rectangle(
            [cx0, cy0, cx0 + CW, cy0 + CH],
            radius=28, outline=(255, 255, 255, 26), width=1
        )
        canvas.alpha_composite(brd)

        # Top reflection
        for ri in range(22):
            t  = ri / 22
            a  = int(115 * (1 - t) ** 2.4)
            rl = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            ImageDraw.Draw(rl).rounded_rectangle(
                [cx0 + ri, cy0 + ri, cx0 + CW - ri, cy0 + 40],
                radius=28 - ri, fill=(255, 255, 255, a)
            )
            canvas.alpha_composite(rl)

    # ── Artwork ────────────────────────────────────────────────────────────

    def draw_artwork(self, canvas, ax, ay, ART, raw_thumb):
        # Cover-crop real thumbnail, desaturate slightly for warmth
        art_img = self.cover_crop(raw_thumb, ART, ART)
        art_img = ImageEnhance.Color(art_img).enhance(0.82)
        art_img = ImageEnhance.Contrast(art_img).enhance(0.92)
        art_img = ImageEnhance.Brightness(art_img).enhance(0.85)

        # Sufi geometric overlay
        overlay = Image.new("RGBA", (ART, ART), (0, 0, 0, 0))
        od      = ImageDraw.Draw(overlay)
        acx, acy = ART // 2, ART // 2

        # Warm tint
        od.rectangle([0, 0, ART, ART], fill=(155, 98, 45, 72))

        # Rings
        for ri, rv in [(108, 50), (80, 72), (52, 100)]:
            od.ellipse([acx - ri, acy - ri, acx + ri, acy + ri],
                       outline=(255, 225, 155, rv), width=1)
        # 8-pt star
        for ao in [0, 45]:
            pts = []
            for a in range(8):
                ang = math.radians(a * 45 + ao)
                r2  = 85 if a % 2 == 0 else 55
                pts.append((acx + math.cos(ang) * r2, acy + math.sin(ang) * r2))
            od.polygon(pts, outline=(255, 218, 142, 65))
        # Spokes
        for deg in range(0, 360, 30):
            rad = math.radians(deg)
            od.line([
                (acx + math.cos(rad) * 28, acy + math.sin(rad) * 28),
                (acx + math.cos(rad) * 102, acy + math.sin(rad) * 102)
            ], fill=(255, 218, 142, 28), width=1)
        # Center glow
        for gi in range(9, 0, -1):
            od.ellipse([acx - gi * 4, acy - gi * 4, acx + gi * 4, acy + gi * 4],
                       fill=(255, 238, 185, 26 - gi * 2))
        od.ellipse([acx - 7, acy - 7, acx + 7, acy + 7], fill=(255, 242, 205, 165))

        base = art_img.convert("RGBA")
        base.alpha_composite(overlay)
        self.paste_rounded(canvas, base, (ax, ay), radius=20)

        # Warm glow around art
        ag = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        for gi in range(8, 0, -1):
            e2 = gi * 3
            a2 = 14 - gi
            ImageDraw.Draw(ag).rounded_rectangle(
                [ax - e2, ay - e2, ax + ART + e2, ay + ART + e2],
                radius=20 + e2, fill=(210, 160, 80, a2)
            )
        ag = ag.filter(ImageFilter.GaussianBlur(6))
        canvas.alpha_composite(ag)

        # 1px white border
        ab = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ImageDraw.Draw(ab).rounded_rectangle(
            [ax, ay, ax + ART, ay + ART],
            radius=20, outline=(255, 255, 255, 65), width=1
        )
        canvas.alpha_composite(ab)

        # Inner top shadow
        for ii in range(5):
            il = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            ImageDraw.Draw(il).rounded_rectangle(
                [ax + ii, ay + ii, ax + ART - ii, ay + 28],
                radius=20 - ii, fill=(80, 55, 25, 8 - ii)
            )
            canvas.alpha_composite(il)

    # ── EQ bars ────────────────────────────────────────────────────────────

    def draw_eq(self, canvas, eq_cx, eq_base):
        half_h  = [14, 26, 44, 22, 40, 54, 30, 48, 18, 36, 58, 24, 42, 34, 14, 50, 26, 10, 38, 46]
        heights = half_h + half_h[::-1]
        bw, gap = 7, 5
        total   = len(heights) * (bw + gap) - gap
        sx      = eq_cx - total // 2

        eq_l = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        eqd  = ImageDraw.Draw(eq_l)
        for i, bh in enumerate(heights):
            bx = sx + i * (bw + gap)
            for row in range(bh):
                t  = row / bh
                rc = int(182 + t * 58)
                gc = int(86  + t * 106)
                bc = int(36  + t * 108)
                ac = int(228 - t * 88)
                eqd.rectangle(
                    [bx, eq_base - bh + row, bx + bw, eq_base - bh + row + 1],
                    fill=(rc, gc, bc, ac)
                )
            eqd.ellipse(
                [bx - 1, eq_base - bh - 3, bx + bw + 1, eq_base - bh + bw - 3],
                fill=(210, 118, 48, 188)
            )

        # Bottom anchor shadow
        ba = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ImageDraw.Draw(ba).rectangle(
            [sx - 4, eq_base, sx + total + 4, eq_base + 4],
            fill=(148, 108, 60, 60)
        )
        ba = ba.filter(ImageFilter.GaussianBlur(4))
        canvas.alpha_composite(ba)

        glow = eq_l.filter(ImageFilter.GaussianBlur(3))
        canvas.alpha_composite(glow)
        canvas.alpha_composite(eq_l)

    # ── Progress bar ───────────────────────────────────────────────────────

    def draw_progress(self, canvas, bx0, by0, bwid, duration, progress=0.15):
        pb  = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        pbd = ImageDraw.Draw(pb)

        # Track
        pbd.rounded_rectangle(
            [bx0, by0, bx0 + bwid, by0 + 3],
            radius=2, fill=(195, 168, 138, 135)
        )

        # Gradient fill
        fill_w = max(4, int(bwid * progress))
        for x in range(bx0, bx0 + fill_w):
            t  = (x - bx0) / fill_w
            rc = int(196 + t * 40)
            gc = int(104 + t * 90)
            bc = int(52  + t * 88)
            pbd.line([(x, by0), (x, by0 + 3)], fill=(rc, gc, bc, 220))

        # Slider glow + dot
        dx, my = bx0 + fill_w, by0 + 1
        for gr, a in [(20, 22), (13, 50), (8, 115), (5, 195)]:
            pbd.ellipse([dx - gr, my - gr, dx + gr, my + gr], fill=(196, 104, 52, a))
        pbd.ellipse([dx - 5, my - 5, dx + 5, my + 5], fill=(252, 248, 242, 255))
        pbd.ellipse([dx - 2, my - 2, dx + 2, my + 2], fill=(196, 104, 52, 255))

        canvas.alpha_composite(pb)

        draw = ImageDraw.Draw(canvas)
        draw.text((bx0, by0 + 10), "0:00",
                  font=self.f_small, fill=(118, 88, 58, 210))
        dw, _ = self.ts(duration, self.f_small)
        draw.text((bx0 + bwid - dw, by0 + 10), duration,
                  font=self.f_small, fill=(118, 88, 58, 210))

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

            # ── Background ────────────────────────────────────────────────
            canvas = self.build_background(W, H)

            # ── Left card ─────────────────────────────────────────────────
            CW, CH = 318, 432
            cx0    = 62
            cy0    = (H - CH) // 2 - 8
            CCX    = cx0 + CW // 2

            self.draw_card(canvas, cx0, cy0, CW, CH)

            # Artwork
            ART = 254
            ax  = cx0 + (CW - ART) // 2
            ay  = cy0 + 28
            self.draw_artwork(canvas, ax, ay, ART, raw)

            # Card micro text
            draw = ImageDraw.Draw(canvas)

            song_lbl = song.title[:24] + ("…" if len(song.title) > 24 else "")
            slw, slh = self.ts(song_lbl, self.f_card)
            draw.text((CCX - slw // 2, ay + ART + 14),
                      song_lbl, font=self.f_card, fill=(62, 42, 22, 230))

            art_lbl = song.channel_name[:28]
            alw, alh = self.ts(art_lbl, self.f_micro)
            draw.text((CCX - alw // 2, ay + ART + 14 + slh + 4),
                      art_lbl, font=self.f_micro, fill=(120, 88, 55, 175))

            # Verified badge
            vbt      = "✓  siyabot"
            vbw, vbh = self.ts(vbt, self.f_micro)
            vby      = ay + ART + 14 + slh + alh + 16
            vbs = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(vbs).rounded_rectangle(
                [CCX - vbw // 2 - 11, vby + 2, CCX + vbw // 2 + 11, vby + vbh + 10],
                radius=11, fill=(155, 112, 62, 45)
            )
            vbs = vbs.filter(ImageFilter.GaussianBlur(3))
            canvas.alpha_composite(vbs)
            vbl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(vbl).rounded_rectangle(
                [CCX - vbw // 2 - 11, vby, CCX + vbw // 2 + 11, vby + vbh + 8],
                radius=11, fill=(222, 190, 142, 190)
            )
            canvas.alpha_composite(vbl)
            draw = ImageDraw.Draw(canvas)
            draw.text((CCX - vbw // 2, vby + 4), vbt,
                      font=self.f_micro, fill=(68, 42, 18, 240))

            # ── Right content ─────────────────────────────────────────────
            RX = cx0 + CW + 68
            RY = 118
            RW = W - RX - 52

            # NOW PLAYING badge
            bt       = "NOW PLAYING"
            bw2, bh2 = self.ts(bt, self.f_badge)
            pad      = 14
            bsh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(bsh).rounded_rectangle(
                [RX, RY + 3, RX + bw2 + pad * 2, RY + bh2 + 13],
                radius=22, fill=(150, 72, 25, 55)
            )
            bsh = bsh.filter(ImageFilter.GaussianBlur(5))
            canvas.alpha_composite(bsh)
            bl2 = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(bl2).rounded_rectangle(
                [RX, RY, RX + bw2 + pad * 2, RY + bh2 + 10],
                radius=22, fill=(196, 104, 52, 240)
            )
            canvas.alpha_composite(bl2)
            draw = ImageDraw.Draw(canvas)
            draw.text((RX + pad, RY + 5), bt,
                      font=self.f_badge, fill=(255, 255, 255, 255))

            # Title — deep brown, strong contrast
            ty    = RY + bh2 + 28
            lines = self.wrap(song.title, self.f_h1, RW)
            for line in lines[:2]:
                lw, lh = self.ts(line, self.f_h1)
                draw.text((RX + 2, ty + 2), line, font=self.f_h1, fill=(195, 152, 98, 45))
                draw.text((RX,     ty),     line, font=self.f_h1, fill=(46,  31,  22, 255))
                ty += lh + 4

            # Accent divider 2px
            acc_w  = int(RW * 0.38)
            acc_y  = ty + 12
            acc_l  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            acc_px = acc_l.load()
            for x in range(RX, RX + acc_w):
                t2 = (x - RX) / acc_w
                a  = int(255 * (1 - t2 ** 1.5))
                for dy in range(2):
                    if acc_y + dy < H:
                        acc_px[x, acc_y + dy] = (196, 104, 52, a)
            ImageDraw.Draw(acc_l).ellipse(
                [RX - 1, acc_y - 1, RX + 4, acc_y + 3], fill=(196, 104, 52, 230)
            )
            canvas.alpha_composite(acc_l)
            draw = ImageDraw.Draw(canvas)

            # Artist — stronger contrast
            draw.text((RX, acc_y + 16), song.channel_name[:34],
                      font=self.f_sub, fill=(95, 72, 52, 230))

            # Metadata pills
            meta_y  = acc_y + 68
            meta_sx = RX
            meta_items = [
                (song.duration,        "Duration"),
                (str(song.view_count), "Views"),
                ("HD",                 "Quality"),
            ]
            for val, label in meta_items:
                vw, vh = self.ts(val,   self.f_stat)
                lw3, _ = self.ts(label, self.f_micro)
                pw     = max(vw, lw3) + 34
                ph     = vh + 28

                for blur, sa, se in [(9, 16, 7), (4, 25, 3)]:
                    ps = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                    ImageDraw.Draw(ps).rounded_rectangle(
                        [meta_sx - se, meta_y + se, meta_sx + pw + se, meta_y + ph + se],
                        radius=16 + se, fill=(148, 118, 72, sa)
                    )
                    ps = ps.filter(ImageFilter.GaussianBlur(blur))
                    canvas.alpha_composite(ps)

                pill = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                ImageDraw.Draw(pill).rounded_rectangle(
                    [meta_sx, meta_y, meta_sx + pw, meta_y + ph],
                    radius=16, fill=(250, 244, 234, 200)
                )
                canvas.alpha_composite(pill)

                for ii in range(4):
                    il = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                    ImageDraw.Draw(il).rounded_rectangle(
                        [meta_sx + ii, meta_y + ii, meta_sx + pw - ii, meta_y + 12],
                        radius=16 - ii, fill=(148, 118, 72, 9 - ii * 2)
                    )
                    canvas.alpha_composite(il)

                pb3 = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                ImageDraw.Draw(pb3).rounded_rectangle(
                    [meta_sx, meta_y, meta_sx + pw, meta_y + ph],
                    radius=16, outline=(200, 165, 118, 105), width=1
                )
                canvas.alpha_composite(pb3)
                draw = ImageDraw.Draw(canvas)
                draw.text((meta_sx + 17, meta_y + 6),       val,   font=self.f_stat,  fill=(62,  38,  18, 248))
                draw.text((meta_sx + 17, meta_y + vh + 11), label, font=self.f_micro, fill=(128, 95,  60, 190))
                meta_sx += pw + 14

            # ── EQ bars ───────────────────────────────────────────────────
            self.draw_eq(canvas, RX + RW // 2 - 8, H - 108)

            # ── Progress bar ──────────────────────────────────────────────
            self.draw_progress(canvas, 62, H - 52, W - 124, song.duration)

            # ── Top sine accent ───────────────────────────────────────────
            topa = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            tad  = ImageDraw.Draw(topa)
            for x in range(W):
                t = x / W
                a = int(165 * math.sin(t * math.pi))
                tad.point((x, 0), fill=(196, 104, 52, a))
                tad.point((x, 1), fill=(196, 104, 52, a // 2))
            canvas.alpha_composite(topa)

            # ── Cinematic DoF vignette ────────────────────────────────────
            dof = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            for i in range(75):
                t = (75 - i) / 75
                a = int(24 * t ** 3)
                ImageDraw.Draw(dof).rectangle(
                    [i, i, W - i, H - i], outline=(175, 138, 90, a), width=1
                )
            canvas.alpha_composite(dof)

            canvas.save(output, "PNG", optimize=True)
            os.remove(temp)
            return output

        except Exception as e:
            print("Thumbnail Error:", e)
            return config.DEFAULT_THUMB
