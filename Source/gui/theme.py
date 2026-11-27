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
    # nền và bề mặt — light vintage paper
    bg = _hex("E9E0D0")              # warm archival paper
    surface_1 = _hex("F5EFE3")       # ivory: sidebar, toolbar, panels
    surface_2 = _hex("EDE4D4")       # parchment: clue rows, buttons
    surface_3 = _hex("E2D5C0")       # darker parchment: hover
    border = _hex("C8B99F")          # aged paper border

    # chữ trên nền sáng
    text = _hex("342B22")            # dark ink
    text_dim = _hex("766653")        # faded sepia
    text_disabled = _hex("A99C89")
    scrollbar = _hex("A8957D", 140)

    # chữ trên thẻ
    card_text = _hex("34271F")       # dark brown ink
    card_text_dim = _hex("715D47")  # faded brown

    # thẻ
    card_back = _hex("C5AD88")       # aged parchment
    card_back_hover = _hex("D3BD99")
    card_border = _hex("947A57")     # antique brass

    criminal = _hex("963F3B")        # muted burgundy
    innocent = _hex("39775A")        # muted forest green

    badge_bg = _hex("342B22")        # dark ink badge
    on_status = _hex("FBF6EC")       # chữ / ký hiệu trên nền đậm (nút phán quyết, huy hiệu)
    verdict_criminal = _hex("AE4F48")  # nút Criminal: sáng hơn criminal, chữ on_status vẫn 4.9:1
    verdict_innocent = _hex("3C7E5D")  # nút Innocent: sáng hơn innocent, chữ on_status vẫn 4.5:1

    # thẻ đã lật — giấy sáng, verdict tint nhẹ
    card_face = _hex("F2E8D5")       # warm ivory paper
    card_face_criminal = _hex("E8D0C5") # parchment with subtle red tint
    card_face_innocent = _hex("D8E2D1") # parchment with subtle green tint

    stamp_criminal = _hex("812F2B")  # dark burgundy ink
    stamp_innocent = _hex("285C43")  # dark forest ink

    # tương tác
    accent = _hex("A77B35")          # antique gold
    focus = _hex("A77B35")           # gold selection ring
    focus_edge = _hex("F5EFE3")      # ivory outer separation

    hint = _hex("B65F25")             # burnt amber

    hover_overlay = (52, 43, 34, 16)
    scrim = _hex("342B22", 110)

    # vai trò khi highlight clue
    # darker colors for visibility on light parchment
    role_subject = _hex("A57923")    # antique gold
    role_counted = _hex("287F83")    # deep dusty teal
    role_condition = _hex("92549E")  # muted plum

    role_tint = 35

    # phản hồi
    fb_info = _hex("39758D")         # archival blue
    fb_warn = _hex("A47722")         # amber
    fb_error = _hex("AD4640")        # muted red
    fb_ok = _hex("397A58")           # forest green


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

FACE_COLOR = {          # nền thẻ đã lật, chữ card_text trên nền này vẫn tương phản >= 5.5:1
    Status.CRIMINAL: Color.card_face_criminal,
    Status.INNOCENT: Color.card_face_innocent,
}
VERDICT_COLOR = {       # nền nút phán quyết (STATUS_COLOR vẫn dùng cho viền thẻ, huy hiệu panel)
    Status.CRIMINAL: Color.verdict_criminal,
    Status.INNOCENT: Color.verdict_innocent,
}
STAMP_COLOR = {
    Status.CRIMINAL: Color.stamp_criminal,
    Status.INNOCENT: Color.stamp_innocent,
}

ROLE_COLOR = {
    Role.SUBJECT: Color.role_subject,
    Role.COUNTED: Color.role_counted,
    Role.CONDITION: Color.role_condition,
}


# ------------------------------------------------------------------ fonts
class Face:
    """Vai trò kiểu chữ"""
    BODY = "body"               # Source Sans 3: clue, nghề, nút, status bar
    DISPLAY = "display"         # Oswald: tên nghi phạm, tiêu đề mục, tab
    TYPEWRITER = "typewriter"   # Special Elite: tên vụ án, mã ô, con dấu


FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
_FONT_FILES = {
    (Face.BODY, False): "SourceSans3-Regular.ttf",
    (Face.BODY, True): "SourceSans3-SemiBold.ttf",
    (Face.DISPLAY, False): "Oswald-Medium.ttf",
    (Face.DISPLAY, True): "Oswald-SemiBold.ttf",
    (Face.TYPEWRITER, False): "SpecialElite-Regular.ttf",
    (Face.TYPEWRITER, True): "SpecialElite-Regular.ttf",   # chỉ có một độ đậm
}
_FALLBACK_FAMILIES = {
    Face.BODY: "segoeui,helveticaneue,helvetica,arial,dejavusans",
    Face.DISPLAY: "oswald,impact,arialnarrow,arial,dejavusans",
    Face.TYPEWRITER: "couriernew,courier,dejavusansmono",
}


@functools.lru_cache(maxsize=None)
def get_font(size: int, bold: bool = False, face: str = Face.BODY) -> pygame.font.Font:
    """Font TTF đóng gói theo dự án; thiếu file thì rơi về font hệ thống"""
    path = FONT_DIR / _FONT_FILES[(face, bold)]
    if path.is_file():
        return pygame.font.Font(str(path), size)
    return pygame.font.SysFont(_FALLBACK_FAMILIES[face], size, bold=bold)


@functools.lru_cache(maxsize=1024)
def render_text(text: str, size: int, color: tuple, bold: bool = False, face: str = Face.BODY) -> pygame.Surface:
    return get_font(size, bold, face).render(text, True, color)


def ellipsize(text: str, font: pygame.font.Font, max_width: int) -> str:
    """Cắt cuối chuỗi và thêm '...' cho vừa max_width (giữ nguyên nếu đã vừa)"""
    if font.size(text)[0] <= max_width:
        return text
    while text and font.size(text + "...")[0] > max_width:
        text = text[:-1]
    return text.rstrip() + "..."


def fit_line(text: str, max_size: int, max_width: int, bold: bool = False,
             min_size: int = Size.min_text, face: str = Face.BODY) -> tuple[pygame.font.Font, str]:
    """Một dòng: co cỡ chữ tới min_size, vẫn không vừa thì cắt bằng '...'. Trả về (font, text)"""
    size = max(min_size, max_size)
    while size > min_size and get_font(size, bold, face).size(text)[0] > max_width:
        size -= 1
    font = get_font(size, bold, face)
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
    from .avatar import clear_cache as clear_avatar_cache   # import trễ: avatar không phụ thuộc theme
    render_text.cache_clear()
    get_font.cache_clear()
    clear_avatar_cache()                                    # Surface avatar cũng hỏng sau pygame.quit()
    
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
    pygame.draw.circle(surface, Color.on_status, (cx, cy), r, width=max(1, r // 7))
    d = r * 0.42
    width = max(2, r // 4)
    if status is Status.CRIMINAL:
        pygame.draw.line(surface, Color.on_status, (cx - d, cy - d), (cx + d, cy + d), width)
        pygame.draw.line(surface, Color.on_status, (cx - d, cy + d), (cx + d, cy - d), width)
    else:
        pts = [(cx - d, cy + d * 0.05), (cx - d * 0.25, cy + d * 0.8), (cx + d, cy - d * 0.7)]
        pygame.draw.lines(surface, Color.on_status, False, pts, width)

def draw_scrollbar(surface: pygame.Surface, vp: pygame.Rect, content_h: int, scroll: int, max_scroll: int) -> None:
        if max_scroll <= 0:
            return
        track_h = vp.h
        thumb_h = max(24, track_h * vp.h // content_h)
        thumb_y = vp.y + (track_h - thumb_h) * scroll // max_scroll
        thumb = pygame.Rect(vp.right - SCROLLBAR_W - Space.xs, thumb_y, SCROLLBAR_W, thumb_h)
        draw_rect_alpha(surface, Color.scrollbar, thumb, Radius.small)