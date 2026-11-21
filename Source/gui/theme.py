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

import pygame

from game.character import Status
from .highlight import Role


def _hex(value: str, alpha: int = 255) -> tuple[int, int, int, int]:
    v = value.lstrip("#")
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16), alpha


class Color:
    # nền và bề mặt (sáng dần theo độ nổi)
    bg = _hex("12101A")
    surface_1 = _hex("1B1826")       # panel, toolbar
    surface_2 = _hex("262235")       # dòng clue, nút
    surface_3 = _hex("322D45")       # hover trên surface
    border = _hex("3A3552")          # đường chia, viền panel

    # chữ
    text = _hex("EDE9FF")
    text_dim = _hex("A9A2C7")
    text_disabled = _hex("6B6585")
    scrollbar = _hex("A9A2C7", 140)

    # thẻ
    card_back = _hex("2F2B44")       # thẻ úp, tương phản với text ~11:1
    card_back_hover = _hex("3A3556")
    card_border = _hex("5A5380")
    criminal = _hex("B8323F")
    innocent = _hex("17795A")
    badge_bg = _hex("12101A")        # nền huy hiệu trạng thái, luôn tối để biểu tượng sáng nổi lên

    # tương tác (cố ý trung tính để không đụng với 3 màu role và 2 màu trạng thái)
    focus = _hex("F4F1FF")
    hover_overlay = (255, 255, 255, 22)

    # vai trò khi highlight clue
    role_subject = _hex("FFD84D")
    role_counted = _hex("6FE3F5")
    role_condition = _hex("D86BE0")
    role_tint = 50

    # phản hồi (toast, dùng ở P2)
    fb_info = _hex("5AA9FF")
    fb_warn = _hex("F2B84B")
    fb_error = _hex("FF6B6B")
    fb_ok = _hex("4FD18B")


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


# ---------------------------------------------------------------- drawing
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