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

BUTTON_H = 36
ICON_R = 9


class Button(Component):
    """
    Nút bấm. handle_event trả True nếu đã nuốt sự kiện (nhấn / nhả chuột trên nút);
    MOUSEMOTION luôn trả False để mọi nút đều cập nhật được hover.
    Nút có `status` là nút phán quyết: tô màu trạng thái + huy hiệu X / tích,
    xám đi và không bấm được khi enabled = False.
    """

    def __init__(self, label: str, on_click: Callable[[], None], status: Status | None = None,
                 on_disabled_click: Callable[[], None] | None = None):
        self.label = label
        self.on_click = on_click
        self.on_disabled_click = on_disabled_click
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
            if self.rect.collidepoint(e.pos):
                if self.enabled:
                    self.on_click()
                elif self.on_disabled_click is not None:
                    self.on_disabled_click()
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


# ------------------------------------------------------------------ tab bar
TAB_H = 36
TAB_PAD_X = Space.md
TAB_MIN_W = 60


class TabBar(Component):
    """
    Horizontal tab bar: a row of labelled tabs; clicking activates one.
    Call active_index to read the current selection.
    on_change(index) is called whenever the active tab changes.
    """

    def __init__(self, labels: Sequence[str],
                 on_change: Callable[[int], None] | None = None,
                 initial: int = 0) -> None:
        self._labels = list(labels)
        self._on_change = on_change or (lambda i: None)
        self._active = initial
        self.rect = pygame.Rect(0, 0, 0, 0)
        self._tab_rects: list[pygame.Rect] = []
        self._hovered: int | None = None

    # ---------------------------------------------------------------- state
    @property
    def active_index(self) -> int:
        return self._active

    def set_active(self, index: int) -> None:
        if 0 <= index < len(self._labels) and index != self._active:
            self._active = index
            self._on_change(index)

    # --------------------------------------------------------------- layout
    def fit(self, rect: pygame.Rect) -> None:
        self.rect = pygame.Rect(rect)
        self._layout()

    def _layout(self) -> None:
        """Distribute tabs evenly across the bar width."""
        n = len(self._labels)
        if n == 0:
            self._tab_rects = []
            return
        tab_w = self.rect.w // n
        self._tab_rects = [
            pygame.Rect(self.rect.x + i * tab_w, self.rect.y, tab_w, TAB_H)
            for i in range(n)
        ]
        # stretch last tab to cover rounding remainder
        if self._tab_rects:
            last = self._tab_rects[-1]
            self._tab_rects[-1] = pygame.Rect(last.x, last.y,
                                               self.rect.right - last.x, last.h)

    # --------------------------------------------------------------- events
    def handle_event(self, e: pygame.event.Event) -> bool:
        if e.type == pygame.MOUSEMOTION:
            self._hovered = self._tab_at(e.pos)
            return False   # don't consume: others need hover too
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            idx = self._tab_at(e.pos)
            if idx is not None:
                self.set_active(idx)
                return True
        return False

    def _tab_at(self, pos) -> int | None:
        for i, r in enumerate(self._tab_rects):
            if r.collidepoint(pos):
                return i
        return None

    # ----------------------------------------------------------------- draw
    def draw(self, surface: pygame.Surface) -> None:
        font = get_font(Size.body, True)
        for i, (label, r) in enumerate(zip(self._labels, self._tab_rects)):
            active = i == self._active
            hovered = i == self._hovered and not active
            # background
            if active:
                bg = Color.surface_3
            elif hovered:
                bg = Color.surface_2
            else:
                bg = Color.surface_1
            pygame.draw.rect(surface, bg, r)
            # active indicator underline
            if active:
                pygame.draw.line(surface, Color.focus,
                                 (r.x, r.bottom - 2), (r.right, r.bottom - 2), 2)
            # label
            color = Color.text if active else Color.text_dim
            txt = render_text(label, Size.body, color, True)
            surface.blit(txt, txt.get_rect(center=r.center))
        # bottom border
        pygame.draw.line(surface, Color.border,
                         (self.rect.x, self.rect.bottom - 1),
                         (self.rect.right, self.rect.bottom - 1))