import pygame
from game.character import Status

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
    "selected": (30, 30, 30, 100)
}

STATUS_COLOR = {
    Status.CRIMINAL: PALETTE["criminal"],
    Status.INNOCENT: PALETTE["innocent"],
}

SELECT_COLOR = {
    Status.CRIMINAL: PALETTE["select_criminal"],
    Status.INNOCENT: PALETTE["select_innocent"],
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