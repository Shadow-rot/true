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
            self.f_h1    = ImageFont.truetype("anony/helpers/Raleway-Bold.ttf",   48)
            self.f_sub   = ImageFont.truetype("anony/helpers/Inter-Light.ttf",    25)
            self.f_body  = ImageFont.truetype("anony/helpers/Inter-Light.ttf",    19)
            self.f_small = ImageFont.truetype("anony/helpers/Inter-Light.ttf",    16)
            self.f_micro = ImageFont.truetype("anony/helpers/Inter-Light.ttf",    13)
            self.f_badge = ImageFont.truetype("anony/helpers/Raleway-Bold.ttf",   13)
            self.f_stat  = ImageFont.truetype("anony/helpers/Raleway-Bold.ttf",   19)
        except Exception:
            self.f_h1 = self.f_sub = self.f_body = self.f_small = \
            self.f_micro = self.f_badge = self.f_stat = ImageFont.load_default()

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

    def bloom(self, canvas, cx, cy, r, color, alpha=55):
        g = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(g)
        for i in range(22, 0, -1):
            t  = i / 22
            sp = int(r * t)
            a  = int(alpha * (1 - t) ** 0.38)
            d.ellipse([cx - sp, cy - sp, cx + sp, cy + sp], fill=(*color, a))
        g = g.filter(ImageFilter.GaussianBlur(60))
        canvas.alpha_composite(g)

    def draw_card_shadow(self, canvas, cx0, cy0, cw, ch):
        for spread, oy_f, alpha in [(40, 0.9, 10), (22, 0.6, 14), (10, 0.35, 20)]:
            sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            e  = spread
            oy = int(e * oy_f)
            ImageDraw.Draw(sh).rounded_rectangle(
                [cx0 - e, cy0 + oy, cx0 + cw + e, cy0 + ch + oy],
                radius=32 + e // 2, fill=(120, 90, 55, alpha)
            )
            sh = sh.filter(ImageFilter.GaussianBlur(spread // 2 + 5))
            canvas.alpha_composite(sh)

    def draw_card(self, canvas, cx0, cy0, cw, ch):
        # Glass body
        c = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ImageDraw.Draw(c).rounded_rectangle(
            [cx0, cy0, cx0 + cw, cy0 + ch], radius=28, fill=(252, 248, 242, 198)
        )
        canvas.alpha_composite(c)
        # Inner softness
        i = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ImageDraw.Draw(i).rounded_rectangle(
            [cx0 + 3, cy0 + 3, cx0 + cw - 3, cy0 + ch - 3],
            radius=25, fill=(255, 255, 252, 18)
        )
        canvas.alpha_composite(i)
        # 1px white border 15%
        b = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ImageDraw.Draw(b).rounded_rectangle(
            [cx0, cy0, cx0 + cw, cy0 + ch],
            radius=28, outline=(255, 255, 255, 38), width=1
        )
        canvas.alpha_composite(b)
        # Top reflection highlight
        for ri in range(20):
            t  = ri / 20
            a  = int(105 * (1 - t) ** 2.2)
            rl = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            ImageDraw.Draw(rl).rounded_rectangle(
                [cx0 + ri, cy0 + ri, cx0 + cw - ri, cy0 + 38],
                radius=28 - ri, fill=(255, 255, 255, a)
            )
            canvas.alpha_composite(rl)

    def draw_sufi_art(self, canvas, ax, ay, art_size, raw_thumb):
        ART = art_size
        # Cover-crop real thumbnail
        art_img = self.cover_crop(raw_thumb, ART, ART)
        art_img = ImageEnhance.Contrast(art_img).enhance(0.88)
        art_img = ImageEnhance.Brightness(art_img).enhance(0.82)
        art_img = ImageEnhance.Color(art_img).enhance(0.7)

        # Overlay the sufi geometric pattern on top of the thumbnail
        overlay = Image.new("RGBA", (ART, ART), (0, 0, 0, 0))
        od      = ImageDraw.Draw(overlay)
        acx, acy = ART // 2, ART // 2

        # Warm semi-transparent tint layer
        od.rectangle([0, 0, ART, ART], fill=(160, 100, 50, 80))

        # Concentric rings
        for ri, rv in [(110, 40), (82, 60), (54, 88), (30, 120)]:
            od.ellipse([acx - ri, acy - ri, acx + ri, acy + ri],
                       outline=(255, 220, 150, rv), width=1)
        # 8-point star
        for angle_off in [0, 45]:
            pts = []
            for a in range(8):
                ang = math.radians(a * 45 + angle_off)
                r2  = 88 if a % 2 == 0 else 58
                pts.append((acx + math.cos(ang) * r2, acy + math.sin(ang) * r2))
            od.polygon(pts, outline=(255, 215, 140, 60))
        # Radial spokes
        for deg in range(0, 360, 22):
            rad = math.radians(deg)
            od.line([
                (acx + math.cos(rad) * 30, acy + math.sin(rad) * 30),
                (acx + math.cos(rad) * 105, acy + math.sin(rad) * 105)
            ], fill=(255, 220, 150, 38), width=1)
        # Center glow
        for gi in range(10, 0, -1):
            od.ellipse([acx - gi * 4, acy - gi * 4, acx + gi * 4, acy + gi * 4],
                       fill=(255, 235, 175, 28 - gi * 2))
        od.ellipse([acx - 8, acy - 8, acx + 8, acy + 8], fill=(255, 240, 200, 160))

        # Merge thumbnail + overlay
        base = art_img.convert("RGBA")
        base.alpha_composite(overlay)

        self.paste_rounded(canvas, base, (ax, ay), radius=20)

        # 1px white border on artwork
        ab = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ImageDraw.Draw(ab).rounded_rectangle(
            [ax, ay, ax + ART, ay + ART],
            radius=20, outline=(255, 255, 255, 75), width=1
        )
        canvas.alpha_composite(ab)

    def draw_eq_bars(self, canvas, eq_cx, eq_base):
        half_h  = [16, 28, 46, 24, 42, 56, 32, 50, 20, 38, 60, 26, 44, 36, 16, 52, 28, 12, 40, 48]
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
                rc = int(180 + t * 55)
                gc = int(88  + t * 102)
                bc = int(38  + t * 102)
                ac = int(225 - t * 90)
                eqd.rectangle(
                    [bx, eq_base - bh + row, bx + bw, eq_base - bh + row + 1],
                    fill=(rc, gc, bc, ac)
                )
            eqd.ellipse(
                [bx - 1, eq_base - bh - 3, bx + bw + 1, eq_base - bh + bw - 3],
                fill=(215, 125, 55, 180)
            )

        glow = eq_l.filter(ImageFilter.GaussianBlur(3.5))
        canvas.alpha_composite(glow)
        canvas.alpha_composite(eq_l)

    def draw_progress(self, canvas, bx0, by0, bwid, duration):
        pb  = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        pbd = ImageDraw.Draw(pb)
        pbd.rounded_rectangle(
            [bx0, by0, bx0 + bwid, by0 + 3],
            radius=2, fill=(200, 175, 148, 120)
        )
        dx, my = bx0, by0 + 1
        for gr, a in [(22, 18), (15, 42), (9, 100), (6, 185)]:
            pbd.ellipse([dx - gr, my - gr, dx + gr, my + gr], fill=(199, 107, 58, a))
        pbd.ellipse([dx - 5, my - 5, dx + 5, my + 5], fill=(252, 248, 242, 255))
        pbd.ellipse([dx - 2, my - 2, dx + 2, my + 2], fill=(199, 107, 58, 255))
        canvas.alpha_composite(pb)

        draw = ImageDraw.Draw(canvas)
        draw.text((bx0, by0 + 10), "0:00",
                  font=self.f_small, fill=(148, 118, 88, 185))
        dw, _ = self.ts(duration, self.f_small)
        draw.text((bx0 + bwid - dw, by0 + 10), duration,
                  font=self.f_small, fill=(148, 118, 88, 185))

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
            random.seed(42)

            # ── Background: #F4EDE4 → #E9D8C7 ────────────────────────────
            canvas = Image.new("RGBA", (W, H), (244, 237, 228, 255))

            grad = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            gd   = ImageDraw.Draw(grad)
            for y in range(H):
                t = y / H
                gd.line([(0, y), (W, y)], fill=(
                    int(244 - t * 11),
                    int(237 - t * 21),
                    int(228 - t * 27), 255
                ))
            canvas.alpha_composite(grad)

            # Horizontal warmth
            warm = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            wd   = ImageDraw.Draw(warm)
            for x in range(W):
                wd.line([(x, 0), (x, H)], fill=(210, 150, 90, int(12 * x / W)))
            canvas.alpha_composite(warm)

            # Grain 2–3%
            noise = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            nd    = noise.load()
            for y in range(H):
                for x in range(W):
                    v = random.randint(0, 255)
                    nd[x, y] = (v, int(v * 0.72), int(v * 0.44), random.randint(0, 6))
            canvas.alpha_composite(noise)

            # Corner vignette
            vig = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            for i in range(90):
                t = (90 - i) / 90
                a = int(28 * t ** 2.5)
                ImageDraw.Draw(vig).rectangle(
                    [i, i, W - i, H - i], outline=(155, 120, 80, a), width=1
                )
            canvas.alpha_composite(vig)

            # Studio blooms
            self.bloom(canvas, -80,  -60, 620, (255, 225, 170), alpha=68)
            self.bloom(canvas,  920,  400, 500, (255, 210, 155), alpha=30)
            self.bloom(canvas,  380,  700, 360, (220, 185, 130), alpha=22)
            self.bloom(canvas,  860,  320, 440, (255, 218, 180), alpha=40)

            # Dust particles
            dust = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            dd   = ImageDraw.Draw(dust)
            for _ in range(130):
                px = random.randint(0, W)
                py = random.randint(0, H)
                pr = random.uniform(0.4, 2.2)
                pa = random.randint(6, 30)
                v  = random.randint(210, 255)
                dd.ellipse(
                    [px - pr, py - pr, px + pr, py + pr],
                    fill=(v, int(v * 0.82), int(v * 0.56), pa)
                )
            dust = dust.filter(ImageFilter.GaussianBlur(1.0))
            canvas.alpha_composite(dust)

            # ── Left floating card ────────────────────────────────────────
            CW, CH = 316, 430
            cx0    = 60
            cy0    = (H - CH) // 2 - 10
            CCX    = cx0 + CW // 2

            self.draw_card_shadow(canvas, cx0, cy0, CW, CH)
            self.draw_card(canvas, cx0, cy0, CW, CH)

            # Artwork with sufi overlay
            ART = 248
            ax  = cx0 + (CW - ART) // 2
            ay  = cy0 + 26
            self.draw_sufi_art(canvas, ax, ay, ART, raw)

            # Card micro text
            draw = ImageDraw.Draw(canvas)

            song_lbl = song.title[:22] + ("…" if len(song.title) > 22 else "")
            slw, slh = self.ts(song_lbl, self.f_micro)
            draw.text((CCX - slw // 2, ay + ART + 14),
                      song_lbl, font=self.f_micro, fill=(70, 48, 28, 225))

            art_lbl = song.channel_name[:28]
            alw, alh = self.ts(art_lbl, self.f_micro)
            draw.text((CCX - alw // 2, ay + ART + 14 + slh + 5),
                      art_lbl, font=self.f_micro, fill=(130, 98, 65, 170))

            # Verified badge
            vbt = "✓  Verified Artist"
            vbw, vbh = self.ts(vbt, self.f_micro)
            vby = ay + ART + 14 + slh + alh + 18
            vbs = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(vbs).rounded_rectangle(
                [CCX - vbw // 2 - 12, vby + 2, CCX + vbw // 2 + 12, vby + vbh + 10],
                radius=11, fill=(160, 120, 70, 40)
            )
            vbs = vbs.filter(ImageFilter.GaussianBlur(3))
            canvas.alpha_composite(vbs)
            vbl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(vbl).rounded_rectangle(
                [CCX - vbw // 2 - 12, vby, CCX + vbw // 2 + 12, vby + vbh + 8],
                radius=11, fill=(225, 195, 148, 180)
            )
            canvas.alpha_composite(vbl)
            draw = ImageDraw.Draw(canvas)
            draw.text((CCX - vbw // 2, vby + 4), vbt,
                      font=self.f_micro, fill=(75, 48, 22, 235))

            # ── Right content ─────────────────────────────────────────────
            RX = cx0 + CW + 72
            RY = 120
            RW = W - RX - 55

            # NOW PLAYING badge
            bt       = "NOW PLAYING"
            bw2, bh2 = self.ts(bt, self.f_badge)
            pad      = 14
            bsh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(bsh).rounded_rectangle(
                [RX, RY + 3, RX + bw2 + pad * 2, RY + bh2 + 13],
                radius=22, fill=(160, 80, 30, 50)
            )
            bsh = bsh.filter(ImageFilter.GaussianBlur(5))
            canvas.alpha_composite(bsh)
            bl2 = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(bl2).rounded_rectangle(
                [RX, RY, RX + bw2 + pad * 2, RY + bh2 + 10],
                radius=22, fill=(199, 107, 58, 235)
            )
            canvas.alpha_composite(bl2)
            draw = ImageDraw.Draw(canvas)
            draw.text((RX + pad, RY + 5), bt,
                      font=self.f_badge, fill=(255, 255, 255, 255))

            # Title lines
            ty    = RY + bh2 + 30
            lines = self.wrap(song.title, self.f_h1, RW)
            for line in lines[:2]:
                lw, lh = self.ts(line, self.f_h1)
                draw.text((RX + 2, ty + 2), line, font=self.f_h1, fill=(200, 158, 105, 42))
                draw.text((RX,     ty),     line, font=self.f_h1, fill=(58,   44,  35, 255))
                ty += lh + 5

            # 2px accent divider
            acc_w   = int(RW * 0.42)
            acc_y   = ty + 14
            acc_l   = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            acc_px  = acc_l.load()
            for x in range(RX, RX + acc_w):
                t = (x - RX) / acc_w
                a = int(255 * (1 - t ** 1.6))
                for dy in range(2):
                    if acc_y + dy < H:
                        acc_px[x, acc_y + dy] = (199, 107, 58, a)
            ImageDraw.Draw(acc_l).ellipse(
                [RX - 1, acc_y - 1, RX + 3, acc_y + 3], fill=(199, 107, 58, 230)
            )
            canvas.alpha_composite(acc_l)
            draw = ImageDraw.Draw(canvas)

            # Artist subtitle
            draw.text((RX, acc_y + 18), song.channel_name[:34],
                      font=self.f_sub, fill=(110, 92, 80, 210))

            # Metadata pills
            meta_y  = acc_y + 74
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

                for blur, sa, se_f in [(8, 14, 6), (4, 22, 3)]:
                    ps = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                    se = se_f
                    ImageDraw.Draw(ps).rounded_rectangle(
                        [meta_sx - se, meta_y + se, meta_sx + pw + se, meta_y + ph + se],
                        radius=16 + se, fill=(160, 130, 90, sa)
                    )
                    ps = ps.filter(ImageFilter.GaussianBlur(blur))
                    canvas.alpha_composite(ps)

                pill = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                ImageDraw.Draw(pill).rounded_rectangle(
                    [meta_sx, meta_y, meta_sx + pw, meta_y + ph],
                    radius=16, fill=(250, 244, 235, 192)
                )
                canvas.alpha_composite(pill)
                for ii in range(4):
                    il = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                    ImageDraw.Draw(il).rounded_rectangle(
                        [meta_sx + ii, meta_y + ii,
                         meta_sx + pw - ii, meta_y + 10],
                        radius=16 - ii, fill=(160, 130, 90, 10 - ii * 2)
                    )
                    canvas.alpha_composite(il)
                pb3 = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                ImageDraw.Draw(pb3).rounded_rectangle(
                    [meta_sx, meta_y, meta_sx + pw, meta_y + ph],
                    radius=16, outline=(210, 178, 135, 95), width=1
                )
                canvas.alpha_composite(pb3)
                draw = ImageDraw.Draw(canvas)
                draw.text((meta_sx + 17, meta_y + 6),      val,   font=self.f_stat,  fill=(68,  44,  22, 240))
                draw.text((meta_sx + 17, meta_y + vh + 11), label, font=self.f_micro, fill=(140, 108, 72, 180))
                meta_sx += pw + 14

            # ── EQ bars ───────────────────────────────────────────────────
            self.draw_eq_bars(canvas, RX + RW // 2 - 10, H - 102)

            # ── Progress bar ──────────────────────────────────────────────
            self.draw_progress(canvas, 60, H - 55, W - 120, song.duration)

            # ── Top sine accent line ──────────────────────────────────────
            topa = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            tad  = ImageDraw.Draw(topa)
            for x in range(W):
                t = x / W
                a = int(170 * math.sin(t * math.pi))
                tad.point((x, 0), fill=(199, 107, 58, a))
                tad.point((x, 1), fill=(199, 107, 58, a // 2))
            canvas.alpha_composite(topa)

            # ── Cinematic DoF edge vignette ───────────────────────────────
            dof = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            for i in range(70):
                t = (70 - i) / 70
                a = int(20 * t ** 3)
                ImageDraw.Draw(dof).rectangle(
                    [i, i, W - i, H - i], outline=(185, 148, 100, a), width=1
                )
            canvas.alpha_composite(dof)

            canvas.save(output, "PNG", optimize=True)
            os.remove(temp)
            return output

        except Exception as e:
            print("Thumbnail Error:", e)
            return config.DEFAULT_THUMB
