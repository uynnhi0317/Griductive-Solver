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

import pygame

from game.board import Board
from game.cell import Cell
from game.public_state import PublicState
from .clue_panel import CluePanel
from .component import Component
from .stats_panel import StatsPanel
from .trace_panel import TracePanel
from .theme import Color, Radius, Size, Space, Stroke, render_text
from .widgets import TabBar

if TYPE_CHECKING:
    from engine.game_engine import VerdictResult

TAB_H = 36          # must match widgets.TAB_H
PAD = Space.sm


class Sidebar(Component):
    """
    Three-tab sidebar.  App creates one Sidebar per puzzle and calls:
      refresh(state, history)  — after every verdict / restart / load
    """

    _TAB_LABELS = ["Clues", "Trace", "Stats"]

    def __init__(self, state: PublicState,
                 history: tuple[VerdictResult, ...],
                 area: pygame.Rect,
                 on_select: Callable[[Cell], None] | None = None) -> None:
        self.area = pygame.Rect(area)
        self._on_select = on_select
        board = state.board

        self._tabbar = TabBar(self._TAB_LABELS, on_change=self._on_tab_change)
        self._active = 0

        content_rect = self._content_rect(area)
        self._clue_panel = CluePanel(state, content_rect, on_select=on_select)
        self._trace_panel = TracePanel(board, history, content_rect)
        self._stats_panel = StatsPanel(board, history, content_rect)

        self._panels: list[Component] = [
            self._clue_panel,
            self._trace_panel,
            self._stats_panel,
        ]
        self._fit_parts(area)

    # ---------------------------------------------------------------- proxy for CluePanel's selection attribute
    @property
    def selected(self) -> Cell | None:
        return self._clue_panel.selected

    @selected.setter
    def selected(self, cell: Cell | None) -> None:
        self._clue_panel.selected = cell

    @property
    def _rows(self):
        """Expose CluePanel._rows for backward-compatibility with existing tests."""
        return self._clue_panel._rows

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
        """Push new state and history to all three panels."""
        self._clue_panel.refresh(state)
        self._trace_panel.refresh(history)
        self._stats_panel.refresh(history)

    # --------------------------------------------------------------- events
    def _on_tab_change(self, index: int) -> None:
        self._active = index

    def handle_event(self, e: pygame.event.Event) -> bool:
        # TabBar always gets first look (tab clicks must be consumed)
        if self._tabbar.handle_event(e):
            return True
        # Delegate to active panel
        return self._panels[self._active].handle_event(e)

    # ------------------------------------------------------------------ draw
    def draw(self, surface: pygame.Surface) -> None:
        a = self.area
        # outer card background
        pygame.draw.rect(surface, Color.surface_1, a, border_radius=Radius.card)
        # tab bar (draws its own background)
        self._tabbar.draw(surface)
        # active panel
        self._panels[self._active].draw(surface)
