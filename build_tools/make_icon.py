# -*- coding: utf-8 -*-
"""生成软件图标（assets/icon.ico 与预览图）。

设计：圆角方形（超椭圆观感）蓝→青纵向渐变底，主体为「A ⇄ 文」双向翻译符号：
  * 左侧白色 "A"（英文）
  * 右侧青白色 "文"（中文）
  * 中间细的上下双向箭头，表达"互译"
16px 下会自动切换为简化构图（只留 A/文 并放大），保证小尺寸也清晰可辨。

用法：python build_tools/make_icon.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
SS = 8                      # 超采样倍数
FONT_LATIN = r"C:\Windows\Fonts\segoeuib.ttf"     # Segoe UI Bold
FONT_CJK = r"C:\Windows\Fonts\msyhbd.ttc"         # 微软雅黑 Bold

TOP = (43, 108, 240)        # #2B6CF0 蓝
BOTTOM = (16, 185, 170)     # #10B9AA 青
GLYPH_A = (255, 255, 255)
GLYPH_WEN = (226, 247, 255)


def rounded_mask(size: int, radius_ratio: float = 0.235) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    r = int(size * radius_ratio)
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=r, fill=255)
    return mask


def vertical_gradient(size: int) -> Image.Image:
    grad = Image.new("RGB", (1, size))
    for y in range(size):
        t = y / max(size - 1, 1)
        grad.putpixel((0, y), tuple(int(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(3)))
    return grad.resize((size, size), Image.BILINEAR)


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def draw_center_text(base: Image.Image, text: str, fnt, box, fill, shadow=True):
    """在 box=(x0,y0,x1,y1) 内居中绘制文字（按高宽 1:1 约束，避免字太宽）。"""
    tmp = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(tmp)
    x0, y0, x1, y1 = box
    bbox = d.textbbox((0, 0), text, font=fnt)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    if tw > 0 and th > 0:
        box_h = y1 - y0
        if tw > box_h:          # 字比可用高度还宽 -> 缩小字号，保持方形比例
            scale = box_h / tw
            try:
                fnt = ImageFont.truetype(fnt.path, max(8, int(fnt.size * scale)))
            except Exception:
                pass
            bbox = d.textbbox((0, 0), text, font=fnt)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    cx = (x0 + x1) / 2 - tw / 2 - bbox[0]
    cy = (y0 + y1) / 2 - th / 2 - bbox[1]

    if shadow:
        sh = Image.new("RGBA", base.size, (0, 0, 0, 0))
        ds = ImageDraw.Draw(sh)
        off = max(1, int(base.size[0] * 0.012))
        ds.text((cx + off, cy + off * 1.4), text, font=fnt, fill=(8, 34, 92, 90))
        sh = sh.filter(ImageFilter.GaussianBlur(max(1, base.size[0] * 0.006)))
        base.alpha_composite(sh)

    ImageDraw.Draw(base).text((cx, cy), text, font=fnt, fill=fill)


def draw_arrow(base: Image.Image, box, color=(255, 255, 255, 235)):
    """在 box 内画上下双向箭头（表示双向互译）。带深色细描边，缩小后也清晰。"""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    cx = (x0 + x1) / 2
    shaft = max(2, int(w * 0.34))          # 杆宽
    head_w = w * 1.25                      # 箭头宽
    head_h = h * 0.26                      # 箭头高
    outline = (12, 48, 120, 120)
    stroke = max(1, int(w * 0.10))

    def shape(inset: float, fill):
        d = ImageDraw.Draw(base)
        # 竖杆
        d.rounded_rectangle(
            (cx - shaft / 2 - inset, y0 + head_h * 0.55 - inset,
             cx + shaft / 2 + inset, y1 - head_h * 0.55 + inset),
            radius=shaft / 2, fill=fill,
        )
        # 上下箭头
        d.polygon([(cx, y0 - inset),
                   (cx - head_w / 2 - inset, y0 + head_h + inset),
                   (cx + head_w / 2 + inset, y0 + head_h + inset)], fill=fill)
        d.polygon([(cx, y1 + inset),
                   (cx - head_w / 2 - inset, y1 - head_h - inset),
                   (cx + head_w / 2 + inset, y1 - head_h - inset)], fill=fill)

    shape(stroke, outline)   # 描边
    shape(0, color)          # 主体


def render(size: int) -> Image.Image:
    """渲染某个尺寸的图标（size 为最终尺寸）。"""
    n = size * SS
    base = Image.new("RGBA", (n, n), (0, 0, 0, 0))

    # 1) 渐变底 + 圆角
    body = vertical_gradient(n).convert("RGBA")
    body.putalpha(rounded_mask(n))

    # 2) 顶部柔光，增加层次
    gloss = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    gd = ImageDraw.Draw(gloss)
    gd.ellipse((-n * 0.35, -n * 0.95, n * 1.35, n * 0.55), fill=(255, 255, 255, 46))
    gloss.putalpha(Image.composite(gloss.getchannel("A"), Image.new("L", (n, n), 0), rounded_mask(n)))
    body.alpha_composite(gloss)

    base.alpha_composite(body)

    # 3) 主体符号
    if size >= 128:
        # 大尺寸：完整构图 A | ⇅ | 文
        f_a = font(FONT_LATIN, int(n * 0.44))
        f_w = font(FONT_CJK, int(n * 0.42))
        draw_center_text(base, "A", f_a, (n * 0.105, n * 0.26, n * 0.425, n * 0.74), GLYPH_A)
        draw_arrow(base, (n * 0.435, n * 0.29, n * 0.565, n * 0.71))
        draw_center_text(base, "文", f_w, (n * 0.575, n * 0.26, n * 0.895, n * 0.74), GLYPH_WEN)
    elif size >= 48:
        # 中等尺寸：箭头短一些
        f_a = font(FONT_LATIN, int(n * 0.50))
        f_w = font(FONT_CJK, int(n * 0.48))
        draw_center_text(base, "A", f_a, (n * 0.075, n * 0.25, n * 0.43, n * 0.75), GLYPH_A, shadow=False)
        draw_arrow(base, (n * 0.45, n * 0.36, n * 0.55, n * 0.64))
        draw_center_text(base, "文", f_w, (n * 0.57, n * 0.25, n * 0.925, n * 0.75), GLYPH_WEN, shadow=False)
    else:
        # 小尺寸（16/20/24/32/40）：只留 A 与 文，中间加一道竖向分隔缝，保证可辨识
        f_a = font(FONT_LATIN, int(n * 0.56))
        f_w = font(FONT_CJK, int(n * 0.54))
        draw_center_text(base, "A", f_a, (n * 0.035, n * 0.20, n * 0.485, n * 0.80), GLYPH_A, shadow=False)
        draw_center_text(base, "文", f_w, (n * 0.515, n * 0.20, n * 0.965, n * 0.80), GLYPH_WEN, shadow=False)
        seam = Image.new("RGBA", (n, n), (0, 0, 0, 0))
        ImageDraw.Draw(seam).rectangle(
            (n * 0.4925, n * 0.235, n * 0.5075, n * 0.765), fill=(255, 255, 255, 120)
        )
        seam.putalpha(Image.composite(seam.getchannel("A"), Image.new("L", (n, n), 0), rounded_mask(n)))
        base.alpha_composite(seam)

    # 4) 内侧细描边，让图标在浅色/深色背景上都清晰
    edge = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    ed = ImageDraw.Draw(edge)
    ed.rounded_rectangle(
        (1, 1, n - 2, n - 2),
        radius=int(n * 0.235),
        outline=(255, 255, 255, 70),
        width=max(1, int(n * 0.012)),
    )
    base.alpha_composite(edge)

    # 5) 降采样
    return base.resize((size, size), Image.LANCZOS)


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    sizes = [256, 128, 64, 48, 40, 32, 24, 20, 16]
    images = {s: render(s) for s in sizes}

    # 主图标 PNG
    images[256].save(ASSETS / "icon.png")
    images[128].save(ASSETS / "icon-128.png")
    images[64].save(ASSETS / "icon-64.png")
    images[48].save(ASSETS / "icon-48.png")
    images[32].save(ASSETS / "icon-32.png")
    images[16].save(ASSETS / "icon-16.png")

    # 多尺寸 ICO（Windows 会挑合适尺寸显示）
    ico = ASSETS / "icon.ico"
    images[256].save(ico, format="ICO", sizes=[(s, s) for s in sizes])
    print(f"已生成 {ico}  ({ico.stat().st_size} 字节)")

    # 预览图：左新右旧 + 小尺寸放大，便于人工确认
    prev_w, prev_h = 760, 360
    preview = Image.new("RGB", (prev_w, prev_h), (245, 247, 250))
    d = ImageDraw.Draw(preview)
    try:
        pf = ImageFont.truetype(FONT_CJK, 18)
        pf_s = ImageFont.truetype(FONT_CJK, 14)
    except Exception:
        pf = pf_s = None
    d.text((24, 16), "新图标（多尺寸）", fill=(30, 41, 59), font=pf)
    x = 24
    for s in (256, 128, 64, 48):
        preview.paste(images[s], (x, 48), images[s])
        d.text((x + 2, 56 + s), f"{s}px", fill=(90, 100, 120), font=pf_s)
        x += s + 18
    d.text((24, 250), "小尺寸（实际像素放大 4 倍，检查清晰度）：16 / 24 / 32 / 40", fill=(30, 41, 59), font=pf)
    x = 24
    for s in (16, 24, 32, 40):
        big = images[s].resize((s * 4, s * 4), Image.NEAREST)
        preview.paste(big, (x, 284), big)
        x += s * 4 + 16
    old = ASSETS / "icon-old.png"
    if old.is_file():
        o = Image.open(old).convert("RGBA").resize((64, 64), Image.LANCZOS)
        preview.paste(o, (620, 48), o)
        d.text((620, 120), "旧图标", fill=(90, 100, 120), font=pf_s)
    preview.save(ASSETS / "icon-preview.png")
    print(f"已生成 {ASSETS / 'icon-preview.png'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
