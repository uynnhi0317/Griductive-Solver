import pygame
from typing import Callable, Mapping
from game.public_state import PublicState
from game.cell import Cell
from .character_card import CharacterCard, CardModel
from .component import Component
from .highlight import Role
from .theme import Color, Size, Space, render_text

LABEL_MARGIN = Space.xxl + Space.sm
PAD = Space.md
MAX_CELL = 200          # thẻ không to hơn mức này, tránh 3x3 thành những tấm bảng khổng lồ


class BoardView(Component):
    """
    Lưới thẻ. Tự xử lý hover / click; chọn ô thì gọi on_select(cell) (None khi bấm ra ngoài lưới).
    Trạng thái `selected` do App đặt (nguồn sự thật là App, vì panel clue cũng dùng chung).
    """

    def __init__(self, state: PublicState, area: pygame.Rect,
                 on_select: Callable[[Cell | None], None] | None = None, gap: int = Space.sm):
        self.n = state.board.size
        self.gap = gap
        self.area = pygame.Rect(area)
        self.selected: Cell | None = None
        self.hovered: Cell | None = None
        self._on_select = on_select or (lambda cell: None)
        self._compute_layout(self.area)
        self.hint: Cell | None = None
        self.cards = {cell: CharacterCard(self.slot_rect(cell),
                            self._model_for(state, cell)) for cell in state.board.cells()}

    # ________________________________________________________________layout
    def _compute_layout(self, area: pygame.Rect):
        w, h = area.size
        avail = min(w, h) - 2 * PAD - LABEL_MARGIN
        self.cell_size = min(MAX_CELL, max(5, (avail - (self.n - 1) * self.gap) // self.n))
        self.pitch = self.cell_size + self.gap
        board_px = self.n * self.cell_size + (self.n - 1) * self.gap
        self.o_x = area.x + (w - board_px) // 2 + LABEL_MARGIN // 2
        self.o_y = area.y + (h - board_px) // 2 + LABEL_MARGIN // 2

    def fit(self, area: pygame.Rect) -> None:
        self.area = pygame.Rect(area)
        self._compute_layout(self.area)
        for cell, card in self.cards.items():
            card.relayout(self.slot_rect(cell))

    # ___________________________________________________________________board
    @staticmethod
    def _model_for(state: PublicState, cell: Cell) -> CardModel:
        clue = state.revealed_clues().get(cell)
        return CardModel(cell, state.board.character_at(cell),
                         state.status_of(cell),
                         clue.describe(state.board) if clue else None)

    def slot_rect(self, cell: Cell) -> pygame.Rect:
        """rect cố định của 1 slot Cell. Dùng để vẽ và test hitting"""
        x = self.o_x + (cell.col - 1) * self.pitch
        y = self.o_y + (cell.row - 1) * self.pitch
        return pygame.Rect(x, y, self.cell_size, self.cell_size)

    def cell_at_pixel(self, pos) -> Cell | None:   # for click handling
        pixel_x, pixel_y = pos
        dx, dy = pixel_x - self.o_x, pixel_y - self.o_y
        if dx < 0 or dy < 0:
            return None                                     # outside grid, above or to the left

        col0, rx = divmod(dx, self.pitch)
        row0, ry = divmod(dy, self.pitch)
        if row0 >= self.n or col0 >= self.n:
            return None                                     # outside grid, below or to the right
        if rx >= self.cell_size or ry >= self.cell_size:
            return None                                     # in between cards

        return Cell(row0 + 1, col0 + 1)

    # ______________________________________________________update
    def refresh(self, state: PublicState) -> None:
        for cell, card in self.cards.items():
            card.sync(self._model_for(state, cell))

    def set_highlights(self, roles: Mapping[Cell, Role]) -> None:
        """Tô các ô theo vai trò; ô không có trong roles bị bỏ highlight"""
        for cell, card in self.cards.items():
            card.role = roles.get(cell)

    def shake(self, cell: Cell) -> None:
        """Rung thẻ khi verdict bị từ chối"""
        self.cards[cell].shake()

    def set_hint(self, cell: Cell | None) -> None:
        """Đặt (hoặc bỏ, nếu None) thẻ mục tiêu của Hint"""
        self.hint = cell
        for c, card in self.cards.items():
            card.hint = c == cell

    def handle_event(self, e: pygame.event.Event) -> bool:
        if e.type == pygame.MOUSEMOTION:
            self.hovered = self.cell_at_pixel(e.pos)
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and self.area.collidepoint(e.pos):
            self._on_select(self.cell_at_pixel(e.pos))
            return True
        return False

    def update(self, dt: float) -> None:
        for card in self.cards.values():
            card.update(dt)

    # _____________________________________________________show
    def _draw_labels(self, surface: pygame.Surface) -> None:
        size = max(Size.body, self.cell_size // 7)
        half = LABEL_MARGIN // 2
        for i in range(self.n):
            row_txt = render_text(str(i + 1), size, Color.text_dim, True)
            col_txt = render_text(chr(ord("A") + i), size, Color.text_dim, True)
            row_slot = self.slot_rect(Cell(i + 1, 1))    # first column of row i+1
            col_slot = self.slot_rect(Cell(1, i + 1))    # first row of column i+1
            # numbers: left of the grid, vertically centered on their row
            surface.blit(row_txt, row_txt.get_rect(center=(self.o_x - half, row_slot.centery)))
            # letters: above the grid, horizontally centered on their column
            surface.blit(col_txt, col_txt.get_rect(center=(col_slot.centerx, self.o_y - half)))

    def draw(self, surface: pygame.Surface) -> None:
        self._draw_labels(surface)
        # thẻ được chọn vẽ sau cùng để phần phóng to / vòng focus không bị thẻ kề đè lên
        for cell, card in self.cards.items():
            if cell != self.selected:
                card.draw(surface, False, cell == self.hovered)
        if self.selected in self.cards:
            self.cards[self.selected].draw(surface, True, self.selected == self.hovered)