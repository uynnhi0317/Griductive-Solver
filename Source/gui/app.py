import pygame
from pathlib import Path
from game.puzzle_loader import discover_puzzles, load_puzzle, PuzzleFormatError
from game.public_state import PublicState
from .board_view import BoardView
from .theme import PALETTE

PUZZLE_ROOT = Path(__file__).resolve().parent.parent / "puzzles"
RESCALE_WINDOW = 0.8

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
        self.selected = None
        self.hovered = None
        if not any(self._load_stage(i) for i in range(len(self.stages))):
            raise SystemExit("Không tìm được puzzle tải thành công")

    #_________________________________________________________________setting up
    def _set_state(self, state: PublicState) -> None:
        self.state = state
        self.board.refresh(state)

    def _load_stage(self, index: int) -> bool:
        self.stage_index = index % len(self.stages)
        path = self.stages[self.stage_index]
        try:
            puzzle = load_puzzle(path)
        except PuzzleFormatError as exc:
            print(f"[App] Không tải được puzzle {self.stages[index].name}: {exc}")
            return False
        
        self.state: PublicState = puzzle.initial_state()
        self.board = BoardView(self.state, pygame.Surface(self.screen.get_size()).get_rect())
        self.selected = None
        pygame.display.set_caption(f"Griductive Solver - {puzzle.title or puzzle.puzzle_id}")
        return True
    
    #____________________________________________________________events
    def handle_event(self, e: pygame.event.Event) -> None:
        if e.type == pygame.QUIT:
            self.running = False
        elif e.type == pygame.VIDEORESIZE:
            self.board.fit(self.screen.get_size())
        elif e.type == pygame.MOUSEMOTION:
            self.hovered = self.board.cell_at_pixel(e.pos)
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            self.selected = self.board.cell_at_pixel(e.pos)
        elif e.type == pygame.KEYDOWN:
            if e.key == pygame.K_RIGHT:
                self._load_stage(self.stage_index + 1)
            elif e.key == pygame.K_LEFT:
                self._load_stage(self.stage_index - 1)

    #______________________________________________________________show        
    def draw(self) -> None:
        self.screen.fill(PALETTE["bg"])
        self.board.draw(self.screen, self.selected, self.hovered)

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