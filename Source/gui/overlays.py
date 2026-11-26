"""
Overlay modal toàn cửa sổ: hướng dẫn điều khiển (lần chạy đầu / F1) và chọn màn (Load)

+ App giữ tối đa MỘT overlay đang mở; overlay nuốt mọi sự kiện còn lại nên không thao tác được bên dưới
+ Overlay không biết gì về engine: Load chỉ nhận StageInfo (tên, cỡ) và gọi callback
+ peek_stage chỉ lấy hai trường title / size từ file puzzle, không dựng PuzzleFull
"""

import math
from typing import Callable

import pygame

from .component import Component
from .theme import Color, Radius, Size, Space, Stroke, draw_rect_alpha, ellipsize, get_font, render_text


def _mix(a: tuple, b: tuple, t: float) -> tuple[int, int, int, int]:
    return (*(round(x + (y - x) * t) for x, y in zip(a[:3], b[:3])), 255)


class Overlay(Component):
    """Lớp phủ modal; handle_event luôn trả True để chặn mọi thứ bên dưới"""

    def __init__(self) -> None:
        self.rect = pygame.Rect(0, 0, 0, 0)     # toàn cửa sổ
        self.panel = pygame.Rect(0, 0, 0, 0)

    def fit(self, rect: pygame.Rect) -> None:
        self.rect = pygame.Rect(rect)
        self._layout()

    def _layout(self) -> None:
        raise NotImplementedError

    def _draw_panel(self, surface: pygame.Surface) -> None:
        draw_rect_alpha(surface, Color.scrim, self.rect)
        pygame.draw.rect(surface, Color.surface_1, self.panel, border_radius=Radius.card)
        pygame.draw.rect(surface, Color.border, self.panel, width=Stroke.thin, border_radius=Radius.card)


# ------------------------------------------------------------------ guide
_GUIDE_ROWS = (
    ("Click / Arrows", "Select a card"),
    ("Click a clue", "Highlight the cells it refers to"),
    ("C  /  I", "Call the card Criminal / Innocent"),
    ("H", "Hint: show a provable card and its clues"),
    ("A", "Auto Solve / Stop"),
    ("Esc", "Deselect, or stop Auto Solve"),
    ("PgUp / PgDn", "Previous / next stage"),
    ("F1", "Show this guide"),
)
_ROW_H = 34
_CHIP_W, _CHIP_H = 140, 26
_HEADER_H = 80
_FOOTER_H = 48
_PULSE_HZ = 0.8


class GuideOverlay(Overlay):
    def __init__(self, on_close: Callable[[], None]) -> None:
        super().__init__()
        self._on_close = on_close
        self.footer = "Click anywhere to start"
        self._t = 0.0

    def _layout(self) -> None:
        w, h = self.rect.size
        pw = min(640, w - 2 * Space.xl)
        ph = 2 * Space.xl + _HEADER_H + len(_GUIDE_ROWS) * _ROW_H + _FOOTER_H
        self.panel = pygame.Rect(0, 0, pw, ph)
        self.panel.center = self.rect.center

    def update(self, dt: float) -> None:
        self._t += dt

    def handle_event(self, e: pygame.event.Event) -> bool:
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            self._on_close()
        elif e.type == pygame.KEYDOWN and e.key in (pygame.K_RETURN, pygame.K_KP_ENTER,
                                                    pygame.K_SPACE, pygame.K_ESCAPE):
            self._on_close()
        return True

    def draw(self, surface: pygame.Surface) -> None:
        self._draw_panel(surface)
        p = self.panel
        x0, inner_w = p.x + Space.xl, p.w - 2 * Space.xl

        surface.blit(render_text("How to play", Size.title, Color.text, True), (x0, p.y + Space.xl))
        sub = ellipsize("Makes verdicts based on the revealed clues.",
                        get_font(Size.body), inner_w)
        surface.blit(render_text(sub, Size.body, Color.text_dim), (x0, p.y + Space.xl + 40))

        body = get_font(Size.body)
        y = p.y + Space.xl + _HEADER_H
        for key, desc in _GUIDE_ROWS:
            chip = pygame.Rect(x0, y + (_ROW_H - _CHIP_H) // 2, _CHIP_W, _CHIP_H)
            pygame.draw.rect(surface, Color.surface_3, chip, border_radius=Radius.control)
            pygame.draw.rect(surface, Color.border, chip, width=Stroke.thin, border_radius=Radius.control)
            k = render_text(key, Size.caption, Color.text, True)
            surface.blit(k, k.get_rect(center=chip.center))
            text_x = chip.right + Space.md
            d = render_text(ellipsize(desc, body, p.right - Space.xl - text_x), Size.body, Color.text)
            surface.blit(d, d.get_rect(midleft=(text_x, chip.centery)))
            y += _ROW_H

        pygame.draw.line(surface, Color.border, (x0, y + Space.sm), (p.right - Space.xl, y + Space.sm))
        phase = 0.5 - 0.5 * math.cos(2 * math.pi * _PULSE_HZ * self._t)
        color = _mix(Color.text_dim, Color.text, round(phase * 10) / 10)   # lượng tử hoá để cache chữ không phình
        foot = render_text(self.footer, Size.h2, color, True)
        surface.blit(foot, foot.get_rect(center=(p.centerx, y + _FOOTER_H // 2 + Space.sm)))