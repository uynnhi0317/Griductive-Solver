"""
Stats Panel — thống kê hiệu suất của bộ giải (solver) trong phiên chơi hiện tại.

Tổng hợp dữ liệu SolverStats từ tất cả các mục VerdictResult trong engine.history
và hiển thị:
  • bảng thống kê theo từng kết quả phán định: bước N | kết quả | số lần gọi SAT | số quyết định | số phép lan truyền
  • hàng tổng kết các giá trị tích lũy
  • thông tin nội bộ của bộ giải: số quyết định, số phép lan truyền,
    số literal thuần, số lần quay lui và thời gian thực thi

Bảng này được thiết kế chỉ để đọc và không lưu trữ trạng thái riêng
(không cần cuộn đối với kích thước câu đố thông thường; thanh cuộn sẽ được
thêm vào nếu nội dung vượt quá không gian hiển thị).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from engine.game_engine import VerdictOutcome
from game.board import Board
from solver.stats import SolverStats
from .component import Component
from .theme import (
    Color, Radius, Size, Space, Stroke,
    draw_rect_alpha, get_font, render_text,
)

if TYPE_CHECKING:
    from engine.game_engine import VerdictResult

PAD = Space.md
ROW_H = 28
ROW_GAP = Space.xs
SCROLLBAR_W = 6
WHEEL_STEP = 48
SECTION_GAP = Space.lg

_COL_STEP = 44
_COL_WHO = 120
_COL_VERDICT = 80
_COL_SAT = 48
_COL_DEC = 56
_COL_PROP = 56


def _fmt(n: int | float, decimals: int = 0) -> str:
    if decimals:
        return f"{n:.{decimals}f}"
    return str(int(n))


class StatsPanel(Component):
    """
    Displays solver statistics aggregated from engine.history.
    Accepts a fresh history tuple on every refresh().
    """

    def __init__(self, board: Board,
                 history: tuple[VerdictResult, ...],
                 area: pygame.Rect) -> None:
        self._board = board
        self.area = pygame.Rect(area)
        self.scroll = 0
        self._content_h = 0
        self._rows: list[dict] = []          # pre-computed display rows
        self._totals: SolverStats = SolverStats()
        self._total_sat: int = 0
        self.refresh(history)

    # --------------------------------------------------------------- layout
    def fit(self, area: pygame.Rect) -> None:
        self.area = pygame.Rect(area)
        self._recalc_content_h()

    def _recalc_content_h(self) -> None:
        """Estimate total content height for scrollbar."""
        n = len(self._rows)
        # header + rows + totals row + gap + summary block
        self._content_h = (ROW_H          # column header
                           + n * (ROW_H + ROW_GAP)
                           + ROW_H        # totals
                           + SECTION_GAP
                           + 7 * (ROW_H + ROW_GAP))   # summary stats
        self.scroll = max(0, min(self.scroll, self._max_scroll))

    @property
    def _viewport(self) -> pygame.Rect:
        return pygame.Rect(self.area)

    @property
    def _max_scroll(self) -> int:
        return max(0, self._content_h - self._viewport.h)

    # --------------------------------------------------------------- update
    def refresh(self, history: tuple[VerdictResult, ...]) -> None:
        """Rebuild display rows from engine history."""
        rows = []
        totals = SolverStats()
        total_sat = 0
        step = 0
        for r in history:
            char = self._board.character_at(r.cell)
            accepted = r.outcome is VerdictOutcome.ACCEPTED
            if accepted:
                step += 1
            # aggregate stats from all SatQuerys in this verdict
            q_stats = SolverStats()
            for q in r.queries:
                q_stats.merge(q.stats)
            totals.merge(q_stats)
            total_sat += r.sat_queries
            rows.append({
                "step": step if accepted else "-",
                "who": char.name,
                "verdict": r.submitted.value,
                "accepted": accepted,
                "sat": r.sat_queries,
                "dec": q_stats.decisions,
                "prop": q_stats.propagations,
                "bt": q_stats.backtracks,
                "rt_ms": q_stats.runtime * 1000,
            })
        self._rows = rows
        self._totals = totals
        self._total_sat = total_sat
        self._recalc_content_h()

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
        vp = self._viewport
        old_clip = surface.get_clip()
        surface.set_clip(vp)

        y = vp.y - self.scroll
        x0 = vp.x + PAD
        content_w = vp.w - 2 * PAD - SCROLLBAR_W

        if not self._rows:
            surface.set_clip(old_clip)
            msg = render_text("No moves yet", Size.body, Color.text_dim)
            surface.blit(msg, msg.get_rect(center=vp.center))
            return

        # --- column header ---
        y = self._draw_header(surface, x0, content_w, y)

        # --- per-verdict rows ---
        for row in self._rows:
            if vp.y <= y + ROW_H and y < vp.bottom:
                y = self._draw_row(surface, row, x0, content_w, y)
            else:
                y += ROW_H + ROW_GAP

        # --- totals ---
        y = self._draw_totals(surface, x0, content_w, y)

        # --- summary block ---
        y += SECTION_GAP
        y = self._draw_summary(surface, x0, content_w, y, vp)

        surface.set_clip(old_clip)
        self._draw_scrollbar(surface, vp)

    # ---------------------------------------------------------------- helpers
    def _cols(self, x0: int, w: int) -> list[tuple[str, int, str]]:
        """(label, x, align) for each column given the available width."""
        # fixed columns then stretch 'who'
        fixed = _COL_STEP + _COL_VERDICT + _COL_SAT + _COL_DEC + _COL_PROP
        who_w = max(60, w - fixed)
        cols = [
            ("#",        x0,                               "r"),
            ("Character",x0 + _COL_STEP,                  "l"),
            ("Verdict",  x0 + _COL_STEP + who_w,          "l"),
            ("SAT",      x0 + _COL_STEP + who_w + _COL_VERDICT, "r"),
            ("Dec",      x0 + _COL_STEP + who_w + _COL_VERDICT + _COL_SAT, "r"),
            ("Prop",     x0 + _COL_STEP + who_w + _COL_VERDICT + _COL_SAT + _COL_DEC, "r"),
        ]
        return cols

    def _draw_header(self, surface, x0, w, y) -> int:
        cols = self._cols(x0, w)
        font = get_font(Size.caption, True)
        for label, cx, align in cols:
            txt = font.render(label, True, Color.text_dim)
            if align == "r":
                surface.blit(txt, txt.get_rect(midright=(cx + _COL_STEP - Space.sm, y + ROW_H // 2)))
            else:
                surface.blit(txt, txt.get_rect(midleft=(cx, y + ROW_H // 2)))
        # divider
        pygame.draw.line(surface, Color.border,
                         (x0, y + ROW_H - 1),
                         (x0 + w, y + ROW_H - 1))
        return y + ROW_H

    def _draw_row(self, surface, row: dict, x0: int, w: int, y: int) -> int:
        # row bg
        rect = pygame.Rect(x0, y, w, ROW_H)
        bg = Color.surface_2 if row["accepted"] else Color.surface_1
        pygame.draw.rect(surface, bg, rect, border_radius=Radius.control)
        if not row["accepted"]:
            # dim text for rejected verdicts
            pass

        cols = self._cols(x0, w)
        values = [
            str(row["step"]),
            row["who"],
            row["verdict"],
            str(row["sat"]),
            str(row["dec"]),
            str(row["prop"]),
        ]
        color = Color.text if row["accepted"] else Color.text_dim
        font = get_font(Size.body)
        for (label, cx, align), val in zip(cols, values):
            txt = font.render(val, True, color)
            if align == "r":
                surface.blit(txt, txt.get_rect(midright=(cx + _COL_STEP - Space.sm, y + ROW_H // 2)))
            else:
                surface.blit(txt, txt.get_rect(midleft=(cx, y + ROW_H // 2)))
        return y + ROW_H + ROW_GAP

    def _draw_totals(self, surface, x0, w, y) -> int:
        # divider above totals
        pygame.draw.line(surface, Color.border,
                         (x0, y), (x0 + w, y))
        y += ROW_GAP
        rect = pygame.Rect(x0, y, w, ROW_H)
        pygame.draw.rect(surface, Color.surface_3, rect, border_radius=Radius.control)

        cols = self._cols(x0, w)
        t = self._totals
        values = [
            "Σ",
            "",
            "",
            str(self._total_sat),
            str(t.decisions),
            str(t.propagations),
        ]
        font = get_font(Size.body, True)
        for (label, cx, align), val in zip(cols, values):
            if not val:
                continue
            txt = font.render(val, True, Color.text)
            if align == "r":
                surface.blit(txt, txt.get_rect(midright=(cx + _COL_STEP - Space.sm, y + ROW_H // 2)))
            else:
                surface.blit(txt, txt.get_rect(midleft=(cx, y + ROW_H // 2)))
        return y + ROW_H

    def _draw_summary(self, surface, x0, w, y, vp) -> int:
        """Render the cumulative solver stats block."""
        t = self._totals
        lines = [
            ("SAT queries (total)",     str(self._total_sat)),
            ("Decisions",               str(t.decisions)),
            ("Propagations",            str(t.propagations)),
            ("Pure literals",           str(t.pure_literals)),
            ("Backtracks",              str(t.backtracks)),
            ("Runtime",                 f"{t.runtime * 1000:.3f} ms"),
        ]
        label_font = get_font(Size.body)
        value_font = get_font(Size.body, True)
        for label, value in lines:
            if vp.y <= y + ROW_H and y < vp.bottom:
                ltxt = label_font.render(label, True, Color.text_dim)
                vtxt = value_font.render(value, True, Color.text)
                surface.blit(ltxt, ltxt.get_rect(midleft=(x0, y + ROW_H // 2)))
                surface.blit(vtxt, vtxt.get_rect(midright=(x0 + w, y + ROW_H // 2)))
            y += ROW_H + ROW_GAP
        return y

    def _draw_scrollbar(self, surface, vp):
        if self._max_scroll <= 0:
            return
        track_h = vp.h
        thumb_h = max(24, track_h * vp.h // max(1, self._content_h))
        thumb_y = vp.y + (track_h - thumb_h) * self.scroll // self._max_scroll
        thumb = pygame.Rect(vp.right - SCROLLBAR_W - Space.xs,
                            thumb_y, SCROLLBAR_W, thumb_h)
        draw_rect_alpha(surface, Color.scrollbar, thumb, Radius.small)
