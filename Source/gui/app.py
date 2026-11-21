import pygame
from pathlib import Path
from game.cell import Cell
from game.puzzle_loader import discover_puzzles, load_puzzle, PuzzleFormatError
from game.public_state import PublicState
from .board_view import BoardView
from .clue_panel import CluePanel
from .highlight import highlight_roles
from .theme import Color

PUZZLE_ROOT = Path(__file__).resolve().parent.parent / "puzzles"
RESCALE_WINDOW = 0.8
MARGIN = 16
PANEL_FRAC = 0.30
PANEL_MIN_W = 300

class App:
    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption("Griductive Solver")
        info = pygame.display.Info()
        size = (int(info.current_w * RESCALE_WINDOW), int(info.current_h * RESCALE_WINDOW))
        self.screen = pygame.display.set_mode(size, pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.running = True

        self.stages = discover_puzzles(PUZZLE_ROOT)
        if not self.stages:
            raise SystemExit(f"Không tìm thấy câu đố trong {PUZZLE_ROOT}")
        self.stage_index = 0
        self.selected: Cell | None = None   # ô đang chọn; nếu thẻ đã lật thì clue của nó là clue đang chọn
        self.hovered = None
        if not any(self._load_stage(i) for i in range(len(self.stages))):
            raise SystemExit("Không tìm được puzzle tải thành công")

    #_________________________________________________________________setting up
    def _layout(self) -> tuple[pygame.Rect, pygame.Rect]:
        """Chia màn hình: bàn cờ bên trái, panel clue bên phải"""
        r = self.screen.get_rect()
        panel_w = min(max(PANEL_MIN_W, int(r.w * PANEL_FRAC)), r.w // 2)
        panel = pygame.Rect(r.right - panel_w - MARGIN, r.y + MARGIN, panel_w, r.h - 2 * MARGIN)
        board = pygame.Rect(r.x, r.y, r.w - panel_w - 2 * MARGIN, r.h)
        return board, panel

    def _set_state(self, state: PublicState) -> None:
        self.state = state
        self.board.refresh(state)
        self.panel.refresh(state)
        self._apply_selection()

    def _load_stage(self, index: int) -> bool:
        index %= len(self.stages)
        path = self.stages[index]
        try:
            puzzle = load_puzzle(path)
        except PuzzleFormatError as exc:
            print(f"[App] Không tải được puzzle {self.stages[index].name}: {exc}")
            return False
        board_area, panel_area = self._layout()
        self.state: PublicState = puzzle.initial_state()
        self.board = BoardView(self.state, board_area)
        self.panel = CluePanel(self.state, panel_area)
        self.stage_index = index
        self.selected = self.hovered = None
        self._apply_selection()
        pygame.display.set_caption(f"Griductive Solver - {puzzle.title or puzzle.puzzle_id}")
        return True

    #_______________________________________________________________selection
    def _select(self, cell: Cell | None) -> None:
        """Chọn ô; bấm lại ô đang chọn thì bỏ chọn"""
        self.selected = None if cell is not None and cell == self.selected else cell
        self._apply_selection()

    def _apply_selection(self) -> None:
        """Đồng bộ highlight trên bàn cờ và dòng được chọn trong panel theo clue đang chọn"""
        clue = self.state.revealed_clues().get(self.selected) if self.selected else None
        self.board.set_highlights(highlight_roles(clue, self.state.board) if clue else {})
        self.panel.selected = self.selected if clue else None

    #____________________________________________________________events
    def handle_event(self, e: pygame.event.Event) -> None:
        if e.type == pygame.QUIT:
            self.running = False
        elif e.type == pygame.VIDEORESIZE:
            board_area, panel_area = self._layout()
            self.board.fit(board_area)
            self.panel.fit(panel_area)
        elif e.type == pygame.MOUSEMOTION:
            self.hovered = self.board.cell_at_pixel(e.pos)
            self.panel.hover_pos = e.pos
        elif e.type == pygame.MOUSEWHEEL:
            if self.panel.area.collidepoint(pygame.mouse.get_pos()):
                self.panel.on_wheel(e.y)
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            if self.panel.area.collidepoint(e.pos):
                cell = self.panel.row_at_pixel(e.pos)
                if cell is not None:
                    self._select(cell)
            else:
                self._select(self.board.cell_at_pixel(e.pos))
        elif e.type == pygame.KEYDOWN:
            if e.key == pygame.K_RIGHT:
                self._load_stage(self.stage_index + 1)
            elif e.key == pygame.K_LEFT:
                self._load_stage(self.stage_index - 1)
            elif e.key == pygame.K_ESCAPE:
                self._select(None)

    #______________________________________________________________show        
    def draw(self) -> None:
        self.screen.fill(Color.bg)
        self.board.draw(self.screen, self.selected, self.hovered)
        self.panel.draw(self.screen)

    #_____________________________________________________________gameloop relevant
    def update(self, dt: float) -> None:
        self.board.update(dt)

    def run(self) -> None:
        while self.running:
            dt = self.clock.tick(60) / 1000
            for e in pygame.event.get():
                self.handle_event(e)
            self.update(dt)
            self.draw()
            pygame.display.flip()
        pygame.quit()