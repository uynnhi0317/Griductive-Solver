"""Thanh trên (tên màn, chuyển màn, tiến độ) và thanh trạng thái (thông báo cho người chơi)"""

from typing import Callable

import pygame

from game.character import Status
from .component import Component
from .theme import Color, LEVEL_COLOR, Level, Size, Space, ellipsize, get_font, render_text
from .widgets import Button, place_buttons

NAV_W, NAV_H = 32, 28


class TopBar(Component):
    def __init__(self, rect: pygame.Rect, on_prev, on_next):
        self.rect = pygame.Rect(rect)
        self.title = ""
        self.stage_text = ""
        self.progress_text = ""
        self.prev = Button("<", on_prev)
        self.next = Button(">", on_next)
        self._title_max_w = 0
        self._stage_x = self._progress_x = 0
        self._layout()

    @property
    def buttons(self) -> tuple[Button, Button]:
        return self.prev, self.next

    def fit(self, rect: pygame.Rect) -> None:
        self.rect = pygame.Rect(rect)
        self._layout()

    def handle_event(self, e: pygame.event.Event) -> bool:
        return any(b.handle_event(e) for b in self.buttons)

    def set_info(self, title: str, stage_text: str, progress_text: str) -> None:
        self.title, self.stage_text, self.progress_text = title, stage_text, progress_text
        self._layout()

    def _layout(self) -> None:
        r, m = self.rect, Space.lg
        self.next.rect = pygame.Rect(r.right - m - NAV_W, r.centery - NAV_H // 2, NAV_W, NAV_H)
        stage_w = render_text(self.stage_text, Size.body, Color.text_dim).get_width()
        self._stage_x = self.next.rect.x - Space.sm - stage_w
        self.prev.rect = pygame.Rect(self._stage_x - Space.sm - NAV_W, self.next.rect.y, NAV_W, NAV_H)
        progress_w = render_text(self.progress_text, Size.body, Color.text_dim).get_width()
        self._progress_x = self.prev.rect.x - Space.xl - progress_w
        self._title_max_w = max(0, self._progress_x - Space.xl - (r.x + m))

    def draw(self, surface: pygame.Surface) -> None:
        r = self.rect
        pygame.draw.rect(surface, Color.surface_1, r)
        pygame.draw.line(surface, Color.border, r.bottomleft, r.bottomright)

        title = ellipsize(self.title, get_font(Size.h2, True), self._title_max_w)
        t = render_text(title, Size.h2, Color.text, True)
        surface.blit(t, t.get_rect(midleft=(r.x + Space.lg, r.centery)))

        for text, x in ((self.progress_text, self._progress_x), (self.stage_text, self._stage_x)):
            s = render_text(text, Size.body, Color.text_dim)
            surface.blit(s, s.get_rect(midleft=(x, r.centery)))
        self.prev.draw(surface)
        self.next.draw(surface)


class StatusBar(Component):
    DOT_R = 5

    def __init__(self, rect: pygame.Rect):
        self.rect = pygame.Rect(rect)
        self.message = ""
        self.level = Level.INFO

    def fit(self, rect: pygame.Rect) -> None:
        self.rect = pygame.Rect(rect)

    def say(self, message: str, level: Level = Level.INFO) -> None:
        self.message, self.level = message, level

    def draw(self, surface: pygame.Surface) -> None:
        r = self.rect
        pygame.draw.rect(surface, Color.surface_1, r)
        pygame.draw.line(surface, Color.border, r.topleft, r.topright)
        cx, cy = r.x + Space.lg + self.DOT_R, r.centery
        pygame.draw.circle(surface, LEVEL_COLOR[self.level], (cx, cy), self.DOT_R)
        x = cx + self.DOT_R + Space.sm
        text = ellipsize(self.message, get_font(Size.body), r.right - Space.lg - x)
        s = render_text(text, Size.body, Color.text)
        surface.blit(s, s.get_rect(midleft=(x, cy)))


class ActionBar(Component):
    """Hàng nút dưới bàn cờ: phán quyết (trái), Hint / Auto Solve / Restart / Load (phải)"""

    def __init__(self, on_verdict: Callable[[Status], None], on_verdict_blocked: Callable[[], None],
                 on_hint, on_auto_solve, on_restart, on_load):
        self.rect = pygame.Rect(0, 0, 0, 0)
        self.criminal = Button("Criminal", lambda: on_verdict(Status.CRIMINAL), Status.CRIMINAL,
                               on_disabled_click=on_verdict_blocked)
        self.innocent = Button("Innocent", lambda: on_verdict(Status.INNOCENT), Status.INNOCENT,
                               on_disabled_click=on_verdict_blocked)
        self._left = [self.criminal, self.innocent]
        self._right = [Button("Hint", on_hint), Button("Auto Solve", on_auto_solve),
                       Button("Restart", on_restart), Button("Load", on_load)]

    def set_verdict_enabled(self, enabled: bool) -> None:
        self.criminal.enabled = self.innocent.enabled = enabled

    def fit(self, rect: pygame.Rect) -> None:
        self.rect = pygame.Rect(rect)
        place_buttons(self.rect, self._left, self._right)

    def handle_event(self, e: pygame.event.Event) -> bool:
        return any(b.handle_event(e) for b in self._left + self._right)

    def draw(self, surface: pygame.Surface) -> None:
        for b in self._left + self._right:
            b.draw(surface)