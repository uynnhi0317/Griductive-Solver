"""
History Panel — lịch sử hành động của phiên chơi (người chơi và Agent).

Nửa trên: danh sách các verdict đã nộp (kể cả bị từ chối), mỗi dòng gắn nhãn You / Agent,
  cộng một dòng "Agent finished" khi agent dừng.
Nửa dưới: ô log chi tiết của dòng đang chọn (mặc định dòng mới nhất, bấm dòng khác để xem;
  bấm lại dòng đang chọn để quay về dòng mới nhất).
  + Dòng của agent: TraceStep.describe, các trường deduction trace (clue đang dùng, SAT agent / engine,
    ô bị ép buộc, ô còn UNKNOWN, clue mới lộ, số liệu solver)
  + Dòng của người chơi: verdict, kết quả, phân loại của engine, số engine checks, clue mới lộ
  + Dòng kết thúc: SOLVED / AMBIGUOUS (kèm ô UNKNOWN) / INCONSISTENT / TIMEOUT

Panel chỉ đọc LogSnapshot, dựng lại mỗi lần refresh().
"""

from __future__ import annotations

from dataclasses import dataclass

import pygame

from agent.trace import AgentStatus
from engine.game_engine import VerdictOutcome
from game.board import Board
from game.cell import Cell
from .action_log import Actor, HistoryEntry, LogSnapshot, AgentEnd
from .component import Component
from .theme import (
    Color, Radius, Size, Space, Stroke, STATUS_COLOR, SCROLLBAR_W,
    ellipsize, get_font, render_text, wrap_text, draw_scrollbar
)

PAD = Space.md
ROW_PAD = Space.sm
ROW_GAP = Space.xs
WHEEL_STEP = 48
STRIPE = 3
LIST_FRAC = 0.5
MIN_LIST = 96
MIN_DETAIL = 120
PANE_GAP = Space.sm
HINT_H = 20

_OUTCOME_NOTE = {
    VerdictOutcome.ACCEPTED: "the verdict is forced by the revealed clues",
    VerdictOutcome.NOT_PROVABLE: "neither status is forced yet",
    VerdictOutcome.CONTRADICTED: "the opposite status is forced",
    VerdictOutcome.INCONSISTENT: "the revealed clues contradict each other",
}


@dataclass
class _Item:
    label: str
    color: tuple
    details: list[str]       # details[0] là tiêu đề (in đậm), phần còn lại là các dòng nội dung
    top: int = 0
    height: int = 0


def _who(board: Board, cell: Cell) -> str:
    return f"{board.character_at(cell).name} ({cell.label})"


def _who_list(board: Board, labels: tuple[str, ...]) -> str:
    return ", ".join(_who(board, Cell.parse(lb)) for lb in labels) or "-"


class HistoryPanel(Component):
    def __init__(self, board: Board, snap: LogSnapshot, area: pygame.Rect) -> None:
        self._board = board
        self.area = pygame.Rect(area)
        self._items: list[_Item] = []
        self._content_h = 0
        self.scroll = 0
        self.selected: int | None = None     # None = dòng mới nhất
        self._detail_scroll = 0
        self._wrapped: list[tuple[str, bool]] | None = None
        self._list = pygame.Rect(0, 0, 0, 0)
        self._detail = pygame.Rect(0, 0, 0, 0)
        self._hint = pygame.Rect(0, 0, 0, 0)
        self._layout_rects()
        self.refresh(snap)

    # --------------------------------------------------------------- layout
    def _layout_rects(self) -> None:
        a = self.area
        list_h = int(a.h * LIST_FRAC)
        list_h = min(list_h, max(MIN_LIST, a.h - MIN_DETAIL - PANE_GAP - HINT_H))
        list_h = max(MIN_LIST, list_h)
        list_h = min(list_h, a.h)
        self._list = pygame.Rect(a.x, a.y, a.w, list_h)
        self._hint = pygame.Rect(a.x + PAD, a.y + list_h + PANE_GAP, max(0, a.w - 2 * PAD), HINT_H)
        top = self._hint.bottom
        self._detail = pygame.Rect(a.x + PAD, top, max(0, a.w - 2 * PAD), max(0, a.bottom - top))

    def fit(self, area: pygame.Rect) -> None:
        self.area = pygame.Rect(area)
        self._layout_rects()
        self._layout()
        self._wrapped = None

    def _layout(self) -> None:
        line_h = get_font(Size.body).get_linesize() + 2 * ROW_PAD
        y = 0
        for item in self._items:
            item.top, item.height = y, line_h
            y += line_h + ROW_GAP
        self._content_h = max(0, y - ROW_GAP) if self._items else 0
        self.scroll = max(0, min(self.scroll, self._max_scroll))

    @property
    def _max_scroll(self) -> int:
        return max(0, self._content_h - self._list.h)

    @property
    def _current(self) -> int | None:
        if not self._items:
            return None
        if self.selected is None:
            return len(self._items) - 1
        return min(self.selected, len(self._items) - 1)

    # --------------------------------------------------------------- update
    def refresh(self, snap: LogSnapshot) -> None:
        items: list[_Item] = []
        step = 0
        for e in snap.entries:
            if e.accepted:
                step += 1
            items.append(self._entry_item(e, step))
        if snap.end is not None:
            items.append(self._end_item(snap.end))

        grew = len(items) != len(self._items)
        self._items = items
        if grew:
            self.selected = None
            self._detail_scroll = 0
        self._wrapped = None
        self._layout()
        if grew:
            self.scroll = self._max_scroll

    def _entry_item(self, e: HistoryEntry, step: int) -> _Item:
        r = e.result
        board = self._board
        name = board.character_at(r.cell).name
        tag = e.actor.value
        q = f"{e.sat_queries} SAT"
        if r.outcome is VerdictOutcome.ACCEPTED:
            label = f"{tag}  Step {step}  {name}  →  {r.submitted.value}  ({q})"
            color = STATUS_COLOR[r.submitted]
        elif r.outcome is VerdictOutcome.NOT_PROVABLE:
            label = f"{tag}  ✗ Not provable: {name} as {r.submitted.value}  ({q})"
            color = Color.fb_warn
        elif r.outcome is VerdictOutcome.CONTRADICTED:
            label = f"{tag}  ✗ Contradicted: {name} not {r.submitted.value}  ({q})"
            color = Color.fb_error
        else:
            label = f"{tag}  ✗ Inconsistent KB  ({q})"
            color = Color.fb_error
        return _Item(label, color, self._entry_details(e))

    def _entry_details(self, e: HistoryEntry) -> list[str]:
        board, r, s = self._board, e.result, e.step
        who = _who(board, r.cell)
        lines: list[str] = []

        if s is not None:
            lines.append(s.describe(board))
            lines.append(f"Agent step {s.step} (history #{e.index + 1})")
            lines.append(f"Active clues ({len(s.active_clue_ids)}): {_who_list(board, s.active_clue_ids)}")
            lines.append(f"Verdict: {who} is {s.verdict.value} [{r.outcome.value}]")
            lines.append(f"SAT queries: agent {s.sat_queries} (skipped {s.skipped_queries}) "
                         f"+ engine {s.engine_queries} = {e.sat_queries}")
            lines.append(f"Forced cells: {_who_list(board, s.forced_cells)}")
            lines.append(f"Unknown cells: {_who_list(board, s.unknown_cells)}")
        else:
            lines.append(f"You called {who} {r.submitted.value}")
            lines.append(f"Outcome: {r.outcome.value} ({_OUTCOME_NOTE[r.outcome]})")
            lines.append(f"Engine classification: {r.classification.verdict.value}")
            n = r.sat_queries
            lines.append(f"Engine checks: {n} SAT {'query' if n == 1 else 'queries'}")

        rev = r.revealed
        if rev is not None:
            lines.append(f"Revealed clue of {_who(board, rev.cell)}: {rev.clue.describe(board)}")
        if s is not None:
            lines.append(f"Solver (agent): {s.stats}")
        return lines

    def _end_item(self, end: AgentEnd) -> _Item:
        board = self._board
        st = end.status
        color = (Color.fb_ok if st is AgentStatus.SOLVED
                 else Color.fb_warn if st is AgentStatus.AMBIGUOUS else Color.fb_error)
        lines = [f"Agent finished: {st.value}"]
        if st is AgentStatus.SOLVED:
            lines.append("Every card has a verdict.")
        elif st is AgentStatus.AMBIGUOUS:
            lines.append(f"Still UNKNOWN ({len(end.unknown)}): {_who_list(board, end.unknown)}")
            lines.append("No card is forced by the revealed clues, so the agent does not guess.")
        elif st is AgentStatus.INCONSISTENT:
            lines.append("The revealed clues contradict each other (puzzle or encoder bug).")
        elif st is AgentStatus.TIMEOUT:
            lines.append("A SAT query exceeded the time limit.")
        if end.queries:
            lines.append(f"Final classification: {end.queries} SAT queries; {end.stats}")
        return _Item(f"Agent finished: {st.value}", color, lines)

    # --------------------------------------------------------------- events
    def _row_rect(self, item: _Item) -> pygame.Rect:
        vp = self._list
        return pygame.Rect(vp.x + PAD, vp.y + item.top - self.scroll,
                           vp.w - 2 * PAD - SCROLLBAR_W, item.height)

    def _row_at(self, pos) -> int | None:
        if not self._list.collidepoint(pos):
            return None
        for i, item in enumerate(self._items):
            if self._row_rect(item).collidepoint(pos):
                return i
        return None

    def _detail_max_scroll(self) -> int:
        lh = get_font(Size.body).get_linesize()
        return max(0, len(self._detail_lines()) * lh - max(0, self._detail.h - 2 * PAD))

    def handle_event(self, e: pygame.event.Event) -> bool:
        if e.type == pygame.MOUSEWHEEL:
            pos = pygame.mouse.get_pos()
            if self._list.collidepoint(pos):
                self.scroll = max(0, min(self.scroll - e.y * WHEEL_STEP, self._max_scroll))
                return True
            if self._detail.collidepoint(pos):
                self._detail_scroll = max(0, min(self._detail_scroll - e.y * WHEEL_STEP,
                                                 self._detail_max_scroll()))
                return True
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and self._list.collidepoint(e.pos):
            idx = self._row_at(e.pos)
            if idx is not None:
                self.selected = None if idx == self.selected else idx
                self._detail_scroll = 0
                self._wrapped = None
            return True
        return False

    # ------------------------------------------------------------------ draw
    def _detail_lines(self) -> list[tuple[str, bool]]:
        if self._wrapped is not None:
            return self._wrapped
        lines: list[tuple[str, bool]] = []
        cur = self._current
        if cur is not None:
            body, bold = get_font(Size.body), get_font(Size.body, True)
            width = max(10, self._detail.w - 2 * PAD - SCROLLBAR_W)
            for i, para in enumerate(self._items[cur].details):
                for ln in wrap_text(para, bold if i == 0 else body, width):
                    lines.append((ln, i == 0))
        self._wrapped = lines
        return lines

    def draw(self, surface: pygame.Surface) -> None:
        self._draw_list(surface)
        self._draw_hint(surface)
        self._draw_detail(surface)

    def _draw_hint(self, surface: pygame.Surface) -> None:
        if not self._items or self._hint.w <= 0:
            return
        text = ("Click a row above to see its trace"
                if self.selected is None
                else "Click the row again to return to the latest")
        font = get_font(Size.caption)
        txt = render_text(ellipsize(text, font, self._hint.w), Size.caption, Color.text)
        surface.blit(txt, txt.get_rect(midleft=self._hint.midleft))

    def _draw_list(self, surface: pygame.Surface) -> None:
        vp = self._list
        old_clip = surface.get_clip()
        surface.set_clip(vp)
        if not self._items:
            msg = render_text("No moves yet", Size.body, Color.text_dim)
            surface.blit(msg, msg.get_rect(center=vp.center))
        else:
            cur = self._current
            font = get_font(Size.body)
            for i, item in enumerate(self._items):
                rect = self._row_rect(item)
                if rect.bottom < vp.top or rect.top > vp.bottom:
                    continue
                pygame.draw.rect(surface, Color.surface_3 if i == cur else Color.surface_2,
                                 rect, border_radius=Radius.control)
                if i == cur:
                    pygame.draw.rect(surface, Color.focus, rect, width=Stroke.thin,
                                     border_radius=Radius.control)
                pygame.draw.rect(surface, item.color, pygame.Rect(rect.x, rect.y, STRIPE, rect.h),
                                 border_top_left_radius=Radius.control,
                                 border_bottom_left_radius=Radius.control)
                max_w = rect.w - STRIPE - Space.sm - Space.xs
                txt = render_text(ellipsize(item.label, font, max_w), Size.body, Color.text)
                surface.blit(txt, txt.get_rect(midleft=(rect.x + STRIPE + Space.sm, rect.centery)))
        surface.set_clip(old_clip)
        draw_scrollbar(surface, vp, self._content_h, self.scroll, self._max_scroll)

    def _draw_detail(self, surface: pygame.Surface) -> None:
        d = self._detail
        if d.w <= 0 or d.h <= 0:
            return
        pygame.draw.rect(surface, Color.surface_2, d, border_radius=Radius.card)
        inner = d.inflate(-2 * PAD, -2 * PAD)
        lines = self._detail_lines()
        if not lines:
            msg = render_text("Log appears here", Size.body, Color.text_dim)
            surface.blit(msg, msg.get_rect(center=d.center))
            return

        lh = get_font(Size.body).get_linesize()
        content_h = len(lines) * lh
        max_scroll = max(0, content_h - inner.h)
        self._detail_scroll = max(0, min(self._detail_scroll, max_scroll))

        old_clip = surface.get_clip()
        surface.set_clip(inner)
        y = inner.y - self._detail_scroll
        for text, is_title in lines:
            if y + lh >= inner.top and y <= inner.bottom:
                surface.blit(render_text(text, Size.body, Color.text if is_title else Color.text_dim, is_title),
                             (inner.x, y))
            y += lh
        surface.set_clip(old_clip)
        draw_scrollbar(surface, inner, content_h, self._detail_scroll, max_scroll)