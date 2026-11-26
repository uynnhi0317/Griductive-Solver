"""
Sidebar — bảng điều khiển bên phải với ba thẻ: Clues | Trace | Stats.

  Clues   — CluePanel hiện có (các manh mối đã được tiết lộ + chú giải)
  Trace   — TracePanel (các kết quả phán định được chấp nhận/từ chối từ engine.history)
  Stats   — StatsPanel (thống kê SolverStats tổng hợp, bảng phân loại theo từng kết quả)

Cơ chế đăng ký thẻ mới cho phép bổ sung thêm các thẻ trong tương lai mà
không cần chỉnh sửa app.py:
chỉ cần thêm một cặp (label, panel_factory) vào danh sách _TABS tại đây.

Sidebar quản lý TabBar và ủy quyền các phương thức fit / handle_event / draw
cho bảng nội dung đang hoạt động. refresh() chuyển tiếp dữ liệu mới đến tất cả
các bảng để đảm bảo chúng luôn được cập nhật khi người dùng chuyển đổi giữa các thẻ.
"""

from __future__ import annotations

from typing import Callable, TYPE_CHECKING
from dataclasses import dataclass

import pygame

from game.board import Board
from game.cell import Cell
from game.public_state import PublicState
from .clue_panel import CluePanel
from .component import Component
from .stats_panel import StatsPanel
from .trace_panel import TracePanel
from .theme import Color, Radius, Size, Space, Stroke, render_text
from .widgets import TabBar, TAB_H

if TYPE_CHECKING:
    from engine.game_engine import VerdictResult


PAD = Space.sm

@dataclass(frozen=True)
class TabContext:
    """Toàn bộ dữ liệu cần thiết để khởi tạo mọi bảng giao diện."""
    state: PublicState
    history: tuple[VerdictResult, ...]
    area: pygame.Rect
    on_select: Callable[[Cell], None] | None = None


@dataclass(frozen=True)
class TabSpec:
    label: str
    build: Callable[[TabContext], Component]
    refresh: Callable[[Component, PublicState, tuple[VerdictResult, ...]], None]

# Để thêm tab: thêm 1 TabSpec ở đây. Không file nào khác (kể cả app.py) thay đổi.
_TABS: list[TabSpec] = [
    TabSpec("Clues",
            build=lambda c: CluePanel(c.state, c.area, on_select=c.on_select),
            refresh=lambda p, state, history: p.refresh(state)),
    TabSpec("Trace",
            build=lambda c: TracePanel(c.state.board, c.history, c.area),
            refresh=lambda p, state, history: p.refresh(history)),
    TabSpec("Stats",
            build=lambda c: StatsPanel(c.state.board, c.history, c.area),
            refresh=lambda p, state, history: p.refresh(history)),
]

class Sidebar(Component):
    """
    Thanh bên gồm ba thẻ. App khởi tạo một Sidebar cho mỗi câu đố và gọi:
    refresh(state, history)  — sau mỗi lần verdict / restart / load
    """

    _TAB_LABELS = ["Clues", "Trace", "Stats"]

    def __init__(self, state: PublicState,
                 history: tuple[VerdictResult, ...],
                 area: pygame.Rect,
                 on_select: Callable[[Cell], None] | None = None) -> None:
        self.area = pygame.Rect(area)

        self._tabbar = TabBar([t.label for t in _TABS], on_change=self._on_tab_change)
        self._active = 0

        ctx = TabContext(state, history, self._content_rect(area), on_select)
        self._panels: list[Component] = [t.build(ctx) for t in _TABS]
        self._fit_parts(area)

    #------------------------------------------------------------- tìm panel theo tên (định nghĩa trong _TABS)
    def panel(self, label: str) -> Component:
        """Lookup by label, replacing the named attributes like self._clue_panel."""
        return self._panels[[t.label for t in _TABS].index(label)]

    # ---------------------------------------------------------------- trung gian đại diện cho thuộc tính selected của CluePanel
    @property
    def selected(self) -> Cell | None:
        return self.panel("Clues").selected

    @selected.setter
    def selected(self, cell: Cell | None) -> None:
        self.panel("Clues").selected = cell

    # --------------------------------------------------------------- layout
    def _content_rect(self, area: pygame.Rect) -> pygame.Rect:
        return pygame.Rect(area.x, area.y + TAB_H + PAD,
                           area.w, area.h - TAB_H - PAD)

    def _fit_parts(self, area: pygame.Rect) -> None:
        tab_rect = pygame.Rect(area.x, area.y, area.w, TAB_H)
        content_rect = self._content_rect(area)
        self._tabbar.fit(tab_rect)
        for panel in self._panels:
            panel.fit(content_rect)

    def fit(self, area: pygame.Rect) -> None:
        self.area = pygame.Rect(area)
        self._fit_parts(area)

    # --------------------------------------------------------------- update
    def refresh(self, state: PublicState,
                history: tuple[VerdictResult, ...]) -> None:
        for spec, panel in zip(_TABS, self._panels):
                spec.refresh(panel, state, history)

    # --------------------------------------------------------------- events
    def _on_tab_change(self, index: int) -> None:
        self._active = index

    def handle_event(self, e: pygame.event.Event) -> bool:
        # TabBar luôn được ưu tiên xử lý trước
        if self._tabbar.handle_event(e):
            return True
        # chuyển tiếp sự kiện đến panel đang hoạt động
        return self._panels[self._active].handle_event(e)

    # ------------------------------------------------------------------ draw
    def draw(self, surface: pygame.Surface) -> None:
        a = self.area
        # nền ngoài thẻ
        pygame.draw.rect(surface, Color.surface_1, a, border_radius=Radius.card)
        # tab bar (tự vẽ nền)
        self._tabbar.draw(surface)
        # panel đang hoạt động
        self._panels[self._active].draw(surface)
