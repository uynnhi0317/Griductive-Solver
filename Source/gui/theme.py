import pygame
from game.character import Status
from .highlight import Role

PALETTE= {
    "card_back": (125, 124, 138, 255),
    "criminal": (184, 36, 33, 255),
    "innocent": (30, 150, 58, 255),
    "highlight": (247, 223, 40, 255),
    "select_criminal": (235, 71, 68, 255),
    "select_innocent": (81, 224, 114, 255),
    "select_card_back": (201, 200, 222, 255),
    "bg": (22, 20, 28, 255),
    "text": (226, 217, 255, 255),
    "hover": (220, 220, 220, 100),
    "selected": (64, 64, 64, 150),
    # highlight roles
    "role_subject": (252, 249, 66, 255),
    "role_counted": (157, 241, 252, 255),
    "role_condition": (202, 59, 209, 255),
    # clue panel
    "panel_bg": (32, 29, 41, 255),
    "panel_row": (44, 40, 56, 255),
    "panel_row_hover": (56, 51, 72, 255),
    "panel_row_selected": (66, 60, 88, 255),
    "text_dim": (150, 143, 175, 255),
}

STATUS_COLOR = {
    Status.CRIMINAL: PALETTE["criminal"],
    Status.INNOCENT: PALETTE["innocent"],
}

SELECT_COLOR = {
    Status.CRIMINAL: PALETTE["select_criminal"],
    Status.INNOCENT: PALETTE["select_innocent"],
}

ROLE_COLOR = {
    Role.SUBJECT: PALETTE["role_subject"],
    Role.COUNTED: PALETTE["role_counted"],
    Role.CONDITION: PALETTE["role_condition"],
}

_fonts: dict[int, pygame.font.Font] = {}
def get_font(size: int) -> pygame.font.Font:
    if size not in _fonts:
        _fonts[size] = pygame.font.Font(None, size)
    return _fonts[size]

def fit_font(text, max_size, max_width):
    size = max(8, max_size)
    while size > 8 and get_font(size).size(text)[0] > max_width:
        size -= 1
    return get_font(size)

def draw_rect_alpha(surface, color, rect, radius=0):
    shape = pygame.Surface(pygame.Rect(rect).size, pygame.SRCALPHA)
    pygame.draw.rect(shape, color, shape.get_rect(), border_radius=radius)
    surface.blit(shape, rect)

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
    """Chọn cỡ chữ lớn nhất để đoạn text ngắt dòng vừa khung; trả về (font, các dòng)"""
    for size in range(max(max_size, min_size), min_size - 1, -1):
        font = get_font(size)
        lines = wrap_text(text, font, max_width)
        if len(lines) * font.get_linesize() <= max_height and all(font.size(l)[0] <= max_width for l in lines):
            return font, lines
    font = get_font(min_size)
    return font, wrap_text(text, font, max_width)