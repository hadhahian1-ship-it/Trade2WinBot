"""
prize_image.py — Premium English-only prize certificate for Trade 2 Win bot.

Layout: 960 × 540 px  (16:9 dark-gradient gift card)
  • DejaVu Sans Bold/Regular for all UI/label text (English only)
  • Amiri Bold for the winner-name slot (supports Arabic Telegram names)
  • Circular admin logo (cached from Telegram) at top-center
  • Consistent layout whether logo file is present or not
"""

import io
import math
import os
import datetime
import logging

from PIL import Image, ImageDraw, ImageFilter, ImageFont

logger = logging.getLogger(__name__)

W, H = 960, 540

# ── Font paths ────────────────────────────────────────────────────────────────
_DEJAVU_BOLD    = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_DEJAVU_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_FONT_DIR       = os.path.join(os.path.dirname(__file__), "fonts")
_AMIRI_BOLD     = os.path.join(_FONT_DIR, "Amiri-Bold.ttf")

# ── Cached admin logo ─────────────────────────────────────────────────────────
LOGO_PATH = os.path.join(os.path.dirname(__file__), "assets", "admin_logo.jpg")

# ── Logo geometry (reserved even when logo is absent, for stable layout) ──────
_LOGO_SIZE   = 64   # inner photo diameter
_LOGO_BORDER = 3    # accent ring thickness (px each side)
_LOGO_TOTAL  = _LOGO_SIZE + _LOGO_BORDER * 2   # 70 px rendered diameter
_LOGO_Y      = 122  # top of the logo on the canvas
_LOGO_CY     = _LOGO_Y + _LOGO_TOTAL // 2      # vertical centre ≈ 157

# y-offset applied to everything below the logo area
_SHIFT = 82

# ── Prize configuration (100 % English) ──────────────────────────────────────
PRIZE_CONFIG = {
    "try_again": {
        "bg_top":    (10, 22, 55),
        "bg_bottom": (18, 45, 95),
        "accent":    (90, 155, 255),
        "glow":      (55, 105, 200),
        "star":      (65, 115, 205),
        "prize":     "EXTRA FREE SPIN",
        "sub":       "Lucky Wheel Retry  ·  No Cooldown Applied",
        "tier":      "BONUS",
    },
    "vip": {
        "bg_top":    (30, 12, 65),
        "bg_bottom": (58, 20, 100),
        "accent":    (212, 175, 55),
        "glow":      (175, 138, 25),
        "star":      (190, 150, 30),
        "prize":     "VIP MEMBERSHIP ACCESS",
        "sub":       "Exclusive Channel  ·  Premium Trading Signals",
        "tier":      "VIP",
    },
    "money_5": {
        "bg_top":    (8, 40, 22),
        "bg_bottom": (12, 68, 35),
        "accent":    (55, 205, 85),
        "glow":      (28, 155, 50),
        "star":      (32, 165, 55),
        "prize":     "CASH PRIZE: $5",
        "sub":       "Contact Support to Claim Your Reward",
        "tier":      "WINNER",
    },
    "money_10": {
        "bg_top":    (65, 12, 12),
        "bg_bottom": (110, 20, 20),
        "accent":    (255, 200, 45),
        "glow":      (205, 155, 15),
        "star":      (220, 165, 20),
        "prize":     "CASH PRIZE: $10",
        "sub":       "Grand Prize  ·  Contact Support Immediately",
        "tier":      "GRAND",
    },
}


# ── Font helpers ──────────────────────────────────────────────────────────────

def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _winner_font(size: int) -> ImageFont.FreeTypeFont:
    """Prefer Amiri (supports Arabic), fall back to DejaVu."""
    try:
        return ImageFont.truetype(_AMIRI_BOLD, size)
    except Exception:
        return _font(_DEJAVU_BOLD, size)


def _prepare_name(text: str) -> str:
    """Reshape + bidi-reorder if text contains Arabic characters."""
    import unicodedata
    has_arabic = any(unicodedata.bidirectional(c) in ("R", "AL", "AN") for c in text)
    if not has_arabic:
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        return text


# ── Drawing helpers ───────────────────────────────────────────────────────────

def _cx(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    bb = draw.textbbox((0, 0), text, font=font)
    return (W - (bb[2] - bb[0])) // 2


def _centered(
    draw: ImageDraw.ImageDraw,
    text: str,
    y: int,
    font: ImageFont.FreeTypeFont,
    fill=(255, 255, 255),
) -> None:
    draw.text((_cx(draw, text, font), y), text, font=font, fill=fill)


def _gradient(draw: ImageDraw.ImageDraw, top: tuple, bottom: tuple) -> None:
    for row in range(H):
        t = row / H
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        draw.line([(0, row), (W, row)], fill=(r, g, b))


def _star5(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int, color: tuple) -> None:
    pts = []
    for i in range(10):
        ang = math.pi / 5 * i - math.pi / 2
        rad = r if i % 2 == 0 else r * 0.42
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    draw.polygon(pts, fill=color)


def _glow_text(
    img: Image.Image,
    text: str,
    xy: tuple,
    font: ImageFont.FreeTypeFont,
    fill: tuple,
    glow_color: tuple,
    radius: int = 9,
) -> None:
    """Render text with a soft glow halo."""
    glow_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(glow_layer).text(xy, text, font=font, fill=(*glow_color, 190))
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius))
    base_rgba  = img.convert("RGBA")
    merged     = Image.alpha_composite(base_rgba, glow_layer)
    ImageDraw.Draw(merged).text(xy, text, font=font, fill=(*fill, 255))
    img.paste(merged.convert("RGB"))


# ── Logo helpers ──────────────────────────────────────────────────────────────

def _make_circle_logo(
    path: str,
    inner_size: int,
    border_color: tuple,
    border_px: int,
) -> Image.Image:
    """
    Load image from path → crop square → resize → circular mask → accent ring.
    Returns an RGBA image of size (inner_size + border_px*2) × same.
    """
    raw = Image.open(path).convert("RGBA")
    w, h   = raw.size
    side   = min(w, h)
    left   = (w - side) // 2
    top    = (h - side) // 2
    raw    = raw.crop((left, top, left + side, top + side))
    raw    = raw.resize((inner_size, inner_size), Image.LANCZOS)

    # Circular mask
    mask   = Image.new("L", (inner_size, inner_size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, inner_size - 1, inner_size - 1], fill=255)
    circle = Image.new("RGBA", (inner_size, inner_size), (0, 0, 0, 0))
    circle.paste(raw, mask=mask)

    # Accent ring
    total  = inner_size + border_px * 2
    ring   = Image.new("RGBA", (total, total), (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse([0, 0, total - 1, total - 1], fill=(*border_color, 255))
    ring.paste(circle, (border_px, border_px), mask=circle)
    return ring


def _fallback_logo(size: int, accent: tuple, bg: tuple) -> Image.Image:
    """
    When no logo file is found, draw a circle with 'T2W' initials instead.
    Returns an RGBA image of size × size.
    """
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([0, 0, size - 1, size - 1], fill=(*bg, 240), outline=(*accent, 255), width=3)
    try:
        fnt = ImageFont.truetype(_DEJAVU_BOLD, size // 4)
    except Exception:
        fnt = ImageFont.load_default()
    for label in ["T2W"]:
        bb = draw.textbbox((0, 0), label, font=fnt)
        lw, lh = bb[2] - bb[0], bb[3] - bb[1]
        draw.text(((size - lw) // 2, (size - lh) // 2), label, font=fnt, fill=(*accent, 255))
    return img


# ── Public API ────────────────────────────────────────────────────────────────

def generate_prize_image(
    prize_key: str,
    winner_name: str,
    bot_username: str = "Trade2WinBot",
    verify_code: str = "",
) -> bytes:
    """
    Generate a 960×540 English-only prize certificate PNG.
    Includes the admin's circular profile photo as a top-center logo.
    If verify_code is provided it is stamped bottom-left to make the
    certificate look official and allow admin validation.
    Returns raw PNG bytes.
    """
    cfg = PRIZE_CONFIG.get(prize_key, PRIZE_CONFIG["try_again"])
    acc  = cfg["accent"]
    glow = cfg["glow"]

    # ── Canvas + gradient ──
    img  = Image.new("RGB", (W, H), cfg["bg_top"])
    draw = ImageDraw.Draw(img)
    _gradient(draw, cfg["bg_top"], cfg["bg_bottom"])

    # ── Corner stars ──
    for sx, sy in [(38, 38), (W - 38, 38), (38, H - 38), (W - 38, H - 38)]:
        _star5(draw, sx, sy, 13, cfg["star"])

    # ── Borders ──
    draw.rectangle([10, 10, W - 10, H - 10], outline=acc, width=5)
    draw.rectangle([20, 20, W - 20, H - 20], outline=acc, width=1)

    # ── Corner accent lines (gift-card feel) ──
    cl = 26
    for ax, ay, bx, by, cx2, cy2 in [
        (10, 10 + cl, 10, 10, 10 + cl, 10),
        (W - 10 - cl, 10, W - 10, 10, W - 10, 10 + cl),
        (10, H - 10 - cl, 10, H - 10, 10 + cl, H - 10),
        (W - 10 - cl, H - 10, W - 10, H - 10, W - 10, H - 10 - cl),
    ]:
        draw.line([(ax, ay), (bx, by), (cx2, cy2)], fill=acc, width=3)

    # ── Fonts ──
    fnt_brand    = _font(_DEJAVU_BOLD,    50)
    fnt_tagline  = _font(_DEJAVU_REGULAR, 16)
    fnt_issued   = _font(_DEJAVU_REGULAR, 13)
    fnt_congrats = _font(_DEJAVU_BOLD,    25)
    fnt_tier     = _font(_DEJAVU_BOLD,    12)
    fnt_prize    = _font(_DEJAVU_BOLD,    50)
    fnt_sub      = _font(_DEJAVU_REGULAR, 15)
    fnt_label    = _font(_DEJAVU_REGULAR, 13)
    fnt_name     = _winner_font(34)
    fnt_value    = _font(_DEJAVU_BOLD,    16)
    fnt_date     = _font(_DEJAVU_REGULAR, 15)
    fnt_footer   = _font(_DEJAVU_REGULAR, 13)
    fnt_seal     = _font(_DEJAVU_BOLD,    11)

    # ════════════════════════════════════════════
    #  ZONE 1 — Brand header  (y 24 – 110)
    # ════════════════════════════════════════════
    _centered(draw, "TRADE 2 WIN", 24, fnt_brand, acc)
    _centered(
        draw,
        "Your Trading Success Partner  ·  Powered by Monaxa",
        82, fnt_tagline, (155, 155, 155),
    )
    draw.line([(55, 108), (W - 55, 108)], fill=acc, width=2)

    # ════════════════════════════════════════════
    #  ZONE 2 — Circular logo  (y 116 – 210)
    # ════════════════════════════════════════════
    try:
        if os.path.exists(LOGO_PATH):
            logo = _make_circle_logo(LOGO_PATH, _LOGO_SIZE, acc, _LOGO_BORDER)
        else:
            logo = _fallback_logo(_LOGO_TOTAL, acc, cfg["bg_bottom"])
    except Exception as e:
        logger.warning(f"Logo render failed: {e}")
        logo = _fallback_logo(_LOGO_TOTAL, acc, cfg["bg_bottom"])

    lw, lh = logo.size
    lx = (W - lw) // 2
    ly = _LOGO_Y
    img_rgba = img.convert("RGBA")
    img_rgba.paste(logo, (lx, ly), mask=logo)
    img = img_rgba.convert("RGB")
    draw = ImageDraw.Draw(img)

    # "Issued by: Trade 2 Win" below the logo
    _centered(draw, "Issued by: Trade 2 Win", ly + lh + 5, fnt_issued, (160, 160, 160))

    # ════════════════════════════════════════════
    #  ZONE 3 — Congratulations + Prize  (shifted down by _SHIFT)
    # ════════════════════════════════════════════
    S = _SHIFT   # shorthand

    _centered(draw, "CONGRATULATIONS!", 126 + S, fnt_congrats, (220, 220, 220))

    # Tier badge (filled pill)
    tier_text = f"  {cfg['tier']}  "
    tb   = draw.textbbox((0, 0), tier_text, font=fnt_tier)
    tw   = tb[2] - tb[0] + 14
    th   = tb[3] - tb[1] + 8
    tx   = (W - tw) // 2
    ty   = 160 + S
    draw.rectangle([tx, ty, tx + tw, ty + th], fill=acc)
    draw.text((tx + 7, ty + 4), tier_text, font=fnt_tier, fill=cfg["bg_top"])

    # Prize name with glow
    prize_text = cfg["prize"]
    px = _cx(draw, prize_text, fnt_prize)
    _glow_text(img, prize_text, (px, 184 + S), fnt_prize, acc, glow, radius=9)
    draw = ImageDraw.Draw(img)

    # Sub-description
    _centered(draw, cfg["sub"], 246 + S, fnt_sub, (150, 150, 150))

    # ════════════════════════════════════════════
    #  ZONE 4 — Winner info  (y ~335 – 460)
    # ════════════════════════════════════════════
    draw.line([(95, 270 + S), (W - 95, 270 + S)], fill=acc, width=1)

    # Two-column layout
    sep = W // 2

    # Left: Winner Name
    draw.text((100, 282 + S), "WINNER NAME", font=fnt_label, fill=(135, 135, 135))
    name_display = _prepare_name(winner_name)
    draw.text((100, 298 + S), name_display, font=fnt_name, fill=(255, 255, 255))

    # Right: Date Awarded
    today = datetime.date.today().strftime("%B %d, %Y")
    draw.text((sep + 28, 282 + S), "DATE AWARDED", font=fnt_label, fill=(135, 135, 135))
    draw.text((sep + 28, 298 + S), today, font=fnt_date, fill=(210, 210, 210))

    # Second row
    draw.text((100, 346 + S), "PRIZE AWARDED", font=fnt_label, fill=(135, 135, 135))
    draw.text((100, 362 + S), cfg["prize"], font=fnt_value, fill=acc)

    draw.text((sep + 28, 346 + S), "ISSUED BY", font=fnt_label, fill=(135, 135, 135))
    draw.text((sep + 28, 362 + S), "Trade 2 Win  ·  Monaxa", font=fnt_value, fill=acc)

    # ════════════════════════════════════════════
    #  ZONE 5 — Official seal  (bottom-right)
    # ════════════════════════════════════════════
    scx, scy, sr = W - 84, H - 72, 46
    draw.ellipse([scx - sr, scy - sr, scx + sr, scy + sr], outline=acc, width=3)
    draw.ellipse([scx - sr + 5, scy - sr + 5, scx + sr - 5, scy + sr - 5], outline=acc, width=1)
    for i, ln in enumerate(["OFFICIAL", "AWARD", "VERIFIED"]):
        bb = draw.textbbox((0, 0), ln, font=fnt_seal)
        draw.text(
            (scx - (bb[2] - bb[0]) // 2, scy - 14 + i * 13),
            ln, font=fnt_seal, fill=acc,
        )

    # ════════════════════════════════════════════
    #  ZONE 5b — Verification Code  (bottom-left, mirrors the seal)
    # ════════════════════════════════════════════
    fnt_verify_lbl = _font(_DEJAVU_REGULAR, 11)
    fnt_verify_val = _font(_DEJAVU_BOLD,    14)
    code_display   = verify_code if verify_code else "T2W-OFFICIAL"
    draw.text((38, H - 92), "VERIFICATION CODE", font=fnt_verify_lbl, fill=(120, 120, 120))
    draw.text((38, H - 75), code_display,        font=fnt_verify_val, fill=acc)

    # ════════════════════════════════════════════
    #  ZONE 6 — Footer
    # ════════════════════════════════════════════
    draw.line([(55, H - 56), (W - 55, H - 56)], fill=acc, width=1)
    _centered(
        draw,
        f"@Trad_2win  ·  t.me/{bot_username}  ·  account.monaxa.com",
        H - 48, fnt_footer, (118, 118, 118),
    )
    _centered(
        draw,
        "Trade 2 Win © 2025  —  All Rights Reserved",
        H - 30, fnt_footer, (88, 88, 88),
    )

    # ── Render ──
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.read()
