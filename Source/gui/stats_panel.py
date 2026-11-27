"""
Stats Panel — thống kê hiệu suất của bộ giải trong phiên chơi hiện tại.

Dữ liệu lấy từ LogSnapshot (engine.history + các bước của agent):
  • bảng theo từng verdict: bước | nhân vật | verdict | SAT | quyết định | phép lan truyền
    SAT / Dec / Prop = truy vấn của ENGINE + truy vấn của AGENT (nếu verdict do agent nộp)
  • dòng "Agent final check" nếu agent dừng sau một lần phân loại không dẫn tới verdict
  • hàng tổng kết và khối thống kê (tách SAT của engine và của agent)

Dòng của agent có vạch xanh bên trái. Panel chỉ đọc, dựng lại mỗi lần refresh().
"""

from __future__ import annotations

import pygame

from game.board import Board
from .action_log import Actor, LogSnapshot
from .component import Component
from .theme import (
    Color, Radius, Size, Space, SCROLLBAR_W,
    ellipsize, get_font, render_text, draw_scrollbar
)

PAD = Space.md
ROW_H = 28
ROW_GAP = Space.xs
WHEEL_STEP = 48
SECTION_GAP = Space.lg
STRIPE_W = 3

_COL_STEP = 44
_COL_VERDICT = 88
_COL_SAT = 48
_COL_DEC = 56
_COL_PROP = 56


class StatsPanel(Component):
    def __init__(self, board: Board, snap: LogSnapshot, area: pygame.Rect) -> None:
        self._board = board
        self.area = pygame.Rect(area)
        self.scroll = 0
        self._content_h = 0
        self._rows: list[dict] = []
        self._totals_row: dict = {}
        self._summary: list[tuple[str, str]] = []
        self.refresh(snap)

    # --------------------------------------------------------------- layout
    def fit(self, area: pygame.Rect) -> None:
        self.area = pygame.Rect(area)
        self._recalc_content_h()

    def _recalc_content_h(self) -> None:
        n = len(self._rows)
        self._content_h = (ROW_H
                           + n * (ROW_H + ROW_GAP)
                           + ROW_H + ROW_GAP          # totals
                           + SECTION_GAP
                           + (len(self._summary) + 1) * (ROW_H + ROW_GAP))   # summary + legend
        self.scroll = max(0, min(self.scroll, self._max_scroll))

    @property
    def _viewport(self) -> pygame.Rect:
        return pygame.Rect(self.area)

    @property
    def _max_scroll(self) -> int:
        return max(0, self._content_h - self._viewport.h)

    # --------------------------------------------------------------- update
    def refresh(self, snap: LogSnapshot) -> None:
        rows = []
        step = 0
        for e in snap.entries:
            if e.accepted:
                step += 1
            st = e.stats()
            rows.append({
                "step": step if e.accepted else "-",
                "who": self._board.character_at(e.result.cell).name,
                "verdict": e.result.submitted.value,
                "accepted": e.accepted,
                "agent": e.actor is Actor.AGENT,
                "sat": e.sat_queries,
                "dec": st.decisions,
                "prop": st.propagations,
            })

        end = snap.end
        if end is not None and end.queries:
            rows.append({
                "step": "-", "who": "Agent final check", "verdict": end.status.value,
                "accepted": False, "agent": True, "sat": end.queries,
                "dec": end.stats.decisions, "prop": end.stats.propagations,
            })

        t = snap.stats()
        self._rows = rows
        self._totals_row = {"sat": snap.total_sat, "dec": t.decisions, "prop": t.propagations}
        self._summary = [
            ("SAT queries (total)", str(snap.total_sat)),
            ("  by engine", str(snap.engine_sat)),
            ("  by agent", str(snap.agent_sat)),
            ("Decisions", str(t.decisions)),
            ("Propagations", str(t.propagations)),
            ("Pure literals", str(t.pure_literals)),
            ("Backtracks", str(t.backtracks)),
            ("Runtime", f"{t.runtime * 1000:.3f} ms"),
        ]
        self._recalc_content_h()

    # --------------------------------------------------------------- events
    def handle_event(self, e: pygame.event.Event) -> bool:
        if e.type == pygame.MOUSEWHEEL:
            if self.area.collidepoint(pygame.mouse.get_pos()):
                self.scroll = max(0, min(self.scroll - e.y * WHEEL_STEP, self._max_scroll))
                return True
        return False

    # ------------------------------------------------------------------ draw
    def draw(self, surface: pygame.Surface) -> None:
        vp = self._viewport
        if not self._rows:
            msg = render_text("No moves yet", Size.body, Color.text_dim)
            surface.blit(msg, msg.get_rect(center=vp.center))
            return

        old_clip = surface.get_clip()
        surface.set_clip(vp)

        y = vp.y - self.scroll
        x0 = vp.x + PAD
        content_w = vp.w - 2 * PAD - SCROLLBAR_W

        y = self._draw_header(surface, x0, content_w, y)
        for row in self._rows:
            if vp.y <= y + ROW_H and y < vp.bottom:
                y = self._draw_row(surface, row, x0, content_w, y)
            else:
                y += ROW_H + ROW_GAP

        y = self._draw_totals(surface, x0, content_w, y)
        y += SECTION_GAP
        self._draw_summary(surface, x0, content_w, y, vp)

        surface.set_clip(old_clip)
        draw_scrollbar(surface, vp, self._content_h, self.scroll, self._max_scroll)

    # ---------------------------------------------------------------- helpers
    def _cols(self, x0: int, w: int) -> list[tuple[str, int, str, int]]:
        """(nhãn, x, căn lề, bề rộng tối đa của chữ) cho từng cột"""
        fixed = _COL_STEP + _COL_VERDICT + _COL_SAT + _COL_DEC + _COL_PROP
        who_w = max(60, w - fixed)
        xs = [x0,
              x0 + _COL_STEP,
              x0 + _COL_STEP + who_w,
              x0 + _COL_STEP + who_w + _COL_VERDICT,
              x0 + _COL_STEP + who_w + _COL_VERDICT + _COL_SAT,
              x0 + _COL_STEP + who_w + _COL_VERDICT + _COL_SAT + _COL_DEC]
        return [
            ("#", xs[0], "r", _COL_STEP),
            ("Character", xs[1], "l", who_w - Space.sm),
            ("Verdict", xs[2], "l", _COL_VERDICT - Space.sm),
            ("SAT", xs[3], "r", _COL_SAT),
            ("Dec", xs[4], "r", _COL_DEC),
            ("Prop", xs[5], "r", _COL_PROP),
        ]

    def _blit_cell(self, surface, font, text, color, cx, align, max_w, y) -> None:
        txt = font.render(ellipsize(text, font, max_w), True, color)
        if align == "r":
            surface.blit(txt, txt.get_rect(midright=(cx + _COL_STEP - Space.sm, y + ROW_H // 2)))
        else:
            surface.blit(txt, txt.get_rect(midleft=(cx, y + ROW_H // 2)))

    def _draw_header(self, surface, x0, w, y) -> int:
        font = get_font(Size.caption, True)
        for label, cx, align, max_w in self._cols(x0, w):
            self._blit_cell(surface, font, label, Color.text_dim, cx, align, max_w, y)
        pygame.draw.line(surface, Color.border, (x0, y + ROW_H - 1), (x0 + w, y + ROW_H - 1))
        return y + ROW_H

    def _draw_row(self, surface, row: dict, x0: int, w: int, y: int) -> int:
        rect = pygame.Rect(x0, y, w, ROW_H)
        pygame.draw.rect(surface, Color.surface_2 if row["accepted"] else Color.surface_1,
                         rect, border_radius=Radius.control)
        if row["agent"]:
            pygame.draw.rect(surface, Color.fb_info, pygame.Rect(rect.x, rect.y, STRIPE_W, rect.h),
                             border_top_left_radius=Radius.control,
                             border_bottom_left_radius=Radius.control)

        values = [str(row["step"]), row["who"], row["verdict"],
                  str(row["sat"]), str(row["dec"]), str(row["prop"])]
        color = Color.text if row["accepted"] else Color.text_dim
        font = get_font(Size.body)
        for (_, cx, align, max_w), val in zip(self._cols(x0, w), values):
            self._blit_cell(surface, font, val, color, cx, align, max_w, y)
        return y + ROW_H + ROW_GAP

    def _draw_totals(self, surface, x0, w, y) -> int:
        pygame.draw.line(surface, Color.border, (x0, y), (x0 + w, y))
        y += ROW_GAP
        pygame.draw.rect(surface, Color.surface_3, pygame.Rect(x0, y, w, ROW_H),
                         border_radius=Radius.control)
        t = self._totals_row
        values = ["Σ", "", "", str(t["sat"]), str(t["dec"]), str(t["prop"])]
        font = get_font(Size.body, True)
        for (_, cx, align, max_w), val in zip(self._cols(x0, w), values):
            if val:
                self._blit_cell(surface, font, val, Color.text, cx, align, max_w, y)
        return y + ROW_H

    def _draw_summary(self, surface, x0, w, y, vp) -> int:
        label_font = get_font(Size.body)
        value_font = get_font(Size.body, True)
        for label, value in self._summary:
            if vp.y <= y + ROW_H and y < vp.bottom:
                ltxt = label_font.render(label, True, Color.text_dim)
                vtxt = value_font.render(value, True, Color.text)
                surface.blit(ltxt, ltxt.get_rect(midleft=(x0, y + ROW_H // 2)))
                surface.blit(vtxt, vtxt.get_rect(midright=(x0 + w, y + ROW_H // 2)))
            y += ROW_H + ROW_GAP

        if vp.y <= y + ROW_H and y < vp.bottom:
            pygame.draw.rect(surface, Color.fb_info, pygame.Rect(x0, y + ROW_H // 2 - 6, STRIPE_W, 12))
            note = render_text("Agent step (SAT = agent + engine)", Size.caption, Color.text_dim)
            surface.blit(note, note.get_rect(midleft=(x0 + STRIPE_W + Space.sm, y + ROW_H // 2)))
        return y + ROW_H + ROW_GAP