from dataclasses import dataclass
from typing import Callable, Sequence

import pygame

from game.character import Status
from .component import Component
from .theme import (
    Color, LEVEL_COLOR, Level, Radius, Size, Space, Stroke, STATUS_COLOR,
    draw_rect_alpha, draw_status_icon, ellipsize, get_font, render_text,
)

BUTTON_H = 36
ICON_R = 9


class Button(Component):
    """
    Nút bấm. handle_event trả True nếu đã nuốt sự kiện (nhấn / nhả chuột trên nút);
    MOUSEMOTION luôn trả False để mọi nút đều cập nhật được hover.
    Nút có `status` là nút phán quyết: tô màu trạng thái + huy hiệu X / tích,
    xám đi và không bấm được khi enabled = False.
    """

    def __init__(self, label: str, on_click: Callable[[], None], status: Status | None = None):
        self.label = label
        self.on_click = on_click
        self.status = status
        self.rect = pygame.Rect(0, 0, 0, 0)
        self.enabled = True
        self.hovered = False
        self._pressed = False

    def fit(self, rect: pygame.Rect) -> None:
        self.rect = pygame.Rect(rect)

    @property
    def _icon_w(self) -> int:
        return 2 * ICON_R + Space.sm if self.status is not None else 0

    def natural_width(self, pad: int) -> int:
        return get_font(Size.body, True).size(self.label)[0] + self._icon_w + 2 * pad

    # ------------------------------------------------------------ events
    def handle_event(self, e: pygame.event.Event) -> bool:
        if e.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(e.pos)
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            if self.rect.collidepoint(e.pos):
                self._pressed = True
                return True
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1 and self._pressed:
            self._pressed = False
            if self.enabled and self.rect.collidepoint(e.pos):
                self.on_click()
            return True
        return False

    # ------------------------------------------------------------ drawing
    def draw(self, surface: pygame.Surface) -> None:
        r = self.rect
        colored = self.status is not None and self.enabled
        if colored:
            fill = STATUS_COLOR[self.status]
        elif not self.enabled:
            fill = Color.surface_1
        else:
            fill = Color.surface_3 if self.hovered else Color.surface_2
        pygame.draw.rect(surface, fill, r, border_radius=Radius.control)
        if colored:
            if self.hovered:
                draw_rect_alpha(surface, Color.hover_overlay, r, Radius.control)
        else:
            pygame.draw.rect(surface, Color.border, r, width=Stroke.thin, border_radius=Radius.control)
        if self._pressed and self.enabled:
            pygame.draw.rect(surface, Color.focus, r, width=Stroke.medium, border_radius=Radius.control)

        color = Color.text if self.enabled else Color.text_disabled
        text = render_text(self.label, Size.body, color, True)
        x = r.centerx - (self._icon_w + text.get_width()) // 2
        if self.status is not None:
            if self.enabled:
                draw_status_icon(surface, self.status, x + ICON_R, r.centery, ICON_R)
            x += self._icon_w
        surface.blit(text, text.get_rect(midleft=(x, r.centery)))


def place_buttons(rect: pygame.Rect, left: Sequence[Button], right: Sequence[Button],
                  gap: int = Space.sm) -> None:
    """
    Xếp nút trên một thanh: nhóm `left` sát trái, nhóm `right` sát phải, giữa hai nhóm là khoảng trống.
    Không đủ chỗ thì thu hẹp lề trong của nút (lg, md, sm) trước khi chịu tràn.
    """
    buttons = [*left, *right]
    for pad in (Space.lg, Space.md, Space.sm):
        widths = [b.natural_width(pad) for b in buttons]
        if sum(widths) + gap * (len(buttons) - 1) + Space.lg <= rect.w:
            break
    y = rect.y + (rect.h - BUTTON_H) // 2

    x = rect.x
    for b, w in zip(left, widths):
        b.rect = pygame.Rect(x, y, w, BUTTON_H)
        x += w + gap

    x = rect.right
    for b, w in zip(reversed(right), reversed(widths[len(left):])):
        x -= w
        b.rect = pygame.Rect(x, y, w, BUTTON_H)
        x -= gap


# ------------------------------------------------------------------ toasts
TOAST_MAX = 3
TOAST_FADE = 0.4                 # giây cuối cùng mờ dần
TOAST_STRIPE_W = 6
_TOAST_SECONDS = {Level.INFO: 3.0, Level.OK: 3.0, Level.WARN: 4.0, Level.ERROR: 5.0}
ALPHA_OPAQUE = 255


@dataclass
class _Toast:
    message: str
    level: Level
    ttl: float


class ToastManager(Component):
    """
    Thông báo ngắn tự tắt, xếp dọc từ trên cùng của vùng được fit(), mới nhất ở trên.
    Không nhận sự kiện chuột nên không chặn thao tác bên dưới.
    """

    def __init__(self) -> None:
        self.rect = pygame.Rect(0, 0, 0, 0)
        self._toasts: list[_Toast] = []

    def fit(self, rect: pygame.Rect) -> None:
        self.rect = pygame.Rect(rect)

    def show(self, message: str, level: Level = Level.INFO) -> None:
        self._toasts.insert(0, _Toast(message, level, _TOAST_SECONDS[level]))
        del self._toasts[TOAST_MAX:]

    def clear(self) -> None:
        self._toasts.clear()

    def update(self, dt: float) -> None:
        for t in self._toasts:
            t.ttl -= dt
        self._toasts = [t for t in self._toasts if t.ttl > 0]

    def draw(self, surface: pygame.Surface) -> None:
        font = get_font(Size.body)
        max_text_w = max(0, self.rect.w - 2 * Space.lg - TOAST_STRIPE_W - 2 * Space.md)
        y = self.rect.y + Space.md
        for t in self._toasts:
            text = render_text(ellipsize(t.message, font, max_text_w), Size.body, Color.text)
            w = TOAST_STRIPE_W + 2 * Space.md + text.get_width()
            h = text.get_height() + 2 * Space.md
            box = pygame.Surface((w, h), pygame.SRCALPHA)
            pygame.draw.rect(box, Color.surface_2, box.get_rect(), border_radius=Radius.control)
            pygame.draw.rect(box, Color.border, box.get_rect(), width=Stroke.thin, border_radius=Radius.control)
            pygame.draw.rect(box, LEVEL_COLOR[t.level], (0, 0, TOAST_STRIPE_W, h),
                             border_top_left_radius=Radius.control, border_bottom_left_radius=Radius.control)
            box.blit(text, (TOAST_STRIPE_W + Space.md, Space.md))
            box.set_alpha(int(ALPHA_OPAQUE * min(1.0, t.ttl / TOAST_FADE)))
            surface.blit(box, box.get_rect(midtop=(self.rect.centerx, y)))
            y += h + Space.sm