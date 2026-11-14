import pygame
from game.public_state import PublicState
from game.cell import Cell
from .character_card import CharacterCard, CardModel
from .theme import get_font, PALETTE

LABEL_MARGIN = 40
PAD = 24

class BoardView:
    def __init__(self, state: PublicState, area: pygame.Rect, gap: int = 8):
        self.n = state.board.size
        self.gap = gap
        self._compute_layout(area)
        self.cards = {cell: CharacterCard(self.slot_rect(cell), 
                            self._model_for(state, cell)) for cell in state.board.cells()}

    #________________________________________________________________layout
    def _compute_layout(self, area: pygame.Rect):
        w, h = area.size
        avail = min(w, h) - 2*PAD - LABEL_MARGIN
        self.cell_size = max(5, (avail - (self.n - 1)*self.gap) // self.n)
        self.pitch = self.cell_size + self.gap
        board_px = self.n * self.cell_size + (self.n - 1) * self.gap
        self.o_x = area.x + (w - board_px) // 2 + LABEL_MARGIN // 2
        self.o_y = area.y + (h - board_px) // 2 + LABEL_MARGIN // 2

    def fit(self, area: pygame.Rect) -> None:
        self._compute_layout(area)
        for cell, card in self.cards.items():
            card.relayout(self.slot_rect(cell))

    #___________________________________________________________________board
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
        if (dx < 0 or dy < 0): return None                  # outside grid, above or to the left

        col0, rx = divmod(dx, self.pitch)
        row0, ry = divmod(dy, self.pitch)
        if row0 >= self.n or col0 >= self.n: return None    # outside grid, below or to the right
        if rx >= self.cell_size or ry >= self.cell_size: return None        # in between cards

        return Cell(row0 + 1, col0 + 1)

    #______________________________________________________update
    def refresh(self, state: PublicState) -> None:
        for cell, card in self.cards.items():
            card.sync(self._model_for(state, cell))

    def update(self, dt: float) -> None:
        for card in self.cards.values():
            card.update(dt)

    #_____________________________________________________show
    def _draw_labels(self, surface: pygame.Surface) -> None:
        font = get_font(max(12, self.cell_size // 6))
        half = LABEL_MARGIN // 2
        for i in range(self.n):
            row_txt = font.render(str(i + 1), True, PALETTE["text"])
            col_txt = font.render(chr(ord("A") + i), True, PALETTE["text"])
            row_slot = self.slot_rect(Cell(i + 1, 1))    # first column of row i+1
            col_slot = self.slot_rect(Cell(1, i + 1))    # first row of column i+1
            # numbers: left of the grid, vertically centered on their row
            surface.blit(row_txt, row_txt.get_rect(center=(self.o_x - half, row_slot.centery)))
            # letters: above the grid, horizontally centered on their column
            surface.blit(col_txt, col_txt.get_rect(center=(col_slot.centerx, self.o_y - half)))

    def draw(self, surface, selected, hovered) -> None:
        self._draw_labels(surface)
        for cell, card in self.cards.items():
            card.draw(surface, cell == selected, cell == hovered)
