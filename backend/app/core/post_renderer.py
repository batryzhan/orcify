"""Awesome Posts — Instagram-посттарының детерминистік рендері (Pillow).

Модель ештеңе салмайды: ол тек мәтіндерді қайтарады (``PostCopySchema``),
ал бұл модуль оларды ``backend/assets/background`` ішіндегі үлгі фондық фотосына салады.
Бірдей кіріс -> бірдей PNG (генеративті графикасыз және желісіз).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Final

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.schemas.smm import PostCopySchema, PostTemplate

WIDTH: Final = 1080
HEIGHT: Final = 1350  # 4:5 — Instagram таспасының негізгі форматы

RGB = tuple[int, int, int]
RGBA = tuple[int, int, int, int]


class PostRenderError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class TemplateSpec:
    id: PostTemplate
    title: str
    use_case: str
    background: str
    # Фонды кадрлаудың тік фокусы (0 — жоғарғы жағы, 1 — төменгі жағы).
    focus_y: float
    credit: str


TEMPLATES: Final[dict[PostTemplate, TemplateSpec]] = {
    PostTemplate.COSMOS: TemplateSpec(
        PostTemplate.COSMOS,
        "Cosmos",
        "Анонс, команданы таныстыру, үлкен жаңалық",
        "cosmos.jpg",
        0.85,
        "Unsplash",
    ),
    PostTemplate.NEON: TemplateSpec(
        PostTemplate.NEON,
        "Neon",
        "Өнімді іске қосу, акция, жеңілдік, промокод",
        "neon.jpg",
        0.5,
        "Unsplash",
    ),
    PostTemplate.SUMMIT: TemplateSpec(
        PostTemplate.SUMMIT,
        "Summit",
        "Дәйексөз, компания құндылықтары, іс-шара",
        "summit.jpg",
        0.6,
        "Unsplash",
    ),
}


# --- қаріптер және примитивтер ---------------------------------------------------


class _Fonts:
    def __init__(self, fonts_dir: Path) -> None:
        self._dir = fonts_dir

    def get(self, family: str, weight: str, size: int) -> ImageFont.FreeTypeFont:
        return _load_font(str(self._dir / f"{family}.ttf"), weight, size)


@lru_cache(maxsize=256)
def _load_font(path: str, weight: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        font = ImageFont.truetype(path, size)
    except OSError:
        raise PostRenderError("font_missing") from None
    try:
        font.set_variation_by_name(weight)
    except (OSError, ValueError):
        pass  # осьсіз статикалық қаріп — сол күйінде қолданамыз
    return font


def _text_width(font: ImageFont.FreeTypeFont, text: str, tracking: int = 0) -> int:
    left, _, right, _ = font.getbbox(text)
    return int(right - left) + tracking * max(len(text) - 1, 0)


def _fit_size(fonts: _Fonts, family: str, weight: str, text: str, max_width: int, start: int, minimum: int) -> int:
    size = start
    while size > minimum and _text_width(fonts.get(family, weight, size), text) > max_width:
        size -= 4
    return size


def _wrap(font: ImageFont.FreeTypeFont, text: str, max_width: int) -> list[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and _text_width(font, candidate) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _wrap_fit(
    fonts: _Fonts, family: str, weight: str, text: str, max_width: int, max_lines: int, start: int, minimum: int
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    size = start
    while True:
        font = fonts.get(family, weight, size)
        lines = _wrap(font, text, max_width)
        if (len(lines) <= max_lines and all(_text_width(font, ln) <= max_width for ln in lines)) or size <= minimum:
            if len(lines) > max_lines:
                lines = lines[: max_lines - 1] + [_ellipsize(font, " ".join(lines[max_lines - 1 :]), max_width)]
            return font, lines
        size -= 2


def _ellipsize(font: ImageFont.FreeTypeFont, text: str, max_width: int) -> str:
    if _text_width(font, text) <= max_width:
        return text
    while text and _text_width(font, text + "…") > max_width:
        text = text[:-1]
    return text.rstrip() + "…"


def _cover(image: Image.Image, focus_y: float) -> Image.Image:
    scale = max(WIDTH / image.width, HEIGHT / image.height)
    resized = image.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS)
    left = (resized.width - WIDTH) // 2
    top = round((resized.height - HEIGHT) * focus_y)
    return resized.crop((left, top, left + WIDTH, top + HEIGHT)).convert("RGBA")


def _vertical_gradient(size: tuple[int, int], top: RGBA, bottom: RGBA) -> Image.Image:
    width, height = size
    column = Image.new("RGBA", (1, height))
    for y in range(height):
        t = y / max(height - 1, 1)
        column.putpixel((0, y), tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)))  # type: ignore[arg-type]
    return column.resize((width, height))


def _horizontal_gradient(size: tuple[int, int], left: RGBA, right: RGBA) -> Image.Image:
    width, height = size
    row = Image.new("RGBA", (width, 1))
    for x in range(width):
        t = x / max(width - 1, 1)
        row.putpixel((x, 0), tuple(round(a + (b - a) * t) for a, b in zip(left, right)))  # type: ignore[arg-type]
    return row.resize((width, height))


def _shade(canvas: Image.Image, box: tuple[int, int, int, int], top: RGBA, bottom: RGBA) -> None:
    x0, y0, x1, y1 = box
    canvas.alpha_composite(_vertical_gradient((x1 - x0, y1 - y0), top, bottom), (x0, y0))


def _text_mask(text: str, font: ImageFont.FreeTypeFont, tracking: int = 0) -> Image.Image:
    left, top, right, bottom = font.getbbox(text)
    width = int(right - left) + tracking * max(len(text) - 1, 0) + 4
    height = int(bottom - top) + 4
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    if tracking == 0:
        draw.text((2 - left, 2 - top), text, font=font, fill=255)
    else:
        x = 2 - left
        for char in text:
            draw.text((x, 2 - top), char, font=font, fill=255)
            x += _text_width(font, char) + tracking
    return mask


def _place(mask: Image.Image, x: int, y: int, align: str) -> tuple[int, int]:
    if align == "center":
        return x - mask.width // 2, y
    if align == "right":
        return x - mask.width, y
    return x, y


def _draw_text(
    canvas: Image.Image,
    text: str,
    font: ImageFont.FreeTypeFont,
    xy: tuple[int, int],
    *,
    fill: RGBA | tuple[RGBA, RGBA] = (255, 255, 255, 255),
    align: str = "left",
    tracking: int = 0,
    glow: RGBA | None = None,
    glow_radius: int = 18,
    shadow: bool = False,
) -> tuple[int, int, int, int]:
    """Жолды (түс немесе тік градиент) қосымша жарқылмен салады. Bbox қайтарады."""
    mask = _text_mask(text, font, tracking)
    x, y = _place(mask, xy[0], xy[1], align)
    pad = glow_radius * 3
    if glow is not None or shadow:
        halo_mask = Image.new("L", (mask.width + pad * 2, mask.height + pad * 2), 0)
        halo_mask.paste(mask, (pad, pad))
        halo_mask = halo_mask.filter(ImageFilter.GaussianBlur(glow_radius if glow else 10))
        color = glow if glow is not None else (0, 0, 0, 150)
        layer = Image.new("RGBA", halo_mask.size, color[:3] + (0,))
        layer.putalpha(halo_mask.point(lambda v: round(v * color[3] / 255)))
        canvas.alpha_composite(layer, (x - pad, y - pad + (0 if glow else 6)))
    if isinstance(fill[0], tuple):
        top, bottom = fill  # type: ignore[misc]
        paint = _vertical_gradient(mask.size, top, bottom)  # type: ignore[arg-type]
    else:
        paint = Image.new("RGBA", mask.size, fill)  # type: ignore[arg-type]
    paint.putalpha(Image.composite(paint.getchannel("A"), Image.new("L", mask.size, 0), mask))
    canvas.alpha_composite(paint, (x, y))
    return x, y, x + mask.width, y + mask.height


def _pill(
    canvas: Image.Image, box: tuple[int, int, int, int], fill: RGBA, outline: RGBA | None = None, width: int = 3
) -> None:
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    radius = (box[3] - box[1]) // 2
    ImageDraw.Draw(layer).rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)
    canvas.alpha_composite(layer)


def _dots(canvas: Image.Image, cy: int, count: int = 10, active: int = 0) -> None:
    draw = ImageDraw.Draw(canvas)
    gap, r = 26, 6
    start = WIDTH // 2 - gap * (count - 1) // 2
    for i in range(count):
        cx = start + i * gap
        color = (255, 255, 255, 255) if i == active else (255, 255, 255, 110)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)


def _arrow(canvas: Image.Image, x: int, cy: int, color: RGBA) -> None:
    draw = ImageDraw.Draw(canvas)
    draw.line((x, cy, x + 30, cy), fill=color, width=5)
    draw.polygon([(x + 34, cy), (x + 20, cy - 12), (x + 20, cy + 12)], fill=color)


def _star_emblem(canvas: Image.Image, cx: int, cy: int, size: int) -> None:
    """Бейтарап эмблема: сақина және жұлдыз (нақты брендтің логотипі емес)."""
    import math

    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    r = size // 2
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(255, 255, 255, 235), width=7)
    points = []
    for i in range(10):
        angle = -math.pi / 2 + i * math.pi / 5
        radius = r * 0.62 if i % 2 == 0 else r * 0.26
        points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    draw.polygon(points, fill=(255, 255, 255, 245))
    glow = layer.filter(ImageFilter.GaussianBlur(14))
    canvas.alpha_composite(glow)
    canvas.alpha_composite(layer)


def _clean(text: str | None) -> str:
    return " ".join((text or "").split())


def _handle(text: str) -> str:
    value = _clean(text).replace(" ", "")
    if not value:
        return ""
    return value if value.startswith("@") else f"@{value}"


# --- рендерер -------------------------------------------------------------------


class PostRenderer:
    def __init__(self, assets_dir: Path, default_handle: str = "@orcify") -> None:
        self._backgrounds = assets_dir / "background"
        self._fonts = _Fonts(assets_dir / "fonts")
        self._default_handle = default_handle

    def background_path(self, template: PostTemplate) -> Path:
        return self._backgrounds / TEMPLATES[template].background

    def render(self, template: PostTemplate, content: PostCopySchema) -> bytes:
        spec = TEMPLATES[template]
        path = self.background_path(template)
        try:
            with Image.open(path) as source:
                canvas = _cover(source.convert("RGB"), spec.focus_y)
        except OSError:
            raise PostRenderError("background_missing") from None

        handle = _handle(content.handle) or self._default_handle
        if template is PostTemplate.COSMOS:
            self._cosmos(canvas, content, handle)
        elif template is PostTemplate.NEON:
            self._neon(canvas, content, handle)
        else:
            self._summit(canvas, content, handle)

        out = BytesIO()
        canvas.convert("RGB").save(out, format="PNG", compress_level=6)
        return out.getvalue()

    # Cosmos: эмблема, үлкен екі жолды градиентті тақырып, карусель нүктелері.
    def _cosmos(self, canvas: Image.Image, c: PostCopySchema, handle: str) -> None:
        f = self._fonts
        _shade(canvas, (0, 0, WIDTH, 760), (6, 8, 30, 200), (6, 8, 30, 0))
        _shade(canvas, (0, 1050, WIDTH, HEIGHT), (0, 0, 0, 0), (0, 0, 10, 150))
        _star_emblem(canvas, WIDTH // 2, 170, 128)

        y = 300
        kicker = _clean(c.kicker).upper()
        if kicker:
            font = f.get("Montserrat", "SemiBold", 30)
            _draw_text(canvas, kicker, font, (WIDTH // 2, y), align="center", tracking=8, fill=(205, 212, 255, 230))
            y += 70

        line1, line2 = _clean(c.headline).upper(), _clean(c.headline_accent).upper()
        size = min(
            _fit_size(f, "Oswald", "Bold", line1, 940, 230, 90),
            _fit_size(f, "Oswald", "Bold", line2, 940, 230, 90),
        )
        font = f.get("Oswald", "Bold", size)
        box = _draw_text(
            canvas, line1, font, (WIDTH // 2, y), align="center",
            fill=((246, 246, 255, 255), (178, 186, 238, 255)), glow=(150, 165, 255, 120), glow_radius=22,
        )
        box = _draw_text(
            canvas, line2, font, (WIDTH // 2, box[3] + 14), align="center",
            fill=((168, 196, 255, 255), (92, 124, 255, 255)), glow=(70, 110, 255, 170), glow_radius=26,
        )
        subtitle = _clean(c.subtitle)
        if subtitle:
            sub_font, lines = _wrap_fit(f, "Montserrat", "Medium", subtitle, 860, 2, 40, 28)
            sy = box[3] + 46
            for line in lines:
                b = _draw_text(canvas, line, sub_font, (WIDTH // 2, sy), align="center", shadow=True)
                sy = b[3] + 10
        cta = _clean(c.cta)
        if cta:
            font = f.get("Montserrat", "Bold", 30)
            w = _text_width(font, cta) + 90
            _pill(canvas, (WIDTH // 2 - w // 2, 1110, WIDTH // 2 + w // 2, 1182), (255, 255, 255, 40), (255, 255, 255, 190))
            _draw_text(canvas, cta, font, (WIDTH // 2, 1129), align="center")
        _draw_text(canvas, handle, f.get("Montserrat", "Medium", 30), (WIDTH // 2, 1228), align="center",
                   fill=(255, 255, 255, 215))
        _dots(canvas, 1300)

    # Neon: сол жақта күңгірт перде, кикер-жолақ, неонды акцентті тақырып, батырма.
    def _neon(self, canvas: Image.Image, c: PostCopySchema, handle: str) -> None:
        f = self._fonts
        canvas.alpha_composite(_horizontal_gradient((WIDTH, HEIGHT), (8, 4, 24, 225), (8, 4, 24, 60)))
        _shade(canvas, (0, 820, WIDTH, HEIGHT), (8, 4, 24, 0), (8, 4, 24, 235))
        x = 84

        kicker = _clean(c.kicker).upper() or "NEW"
        k_font = f.get("Oswald", "Bold", 52)
        kw = _text_width(k_font, kicker) + 64
        _pill(canvas, (x, 120, x + kw, 204), (255, 43, 214, 255))
        _draw_text(canvas, kicker, k_font, (x + 32, 133), glow=(255, 43, 214, 160), glow_radius=20)
        bar = _horizontal_gradient((360, 6), (255, 43, 214, 255), (41, 240, 255, 255))
        canvas.alpha_composite(bar, (x, 236))

        line1, line2 = _clean(c.headline).upper(), _clean(c.headline_accent).upper()
        size = min(
            _fit_size(f, "Oswald", "Bold", line1, 900, 200, 80),
            _fit_size(f, "Oswald", "Bold", line2, 900, 200, 80),
        )
        font = f.get("Oswald", "Bold", size)
        box = _draw_text(canvas, line1, font, (x, 300), shadow=True)
        box = _draw_text(
            canvas, line2, font, (x, box[3] + 6),
            fill=((41, 240, 255, 255), (122, 92, 255, 255)), glow=(41, 240, 255, 150), glow_radius=24,
        )
        subtitle = _clean(c.subtitle)
        if subtitle:
            sub_font, lines = _wrap_fit(f, "Montserrat", "Medium", subtitle, 820, 3, 40, 28)
            sy = box[3] + 48
            for line in lines:
                b = _draw_text(canvas, line, sub_font, (x, sy), fill=(236, 232, 255, 240), shadow=True)
                sy = b[3] + 12
        cta = _clean(c.cta) or "Толығырақ"
        c_font = f.get("Montserrat", "Bold", 36)
        cw = _text_width(c_font, cta) + 110
        _pill(canvas, (x, 1100, x + cw, 1190), (255, 255, 255, 255))
        _draw_text(canvas, f"{cta}", c_font, (x + 44, 1124), fill=(20, 10, 40, 255))
        _arrow(canvas, x + cw - 58, 1145, (255, 43, 214, 255))
        _draw_text(canvas, handle, f.get("Montserrat", "SemiBold", 30), (x, 1240), fill=(255, 255, 255, 200))

    # Summit: сызықтары бар ашық кикер, төменде серифті тақырып, жылы алтын акцент.
    def _summit(self, canvas: Image.Image, c: PostCopySchema, handle: str) -> None:
        f = self._fonts
        _shade(canvas, (0, 0, WIDTH, 360), (4, 8, 20, 170), (4, 8, 20, 0))
        _shade(canvas, (0, 560, WIDTH, HEIGHT), (4, 8, 20, 0), (4, 8, 20, 245))

        kicker = _clean(c.kicker).upper()
        if kicker:
            k_font = f.get("Montserrat", "SemiBold", 28)
            box = _draw_text(canvas, kicker, k_font, (WIDTH // 2, 112), align="center", tracking=7,
                             fill=(255, 255, 255, 225))
            draw = ImageDraw.Draw(canvas)
            mid = (box[1] + box[3]) // 2
            draw.line((box[0] - 90, mid, box[0] - 26, mid), fill=(255, 255, 255, 160), width=2)
            draw.line((box[2] + 26, mid, box[2] + 90, mid), fill=(255, 255, 255, 160), width=2)

        q_font = f.get("PlayfairDisplay", "Bold", 220)
        _draw_text(canvas, "“", q_font, (WIDTH // 2, 560), align="center", fill=(255, 217, 160, 230))

        h_font, h_lines = _wrap_fit(f, "PlayfairDisplay", "Bold", _clean(c.headline), 900, 2, 92, 56)
        a_font, a_lines = _wrap_fit(f, "PlayfairDisplay", "Bold", _clean(c.headline_accent), 900, 2, h_font.size, 56)
        y = 760
        for line in h_lines:
            b = _draw_text(canvas, line, h_font, (WIDTH // 2, y), align="center", shadow=True)
            y = b[3] + 8
        for line in a_lines:
            b = _draw_text(canvas, line, a_font, (WIDTH // 2, y), align="center",
                           fill=((255, 226, 178, 255), (255, 190, 120, 255)), glow=(255, 180, 90, 90))
            y = b[3] + 8
        subtitle = _clean(c.subtitle)
        if subtitle:
            sub_font, lines = _wrap_fit(f, "Montserrat", "Regular", subtitle, 840, 2, 34, 26)
            y += 26
            for line in lines:
                b = _draw_text(canvas, line, sub_font, (WIDTH // 2, y), align="center", fill=(255, 255, 255, 215))
                y = b[3] + 8
        cta = _clean(c.cta)
        if cta:
            font = f.get("Montserrat", "SemiBold", 28)
            w = _text_width(font, cta) + 80
            top = min(max(y + 30, 1120), 1150)
            _pill(canvas, (WIDTH // 2 - w // 2, top, WIDTH // 2 + w // 2, top + 64), (0, 0, 0, 0), (255, 217, 160, 230))
            _draw_text(canvas, cta, font, (WIDTH // 2, top + 15), align="center", fill=(255, 226, 178, 255))
        _draw_text(canvas, handle, f.get("Montserrat", "Medium", 28), (WIDTH // 2, 1262), align="center",
                   fill=(255, 255, 255, 190))
