"""
Trace Panel — hiển thị lịch sử suy luận của phiên chơi hiện tại.

Mỗi kết quả phán định được chấp nhận sẽ được hiển thị dưới dạng một hàng
(bước N, tên nhân vật, kết quả phán định, số lượng truy vấn SAT).

Dữ liệu được lấy từ engine.history (danh sách VerdictResult), cũng chính là
nguồn dữ liệu mà agent sử dụng cho DeductionTrace.

Bảng này được thiết kế theo hướng tối giản: nó được kết xuất lại từ
engine.history mỗi khi phương thức refresh() được gọi, nhằm đảm bảo
nội dung luôn phản ánh trạng thái mới nhất.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pygame

from engine.game_engine import VerdictOutcome
from game.board import Board
from game.cell import Cell
from .component import Component
from .theme import (
    Color, Radius, Size, Space, Stroke, STATUS_COLOR,
    draw_rect_alpha, get_font, render_text, wrap_text,
)

if TYPE_CHECKING:
    from engine.game_engine import VerdictResult

PAD = Space.md
ROW_PAD = Space.sm
ROW_GAP = Space.xs
SCROLLBAR_W = 6
WHEEL_STEP = 48
STEP_DOT_R = 6


@dataclass
class _TraceRow:
    step: int            # 1-based step number (accepted verdicts only)
    label: str           # e.g. "A1  Alice  → Criminal  (2 SAT)"
    outcome_color: tuple # colour of the left accent stripe
    top: int = 0
    height: int = 0


class TracePanel(Component):
    """
    Scrollable list of accepted verdicts drawn from engine.history.
    Rejected attempts (NOT_PROVABLE / CONTRADICTED) are shown as small
    inline notes so the player can see what they tried.
    """

    def __init__(self, board: Board, history: tuple[VerdictResult, ...],
                 area: pygame.Rect) -> None:
        self._board = board
        self.area = pygame.Rect(area)
        self._rows: list[_TraceRow] = []
        self._content_h = 0
        self.scroll = 0
        self.refresh(history)

    # ---------------------------------------------------------------- layout
    def fit(self, area: pygame.Rect) -> None:
        self.area = pygame.Rect(area)
        self._layout()

    def _layout(self) -> None:
        font = get_font(Size.body)
        y = 0
        line_h = font.get_linesize() + 2 * ROW_PAD
        for row in self._rows:
            row.top = y
            row.height = line_h
            y += row.height + ROW_GAP
        self._content_h = max(0, y - ROW_GAP) if self._rows else 0
        self.scroll = max(0, min(self.scroll, self._max_scroll))

    @property
    def _viewport(self) -> pygame.Rect:
        a = self.area
        return pygame.Rect(a.x, a.y, a.w, a.h)

    @property
    def _max_scroll(self) -> int:
        return max(0, self._content_h - self._viewport.h)

    # --------------------------------------------------------------- update
    def refresh(self, history: tuple[VerdictResult, ...]) -> None:
        """Rebuild rows from the engine's history."""
        rows: list[_TraceRow] = []
        step = 0
        for r in history:
            char = self._board.character_at(r.cell)
            n = r.sat_queries
            q_text = f"{n} SAT {'query' if n == 1 else 'queries'}"

            if r.outcome is VerdictOutcome.ACCEPTED:
                step += 1
                label = (f"Step {step}  {char.name}  →  {r.submitted.value}"
                         f"  ({q_text})")
                color = STATUS_COLOR[r.submitted]
            elif r.outcome is VerdictOutcome.NOT_PROVABLE:
                label = f"  ✗ Not provable: {char.name} as {r.submitted.value}  ({q_text})"
                color = Color.fb_warn
            elif r.outcome is VerdictOutcome.CONTRADICTED:
                label = f"  ✗ Contradicted: {char.name} not {r.submitted.value}  ({q_text})"
                color = Color.fb_error
            else:  # INCONSISTENT
                label = f"  ✗ Inconsistent KB  ({q_text})"
                color = Color.fb_error
            rows.append(_TraceRow(step, label, color))

        grew = len(rows) > len(self._rows)
        self._rows = rows
        self._layout()
        if grew:
            self.scroll = self._max_scroll

    # --------------------------------------------------------------- events
    def handle_event(self, e: pygame.event.Event) -> bool:
        if e.type == pygame.MOUSEWHEEL:
            if self.area.collidepoint(pygame.mouse.get_pos()):
                self.scroll = max(0, min(self.scroll - e.y * WHEEL_STEP,
                                         self._max_scroll))
                return True
        return False

    # ------------------------------------------------------------------ draw
    def draw(self, surface: pygame.Surface) -> None:
        a = self.area
        vp = self._viewport
        old_clip = surface.get_clip()
        surface.set_clip(vp)

        if not self._rows:
            msg = render_text("No moves yet", Size.body, Color.text_dim)
            surface.blit(msg, msg.get_rect(center=vp.center))
        else:
            for row in self._rows:
                ry = vp.y + row.top - self.scroll
                if ry + row.height < vp.top or ry > vp.bottom:
                    continue
                self._draw_row(surface, row,
                               pygame.Rect(vp.x + PAD, ry,
                                           vp.w - 2 * PAD - SCROLLBAR_W,
                                           row.height))

        surface.set_clip(old_clip)
        self._draw_scrollbar(surface, vp)

    def _draw_row(self, surface: pygame.Surface, row: _TraceRow,
                  rect: pygame.Rect) -> None:
        STRIPE = 3
        pygame.draw.rect(surface, Color.surface_2, rect,
                         border_radius=Radius.control)
        # left accent stripe
        stripe_r = pygame.Rect(rect.x, rect.y, STRIPE, rect.h)
        pygame.draw.rect(surface, row.outcome_color, stripe_r,
                         border_top_left_radius=Radius.control,
                         border_bottom_left_radius=Radius.control)
        # label
        font = get_font(Size.body)
        max_w = rect.w - STRIPE - Space.sm - Space.xs
        txt_x = rect.x + STRIPE + Space.sm
        label = row.label
        if font.size(label)[0] > max_w:
            while label and font.size(label + "…")[0] > max_w:
                label = label[:-1]
            label = label.rstrip() + "…"
        txt = render_text(label, Size.body, Color.text)
        surface.blit(txt, txt.get_rect(midleft=(txt_x, rect.centery)))

    def _draw_scrollbar(self, surface: pygame.Surface,
                        vp: pygame.Rect) -> None:
        if self._max_scroll <= 0:
            return
        track_h = vp.h
        thumb_h = max(24, track_h * vp.h // self._content_h)
        thumb_y = vp.y + (track_h - thumb_h) * self.scroll // self._max_scroll
        thumb = pygame.Rect(vp.right - SCROLLBAR_W - Space.xs,
                            thumb_y, SCROLLBAR_W, thumb_h)
        draw_rect_alpha(surface, Color.scrollbar, thumb, Radius.small)
