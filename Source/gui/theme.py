"""
Design tokens của GUI: màu, cỡ chữ, thang khoảng cách, bo góc, độ dày nét định nghĩa ở đây.
Hằng số hình học riêng của một component đặt tên rõ ở đầu file component đó,
và nếu dùng số lẻ thì phải rút ra từ thang Space.

+ Màu đặt tên theo VAI TRÒ (surface_2, text_dim...), không theo chỗ dùng (select_card_back...)
+ Component khác chỉ import Color, Size, Space, Radius; không viết tuple RGB hay số pixel rời rạc
+ Font: nạp từ gui/assets/fonts/ nếu có file, không thì dùng SysFont (xem get_font)
"""

import functools
from pathlib import Path
from enum import Enum

import pygame

from game.character import Status
from .highlight import Role


def _hex(value: str, alpha: int = 255) -> tuple[int, int, int, int]:
    v = value.lstrip("#")
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16), alpha


class Color:
    # nền và bề mặt (sáng dần theo độ nổi)
    bg = _hex("151310")              # ink black
    surface_1 = _hex("211C18")       # dark walnut: panel, toolbar
    surface_2 = _hex("2B251F")       # dòng clue, nút
    surface_3 = _hex("38302A")       # hover trên surface
    border = _hex("4A3E2D")          # đường chia, viền panel (brass tối hơn để không quá nặng)

    # chữ trên nền tối
    text = _hex("F5EEDC")            # ivory
    text_dim = _hex("A8957D")        # faded sepia, sáng hơn một chút so với 8D7964 để đủ tương phản
    text_disabled = _hex("6E6253")
    scrollbar = _hex("A8957D", 140)

    # chữ trên thẻ úp (giấy da)
    card_text = _hex("34271F")       # dark brown
    card_text_dim = _hex("4A3C2E")

    # thẻ
    card_back = _hex("C5AD88")       # aged parchment
    card_back_hover = _hex("D3BD99")
    card_border = _hex("6D573A")     # aged brass
    criminal = _hex("963F3B")        # muted burgundy
    innocent = _hex("39775A")        # muted forest green
    badge_bg = _hex("151310")

    # tương tác
    accent = _hex("C49A58")          # antique gold, chỉ dành cho chrome, KHÔNG dùng gần vùng highlight
    focus = _hex("F5EEDC")
    focus_edge = _hex("151310")      # viền tối ngoài vòng focus, để vòng thấy được trên giấy da
    hint = _hex("FF8C42")
    hover_overlay = (255, 255, 255, 22)
    scrim = _hex("0B0A08", 215)

    # vai trò khi highlight clue
    role_subject = _hex("D5A64A")    # antique gold
    role_counted = _hex("54B8B8")    # dusty teal
    role_condition = _hex("BD78C9")  # muted orchid
    role_tint = 50

    # phản hồi
    fb_info = _hex("6FA3B8")
    fb_warn = _hex("D9A441")
    fb_error = _hex("D9625B")
    fb_ok = _hex("6FB58A")


class Space:
    """Thang khoảng cách: chỉ dùng các giá trị này cho padding / gap"""
    xs, sm, md, lg, xl, xxl = 4, 8, 12, 16, 24, 32


class Size:
    """Thang cỡ chữ (pixel, dùng với font TTF)"""
    caption, body, h2, title = 14, 18, 22, 28
    min_text = 10


class Radius:
    card = 10
    control = 8
    small = 3

class Stroke:
    thin, medium, thick = 1, 2, 3

class Level(Enum):
    """Mức độ của thông báo trên thanh trạng thái / toast"""
    INFO = "info"
    WARN = "warn"
    ERROR = "error"
    OK = "ok"


LEVEL_COLOR = {
    Level.INFO: Color.fb_info,
    Level.WARN: Color.fb_warn,
    Level.ERROR: Color.fb_error,
    Level.OK: Color.fb_ok,
}

STATUS_COLOR = {
    Status.CRIMINAL: Color.criminal,
    Status.INNOCENT: Color.innocent,
}

ROLE_COLOR = {
    Role.SUBJECT: Color.role_subject,
    Role.COUNTED: Color.role_counted,
    Role.CONDITION: Color.role_condition,
}


# ------------------------------------------------------------------ fonts
FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
_FONT_FILES = {False: "Inter-Regular.ttf", True: "Inter-SemiBold.ttf"}
_FALLBACK_FAMILIES = "segoeui,helveticaneue,helvetica,arial,dejavusans"


@functools.lru_cache(maxsize=None)
def get_font(size: int, bold: bool = False) -> pygame.font.Font:
    """Font TTF đóng gói theo dự án; thiếu file thì rơi về font hệ thống"""
    path = FONT_DIR / _FONT_FILES[bold]
    if path.is_file():
        return pygame.font.Font(str(path), size)
    return pygame.font.SysFont(_FALLBACK_FAMILIES, size, bold=bold)


@functools.lru_cache(maxsize=1024)
def render_text(text: str, size: int, color: tuple, bold: bool = False) -> pygame.Surface:
    """
    Render chữ có cache theo (text, size, color, bold).
    Surface trả về được dùng chung giữa các lần gọi: KHÔNG được sửa nó.
    """
    return get_font(size, bold).render(text, True, color)


def ellipsize(text: str, font: pygame.font.Font, max_width: int) -> str:
    """Cắt cuối chuỗi và thêm '...' cho vừa max_width (giữ nguyên nếu đã vừa)"""
    if font.size(text)[0] <= max_width:
        return text
    while text and font.size(text + "...")[0] > max_width:
        text = text[:-1]
    return text.rstrip() + "..."


def fit_line(text: str, max_size: int, max_width: int, bold: bool = False,
             min_size: int = Size.min_text) -> tuple[pygame.font.Font, str]:
    """Một dòng: co cỡ chữ tới min_size, vẫn không vừa thì cắt bằng '...'. Trả về (font, text)"""
    size = max(min_size, max_size)
    while size > min_size and get_font(size, bold).size(text)[0] > max_width:
        size -= 1
    font = get_font(size, bold)
    return font, ellipsize(text, font, max_width)


def wrap_text(text: str, font: pygame.font.Font, max_width: int) -> list[str]:
    """Ngắt dòng theo từ; từ dài hơn max_width vẫn nằm trên một dòng riêng"""
    lines: list[str] = []
    line = ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if line and font.size(trial)[0] > max_width:
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)
    return lines


def fit_wrapped(text: str, max_width: int, max_height: int, max_size: int, min_size: int = 10):
    """Chọn cỡ chữ lớn nhất để đoạn text ngắt dòng vừa khung; trả về (font, các dòng), không đủ dòng thì ngắt bằng '...' """
    for size in range(max(max_size, min_size), min_size - 1, -1):
        font = get_font(size)
        lines = wrap_text(text, font, max_width)
        if len(lines) * font.get_linesize() <= max_height and all(font.size(l)[0] <= max_width for l in lines):
            return font, lines
    font = get_font(min_size)
    lines = wrap_text(text, font, max_width)
    max_lines = max(1, max_height // font.get_linesize())
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and font.size(last + "...")[0] > max_width:
            last = last[:-1]
        lines[-1] = last.rstrip() + "..."
    return font, lines

def clear_caches() -> None:
    """
    Xóa cache font và chữ đã render. Font bị hỏng sau pygame.quit(), nên phải gọi hàm này
    trước pygame.quit() nếu sau đó còn pygame.init() lại (ví dụ giữa các test).
    """
    render_text.cache_clear()
    get_font.cache_clear()
    
# ---------------------------------------------------------------- drawing
SCROLLBAR_W = 6

def draw_rect_alpha(surface, color, rect, radius=0):
    shape = pygame.Surface(pygame.Rect(rect).size, pygame.SRCALPHA)
    pygame.draw.rect(shape, color, shape.get_rect(), border_radius=radius)
    surface.blit(shape, rect)


def draw_status_icon(surface: pygame.Surface, status: Status, cx: int, cy: int, r: int) -> None:
    """
    Huy hiệu trạng thái không phụ thuộc màu: dấu X (criminal) hoặc dấu tích (innocent)
    trong vòng tròn tối. Dùng chung cho thẻ và panel để hai nơi luôn khớp nhau.
    """
    pygame.draw.circle(surface, Color.badge_bg, (cx, cy), r)
    pygame.draw.circle(surface, Color.text, (cx, cy), r, width=max(1, r // 7))
    d = r * 0.42
    width = max(2, r // 4)
    if status is Status.CRIMINAL:
        pygame.draw.line(surface, Color.text, (cx - d, cy - d), (cx + d, cy + d), width)
        pygame.draw.line(surface, Color.text, (cx - d, cy + d), (cx + d, cy - d), width)
    else:
        pts = [(cx - d, cy + d * 0.05), (cx - d * 0.25, cy + d * 0.8), (cx + d, cy - d * 0.7)]
        pygame.draw.lines(surface, Color.text, False, pts, width)

def draw_scrollbar(surface: pygame.Surface, vp: pygame.Rect, content_h: int, scroll: int, max_scroll: int) -> None:
        if max_scroll <= 0:
            return
        track_h = vp.h
        thumb_h = max(24, track_h * vp.h // content_h)
        thumb_y = vp.y + (track_h - thumb_h) * scroll // max_scroll
        thumb = pygame.Rect(vp.right - SCROLLBAR_W - Space.xs, thumb_y, SCROLLBAR_W, thumb_h)
        draw_rect_alpha(surface, Color.scrollbar, thumb, Radius.small)