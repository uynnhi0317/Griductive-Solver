import pygame
from dataclasses import dataclass
from game.cell import Cell
from game.character import Status
from game.public_state import PublicState
from .highlight import Role
from .theme import (PALETTE, ROLE_COLOR, SELECT_COLOR, STATUS_COLOR,
                    draw_rect_alpha, get_font, wrap_text)

PAD = 12            # lề của panel
ROW_PAD = 10        # lề trong một dòng clue
ROW_GAP = 8
HEADER_H = 44
FOOTER_H = 34
RADIUS = 10
SCROLLBAR_W = 6
WHEEL_STEP = 48

_LEGEND = (("Subject", Role.SUBJECT), ("Counted", Role.COUNTED), ("Condition", Role.CONDITION))


@dataclass
class _Row:
    cell: Cell               # ô sở hữu clue; cũng là định danh clue (vd. 'B5')
    name: str
    status: Status
    text: str
    lines: list[str] = None  # sau khi layout
    top: int = 0             # toạ độ y trong không gian nội dung (chưa trừ scroll)
    height: int = 0


class CluePanel:
    """Danh sách clue đã lộ. Panel chỉ biết text (describe) nên clue extension tự hiển thị được."""

    def __init__(self, state: PublicState, area: pygame.Rect):
        self.area = pygame.Rect(area)
        self.selected: Cell | None = None
        self.hover_pos: tuple[int, int] | None = None
        self.scroll = 0
        self._rows: list[_Row] = []
        self._content_h = 0
        self.refresh(state)

    #________________________________________________________________layout
    @property
    def viewport(self) -> pygame.Rect:
        a = self.area
        return pygame.Rect(a.x, a.y + HEADER_H, a.w, a.h - HEADER_H - FOOTER_H)

    @property
    def max_scroll(self) -> int:
        return max(0, self._content_h - self.viewport.h)

    def _layout(self) -> None:
        body, tag = get_font(21), get_font(18)
        text_w = self.area.w - 2 * PAD - 2 * ROW_PAD - SCROLLBAR_W
        y = 0
        for row in self._rows:
            row.lines = wrap_text(row.text, body, text_w)
            row.top = y
            row.height = ROW_PAD * 2 + tag.get_linesize() + 4 + len(row.lines) * body.get_linesize()
            y += row.height + ROW_GAP
        self._content_h = max(0, y - ROW_GAP)
        self.scroll = max(0, min(self.scroll, self.max_scroll))

    def fit(self, area: pygame.Rect) -> None:
        self.area = pygame.Rect(area)
        self._layout()

    #_____________________________________________________________update
    def refresh(self, state: PublicState) -> None:
        """Dựng lại danh sách theo thứ tự lật; có clue mới thì tự cuộn xuống cuối"""
        board = state.board
        grew = len(state.cards) > len(self._rows)
        self._rows = [
            _Row(c.cell, board.character_at(c.cell).name, c.status, c.clue.describe(board))
            for c in state.cards
        ]
        self._layout()
        if grew:
            self.scroll = self.max_scroll

    def scroll_by(self, dy: int) -> None:
        self.scroll = max(0, min(self.scroll + dy, self.max_scroll))

    def on_wheel(self, wheel_y: int) -> None:
        self.scroll_by(-wheel_y * WHEEL_STEP)

    #_______________________________________________________________hit test
    def _row_rect(self, row: _Row) -> pygame.Rect:
        vp = self.viewport
        return pygame.Rect(vp.x + PAD, vp.y + row.top - self.scroll,
                           vp.w - 2 * PAD - SCROLLBAR_W, row.height)

    def row_at_pixel(self, pos) -> Cell | None:
        """Ô sở hữu clue tại vị trí chuột, None nếu không trúng dòng nào"""
        if not self.viewport.collidepoint(pos):
            return None
        for row in self._rows:
            if self._row_rect(row).collidepoint(pos):
                return row.cell
        return None

    #_________________________________________________________________show
    def draw(self, surface: pygame.Surface) -> None:
        a = self.area
        pygame.draw.rect(surface, PALETTE["panel_bg"], a, border_radius=RADIUS)

        title = get_font(28).render(f"Clues ({len(self._rows)})", True, PALETTE["text"])
        surface.blit(title, (a.x + PAD, a.y + (HEADER_H - title.get_height()) // 2 + 2))

        vp = self.viewport
        hovered = self.row_at_pixel(self.hover_pos) if self.hover_pos else None
        old_clip = surface.get_clip()
        surface.set_clip(vp)
        if not self._rows:
            msg = get_font(21).render("No clues revealed yet", True, PALETTE["text_dim"])
            surface.blit(msg, msg.get_rect(center=vp.center))
        for row in self._rows:
            rect = self._row_rect(row)
            if rect.bottom >= vp.top and rect.top <= vp.bottom:
                self._draw_row(surface, row, rect, row.cell == self.selected, row.cell == hovered)
        surface.set_clip(old_clip)

        self._draw_scrollbar(surface, vp)
        self._draw_legend(surface)

    def _draw_row(self, surface, row: _Row, rect: pygame.Rect, selected: bool, hovered: bool) -> None:
        bg = (PALETTE["panel_row_selected"] if selected
              else PALETTE["panel_row_hover"] if hovered else PALETTE["panel_row"])
        pygame.draw.rect(surface, bg, rect, border_radius=8)
        if selected:
            pygame.draw.rect(surface, SELECT_COLOR[row.status], rect, width=2, border_radius=8)

        tag_font, body_font = get_font(18), get_font(21)
        x, y = rect.x + ROW_PAD, rect.y + ROW_PAD
        pygame.draw.circle(surface, STATUS_COLOR[row.status], (x + 5, y + tag_font.get_linesize() // 2), 5)
        tag = tag_font.render(f"{row.cell.label}  {row.name}", True, PALETTE["text_dim"])
        surface.blit(tag, (x + 16, y))

        y += tag_font.get_linesize() + 4
        for line in row.lines:
            surface.blit(body_font.render(line, True, PALETTE["text"]), (x, y))
            y += body_font.get_linesize()

    def _draw_scrollbar(self, surface, vp: pygame.Rect) -> None:
        if self.max_scroll <= 0:
            return
        track_h = vp.h
        thumb_h = max(24, track_h * vp.h // self._content_h)
        thumb_y = vp.y + (track_h - thumb_h) * self.scroll // self.max_scroll
        thumb = pygame.Rect(vp.right - SCROLLBAR_W - 4, thumb_y, SCROLLBAR_W, thumb_h)
        draw_rect_alpha(surface, (*PALETTE["text_dim"][:3], 140), thumb, 3)

    def _draw_legend(self, surface) -> None:
        font = get_font(18)
        x = self.area.x + PAD
        y = self.area.bottom - FOOTER_H // 2
        for label, role in _LEGEND:
            pygame.draw.rect(surface, ROLE_COLOR[role], (x, y - 6, 12, 12), border_radius=3)
            txt = font.render(label, True, PALETTE["text_dim"])
            surface.blit(txt, (x + 18, y - txt.get_height() // 2))
            x += 18 + txt.get_width() + 18