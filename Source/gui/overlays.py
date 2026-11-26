"""
Overlay modal toàn cửa sổ: hướng dẫn điều khiển (lần chạy đầu / F1) và chọn màn (Load)

+ App giữ tối đa MỘT overlay đang mở; overlay nuốt mọi sự kiện còn lại nên không thao tác được bên dưới
+ Overlay không biết gì về engine: Load chỉ nhận StageInfo (tên, cỡ) và gọi callback
+ peek_stage chỉ lấy hai trường title / size từ file puzzle, không dựng PuzzleFull
"""

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

import pygame

from .component import Component
from .theme import Color, Radius, Size, Space, Stroke, draw_rect_alpha, ellipsize, get_font, render_text
from .widgets import BUTTON_H, Button


@dataclass(frozen=True)
class StageInfo:
    path: Path
    title: str
    size: int | None            # None nếu không đọc được
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def peek_stage(path: Path) -> StageInfo:
    """Chỉ giữ lại title và size của file puzzle; file hỏng thì trả StageInfo có error"""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        size = data["size"]
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise ValueError(f"size = {size!r}")
        return StageInfo(path, str(data.get("title") or data.get("id") or path.stem), size)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return StageInfo(path, path.stem, None, f"Cannot read this file ({type(exc).__name__})")


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
    ("L", "Load a stage"),
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


# ------------------------------------------------------------------ load
class LoadOverlay(Overlay):
    NAV = 44
    BTN_W = 104
    HEIGHT = 270

    def __init__(self, on_apply: Callable[[int], None], on_cancel: Callable[[], None]) -> None:
        super().__init__()
        self._on_apply, self._on_cancel = on_apply, on_cancel
        self.stages: list[StageInfo] = []
        self.index = 0
        self.current: int | None = None      # màn đang chơi
        self.prev = Button("<", lambda: self._step(-1))
        self.next = Button(">", lambda: self._step(1))
        self.apply = Button("Apply", self._apply)
        self.cancel = Button("Cancel", on_cancel)

    @property
    def buttons(self) -> tuple[Button, ...]:
        return self.prev, self.next, self.apply, self.cancel

    def open(self, stages: Sequence[StageInfo], index: int, current: int | None) -> None:
        self.stages = list(stages)
        self.index = index % len(self.stages)
        self.current = current
        self.prev.enabled = self.next.enabled = len(self.stages) > 1
        self._sync()

    def _step(self, delta: int) -> None:
        self.index = (self.index + delta) % len(self.stages)
        self._sync()

    def _sync(self) -> None:
        """Apply chỉ bấm được khi file đọc được và không phải màn đang chơi"""
        self.apply.enabled = self.stages[self.index].ok and self.index != self.current

    def _apply(self) -> None:
        self._on_apply(self.index)

    def _layout(self) -> None:
        pw = min(560, self.rect.w - 2 * Space.xl)
        self.panel = pygame.Rect(0, 0, pw, self.HEIGHT)
        self.panel.center = self.rect.center
        p, n = self.panel, self.NAV
        cy = p.y + 125
        self.prev.rect = pygame.Rect(p.x + Space.xl, cy - n // 2, n, n)
        self.next.rect = pygame.Rect(p.right - Space.xl - n, cy - n // 2, n, n)
        by = p.bottom - Space.xl - BUTTON_H
        self.cancel.rect = pygame.Rect(p.right - Space.xl - self.BTN_W, by, self.BTN_W, BUTTON_H)
        self.apply.rect = pygame.Rect(self.cancel.rect.x - Space.sm - self.BTN_W, by, self.BTN_W, BUTTON_H)

    def handle_event(self, e: pygame.event.Event) -> bool:
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_LEFT:
                self._step(-1)
            elif e.key == pygame.K_RIGHT:
                self._step(1)
            elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                if self.apply.enabled:
                    self._apply()
            elif e.key == pygame.K_ESCAPE:
                self._on_cancel()
            return True
        for b in self.buttons:          # không dùng any(): mọi nút phải thấy sự kiện để cập nhật hover
            b.handle_event(e)
        return True

    def draw(self, surface: pygame.Surface) -> None:
        self._draw_panel(surface)
        p = self.panel
        title = render_text("Load stage", Size.title, Color.text, True)
        surface.blit(title, (p.x + Space.xl, p.y + Space.xl))
        count = render_text(f"{self.index + 1} / {len(self.stages)}", Size.body, Color.text_dim)
        surface.blit(count, count.get_rect(midright=(p.right - Space.xl, p.y + Space.xl + title.get_height() // 2)))

        info = self.stages[self.index]
        cx, cy = p.centerx, self.prev.rect.centery
        max_w = self.next.rect.x - self.prev.rect.right - 2 * Space.md
        size_txt = f"{info.size}x{info.size}" if info.size else "?"
        line = ellipsize(f"Stage {self.index + 1:02d}: {info.title} ({size_txt})", get_font(Size.h2, True), max_w)
        main = render_text(line, Size.h2, Color.text, True)
        surface.blit(main, main.get_rect(center=(cx, cy - 14)))
        name = render_text(ellipsize(info.path.name, get_font(Size.caption), max_w), Size.caption, Color.text_dim)
        surface.blit(name, name.get_rect(center=(cx, cy + 12)))

        note, color = None, Color.text
        if not info.ok:
            note, color = info.error, Color.fb_error
        elif self.index == self.current:
            note, color = "Currently playing", Color.fb_info
        if note:
            n = render_text(ellipsize(note, get_font(Size.body), max_w), Size.body, color)
            surface.blit(n, n.get_rect(center=(cx, cy + 36)))

        hint = ellipsize("Left / Right: browse   Enter: apply   Esc: cancel", get_font(Size.caption), p.w - 2 * Space.xl)
        h = render_text(hint, Size.caption, Color.text_dim)
        surface.blit(h, h.get_rect(center=(cx, self.apply.rect.y - Space.md - 7)))
        for b in self.buttons:
            b.draw(surface)