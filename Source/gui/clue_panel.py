import pygame
from typing import Callable
from dataclasses import dataclass
from game.cell import Cell
from game.character import Status
from game.public_state import PublicState
from .component import Component
from .highlight import Role
from .theme import (Color, Face, ROLE_COLOR, Radius, Size, Space, Stroke, SCROLLBAR_W,
                    draw_status_icon, get_font, render_text, wrap_text, draw_scrollbar)

PAD = Space.md              # lề của panel
ROW_PAD = Space.md          # lề trong một dòng clue
ROW_GAP = Space.sm
HEADER_H = 44
FOOTER_H = 34
ICON_R = 8
SWATCH = 12
WHEEL_STEP = 48

_LEGEND = (("Subject", Role.SUBJECT), ("Counted", Role.COUNTED), ("Condition", Role.CONDITION))


@dataclass
class _Row:
    cell: Cell               # ô sở hữu clue; cũng là định danh clue (vd. 'B5')
    name: str
    status: Status
    text: str
    lines: list[str] | None = None  # sau khi layout
    top: int = 0             # toạ độ y trong không gian nội dung (chưa trừ scroll)
    height: int = 0


class CluePanel(Component):
    """Danh sách clue đã lộ. Panel chỉ biết text (describe) nên clue extension tự hiển thị được."""

    def __init__(self, state: PublicState, area: pygame.Rect,
                 on_select: Callable[[Cell], None] | None = None):
        self.area = pygame.Rect(area)
        self._on_select = on_select or (lambda cell: None)
        self.selected: Cell | None = None
        self.hover_pos: tuple[int, int] | None = None
        self.scroll = 0
        self._draw_scrollbar = draw_scrollbar
        self._rows: list[_Row] = []
        self._content_h = 0
        self.refresh(state)

    # ________________________________________________________________layout
    @property
    def viewport(self) -> pygame.Rect:
        a = self.area
        return pygame.Rect(a.x, a.y + HEADER_H, a.w, a.h - HEADER_H - FOOTER_H)

    @property
    def max_scroll(self) -> int:
        return max(0, self._content_h - self.viewport.h)

    def _layout(self) -> None:
        body, tag = get_font(Size.body), get_font(Size.caption, True, Face.TYPEWRITER)
        text_w = self.area.w - 2 * PAD - 2 * ROW_PAD - SCROLLBAR_W
        y = 0
        for row in self._rows:
            row.lines = wrap_text(row.text, body, text_w)
            row.top = y
            row.height = ROW_PAD * 2 + max(tag.get_linesize(), 2 * ICON_R) + Space.xs \
                + len(row.lines) * body.get_linesize()
            y += row.height + ROW_GAP
        self._content_h = max(0, y - ROW_GAP)
        self.scroll = max(0, min(self.scroll, self.max_scroll))

    def fit(self, area: pygame.Rect) -> None:
        self.area = pygame.Rect(area)
        self._layout()

    # _____________________________________________________________update
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

    def handle_event(self, e: pygame.event.Event) -> bool:
        if e.type == pygame.MOUSEMOTION:
            self.hover_pos = e.pos
        elif e.type == pygame.MOUSEWHEEL:
            if self.area.collidepoint(pygame.mouse.get_pos()):
                self.on_wheel(e.y)
                return True
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and self.area.collidepoint(e.pos):
            cell = self.row_at_pixel(e.pos)
            if cell is not None:
                self._on_select(cell)
            return True
        return False

    def scroll_by(self, dy: int) -> None:
        self.scroll = max(0, min(self.scroll + dy, self.max_scroll))

    def on_wheel(self, wheel_y: int) -> None:
        self.scroll_by(-wheel_y * WHEEL_STEP)

    # _______________________________________________________________hit test
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

    # _________________________________________________________________show
    def draw(self, surface: pygame.Surface) -> None:
        a = self.area
        pygame.draw.rect(surface, Color.surface_1, a, border_radius=Radius.card)

        title = render_text(f"Clues ({len(self._rows)})", Size.h2, Color.text, True, Face.DISPLAY)
        surface.blit(title, (a.x + PAD, a.y + (HEADER_H - title.get_height()) // 2 + 2))

        vp = self.viewport
        hovered = self.row_at_pixel(self.hover_pos) if self.hover_pos else None
        old_clip = surface.get_clip()
        surface.set_clip(vp)
        if not self._rows:
            msg = render_text("No clues revealed yet", Size.body, Color.text_dim)
            surface.blit(msg, msg.get_rect(center=vp.center))
        for row in self._rows:
            rect = self._row_rect(row)
            if rect.bottom >= vp.top and rect.top <= vp.bottom:
                self._draw_row(surface, row, rect, row.cell == self.selected, row.cell == hovered)
        surface.set_clip(old_clip)

        draw_scrollbar(surface, vp, self._content_h, self.scroll, self.max_scroll)
        self._draw_legend(surface)

    def _draw_row(self, surface, row: _Row, rect: pygame.Rect, selected: bool, hovered: bool) -> None:
        bg = Color.surface_3 if (selected or hovered) else Color.surface_2
        pygame.draw.rect(surface, bg, rect, border_radius=Radius.control)
        if selected:
            pygame.draw.rect(surface, Color.focus, rect, width=Stroke.medium, border_radius=Radius.control)

        body_font = get_font(Size.body)
        x, y = rect.x + ROW_PAD, rect.y + ROW_PAD
        draw_status_icon(surface, row.status, x + ICON_R, y + ICON_R, ICON_R)
        tag = render_text(f"{row.cell.label}  {row.name}", Size.caption, Color.text_dim, True, Face.TYPEWRITER)
        surface.blit(tag, tag.get_rect(midleft=(x + 2 * ICON_R + Space.sm, y + ICON_R)))

        y += 2 * ICON_R + Space.xs
        for line in row.lines:
            surface.blit(render_text(line, Size.body, Color.text), (x, y))
            y += body_font.get_linesize()

    def _draw_legend(self, surface) -> None:
        x = self.area.x + PAD
        y = self.area.bottom - FOOTER_H // 2
        for label, role in _LEGEND:
            pygame.draw.rect(surface, ROLE_COLOR[role], (x, y - SWATCH // 2, SWATCH, SWATCH),
                             border_radius=Radius.small)
            txt = render_text(label, Size.caption, Color.text_dim)
            surface.blit(txt, (x + SWATCH + Space.sm, y - txt.get_height() // 2))
            x += SWATCH + Space.sm + txt.get_width() + Space.lg