import pygame
from pathlib import Path
from engine.game_engine import EngineInvariantError, GameEngine, VerdictOutcome, VerdictResult
from game.cell import Cell
from game.character import Status
from game.puzzle_loader import discover_puzzles, PuzzleFormatError
from game.public_state import PublicState
from solver.dpll import SolverTimeout
from .board_view import BoardView
from .chrome import ActionBar, StatusBar, TopBar
from .clue_panel import CluePanel
from .dialogs import DialogUnavailable, ask_puzzle_path
from .highlight import highlight_roles
from .layout import MIN_WINDOW, compute_layout
from .theme import Color, Level, clear_caches
from .widgets import ToastManager

PUZZLE_ROOT = Path(__file__).resolve().parent.parent / "puzzles"
RESCALE_WINDOW = 0.8
FPS = 60
MAX_FRAME_DT = 0.1       # chặn dt khi một frame bị treo (hộp thoại Load, SAT query chậm) để animation không nhảy vọt
SAT_TIME_LIMIT = 10.0     # giây cho mỗi SAT query; solver chạy trên luồng UI nên giới hạn này cũng là thời gian treo tối đa
DEFAULT_STATUS = "Select a card (click or arrow keys), then press C for Criminal or I for Innocent."

_ARROWS = {pygame.K_UP: (-1, 0), pygame.K_DOWN: (1, 0), pygame.K_LEFT: (0, -1), pygame.K_RIGHT: (0, 1)}
_BLOCKING_MODS = pygame.KMOD_CTRL | pygame.KMOD_ALT | pygame.KMOD_META


class App:
    """
    Giữ layout, GameEngine và định tuyến sự kiện; mọi hit-testing nằm trong từng component.
    GUI chỉ thấy PublicState (engine.state), không bao giờ chạm tới PuzzleFull / đáp án ẩn.
    """

    def __init__(self, puzzle_root: Path = PUZZLE_ROOT) -> None:
        self.puzzle_root = Path(puzzle_root)
        pygame.init()
        pygame.display.set_caption("Griductive Solver")
        info = pygame.display.Info()
        size = (max(MIN_WINDOW[0], int(info.current_w * RESCALE_WINDOW)),
                max(MIN_WINDOW[1], int(info.current_h * RESCALE_WINDOW)))
        self.screen = pygame.display.set_mode(size, pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.running = True

        self.layout = compute_layout(self.screen.get_size())
        self.topbar = TopBar(self.layout.top_bar, lambda: self._nav(-1), lambda: self._nav(1))
        self.statusbar = StatusBar(self.layout.status)
        self.toasts = ToastManager()
        self.actionbar = ActionBar(
            on_verdict=self._verdict,
            on_hint=lambda: self._stub("Hint"),
            on_auto_solve=lambda: self._stub("Auto Solve"),
            on_restart=self._restart,
            on_load=self._load,
        )

        self.stages = discover_puzzles(self.puzzle_root)
        if not self.stages:
            raise SystemExit(f"Không tìm thấy câu đố trong {self.puzzle_root}")
        self.stage_index: int | None = 0   # None khi đang chơi một file nạp từ ngoài danh sách màn
        self.engine: GameEngine | None = None
        self.selected: Cell | None = None   # ô đang chọn; nếu thẻ đã lật thì clue của nó là clue đang chọn
        if not any(self._load_stage(i) for i in range(len(self.stages))):
            raise SystemExit("Không tìm được puzzle tải thành công")

    # ____________________________________________________________components
    @property
    def state(self) -> PublicState:
        return self.engine.state

    def _fit_all(self) -> None:
        """Gửi vùng mới cho mọi component theo self.layout"""
        lay = self.layout
        self.topbar.fit(lay.top_bar)
        self.actionbar.fit(lay.action_bar)
        self.statusbar.fit(lay.status)
        self.toasts.fit(lay.board)
        self.board.fit(lay.board)
        self.panel.fit(lay.sidebar)

    def _event_order(self):
        return (self.topbar, self.actionbar, self.panel, self.board)

    def _draw_order(self):
        return (self.board, self.panel, self.actionbar, self.topbar, self.statusbar, self.toasts)

    def _say(self, message: str, level: Level = Level.INFO) -> None:
        self.statusbar.say(message, level)

    def _load_stage(self, index: int) -> bool:
        index %= len(self.stages)
        return self._open_puzzle(self.stages[index], index)

    def _open_puzzle(self, path: Path, stage_index: int | None) -> bool:
        """Nạp puzzle từ file; thất bại thì giữ nguyên ván đang chơi. stage_index None = file ngoài danh sách"""
        try:
            engine = GameEngine.from_file(path, time_limit=SAT_TIME_LIMIT)
        except (PuzzleFormatError, OSError) as exc:
            print(f"[App] Không tải được puzzle {path.name}: {exc}")
            return False
        self.engine = engine
        self.stage_index = stage_index
        self.selected = None
        self.board = BoardView(engine.state, self.layout.board,
                               on_select=lambda cell: self._select(cell, toggle=True))
        self.panel = CluePanel(engine.state, self.layout.sidebar,
                               on_select=lambda cell: self._select(cell, toggle=True))
        self._apply_selection()
        self._refresh_chrome()
        self._say(DEFAULT_STATUS)
        pygame.display.set_caption(f"Griductive Solver - {engine.title or engine.puzzle_id}")
        self._fit_all()
        return True

    def _sync_views(self) -> None:
        """Đẩy PublicState mới của engine xuống các view"""
        self.board.refresh(self.state)
        self.panel.refresh(self.state)
        self._apply_selection()
        self._refresh_chrome()

    def _refresh_chrome(self) -> None:
        total = self.state.board.size ** 2
        sat_calls = sum(r.sat_queries for r in self.engine.history)
        self.topbar.set_info(
            self.engine.title or self.engine.puzzle_id,
            "Custom file" if self.stage_index is None else f"Stage {self.stage_index + 1}/{len(self.stages)}",
            f"Revealed {len(self.state.cards)}/{total}   SAT calls {sat_calls}",
        )
        self.actionbar.set_verdict_enabled(self._can_call())

    def _can_call(self) -> bool:
        return self.selected is not None and not self.state.is_known(self.selected)

    # ______________________________________________________________actions
    def _nav(self, delta: int) -> None:
        if self.stage_index is None:        # đang ở file ngoài danh sách: tiến thì vào màn đầu, lùi thì vào màn cuối
            target = 0 if delta > 0 else len(self.stages) - 1
        else:
            target = (self.stage_index + delta) % len(self.stages)
        if self._load_stage(target):
            self.toasts.clear()
            self._say(f"Loaded {self.engine.title or self.engine.puzzle_id}.", Level.OK)
        else:
            self._fail(f"Could not load {self.stages[target].name} (see console).")

    def _load(self) -> None:
        """Nút Load: chọn một file puzzle JSON bất kỳ"""
        try:
            path = ask_puzzle_path(self.puzzle_root)
        except DialogUnavailable as exc:
            self._fail(f"Cannot open the file dialog: {exc}")
            return
        if path is None:
            return                          # người dùng bấm Cancel
        index = next((i for i, stage in enumerate(self.stages) if stage.resolve() == path.resolve()), None)
        if self._open_puzzle(path, index):
            self.toasts.clear()
            self._say(f"Loaded {self.engine.title or self.engine.puzzle_id}.", Level.OK)
        else:
            self._fail(f"Could not load {path.name} (see console).")

    def _restart(self) -> None:
        self.engine.restart()
        self.selected = None
        self.toasts.clear()
        self._sync_views()
        self._say("Restarted.", Level.OK)

    def _stub(self, name: str) -> None:
        self._say(f"{name} is not implemented yet.", Level.INFO)
        self.toasts.show(f"{name}: coming in a later phase", Level.INFO)

    def _fail(self, message: str) -> None:
        self._say(message, Level.ERROR)
        self.toasts.show(message, Level.ERROR)

    def _who(self, cell: Cell) -> str:
        return f"{cell.label} {self.state.board.character_at(cell).name}"

    def _verdict(self, status: Status) -> None:
        """Người chơi gọi ô đang chọn là status; engine quyết định bằng entailment trên PublicState"""
        if not self._can_call():
            msg = "Select a face-down card first."
            self._say(msg, Level.WARN)
            self.toasts.show(msg, Level.WARN)
            return
        cell = self.selected
        try:
            result = self.engine.submit_verdict(cell, status)
        except SolverTimeout:
            self._fail(f"Solver timed out after {SAT_TIME_LIMIT:g}s; nothing changed.")
            return
        except EngineInvariantError as exc:
            print(f"[App] {exc}")
            self._fail("Internal error: a proved verdict disagrees with the hidden solution (encoder/solver bug).")
            return
        except ValueError as exc:
            self._fail(str(exc))
            return
        self._show_result(result)

    def _show_result(self, result: VerdictResult) -> None:
        cell, status, n = result.cell, result.submitted, result.sat_queries
        who = self._who(cell)
        queries = f"{n} SAT {'query' if n == 1 else 'queries'}"
        outcome = result.outcome

        if outcome is VerdictOutcome.ACCEPTED:
            self._sync_views()          # thẻ lật, clue mới vào panel; ô vẫn được chọn nên clue của nó được highlight
            if self.engine.is_solved():
                msg = f"Solved! {who} is {status.value}, last card revealed ({queries})."
                self._say(msg, Level.OK)
                self.toasts.show("Puzzle solved!", Level.OK)
            else:
                self._say(f"{who} is {status.value}. New clue revealed ({queries}).", Level.OK)
                self.toasts.show(f"{who} is {status.value}", Level.OK)
            return

        self.board.shake(cell)
        if outcome is VerdictOutcome.NOT_PROVABLE:
            self._say(f"NOT PROVABLE: neither status of {who} is forced by the revealed clues ({queries}).", Level.WARN)
            self.toasts.show(f"NOT PROVABLE: {who} is not forced yet", Level.WARN)
        elif outcome is VerdictOutcome.CONTRADICTED:
            self._say(f"CONTRADICTED: {who} cannot be {status.value}; the opposite verdict is forced ({queries}).", Level.ERROR)
            self.toasts.show(f"CONTRADICTED: {who} is not {status.value}", Level.ERROR)
        else:   # INCONSISTENT
            self._fail("INCONSISTENT: the revealed clues contradict each other (puzzle or encoder bug).")
        self._refresh_chrome()          # số SAT calls tăng kể cả khi bị từ chối

    # _____________________________________________________________selection
    def _select(self, cell: Cell | None, toggle: bool = False) -> None:
        """Chọn ô; toggle=True (click chuột): bấm lại ô đang chọn thì bỏ chọn"""
        self.selected = None if toggle and cell is not None and cell == self.selected else cell
        self._apply_selection()
        self._refresh_chrome()
        self._announce_selection()

    def _apply_selection(self) -> None:
        """Đồng bộ highlight trên bàn cờ và dòng được chọn trong panel theo clue đang chọn"""
        clue = self.state.revealed_clues().get(self.selected) if self.selected else None
        self.board.selected = self.selected
        self.board.set_highlights(highlight_roles(clue, self.state.board) if clue else {})
        self.panel.selected = self.selected if clue else None

    def _announce_selection(self) -> None:
        cell = self.selected
        if cell is None:
            self._say(DEFAULT_STATUS)
            return
        status = self.state.status_of(cell)
        if status is None:
            self._say(f"{self._who(cell)}: press C for Criminal or I for Innocent.")
        else:
            self._say(f"{self._who(cell)} is {status.value}. Highlighting the cells its clue refers to.")

    def _move_selection(self, d_row: int, d_col: int) -> None:
        n = self.state.board.size
        if self.selected is None:
            self._select(Cell(1, 1))
            return
        row = min(n, max(1, self.selected.row + d_row))
        col = min(n, max(1, self.selected.col + d_col))
        self._select(Cell(row, col))

    # ________________________________________________________________events
    def _on_key(self, e: pygame.event.Event) -> bool:
        """Điều khiển bằng bàn phím; trả True nếu phím đã được xử lý"""
        if e.mod & _BLOCKING_MODS:
            return False
        if e.key in _ARROWS:
            self._move_selection(*_ARROWS[e.key])
        elif e.key == pygame.K_c:
            self._verdict(Status.CRIMINAL)
        elif e.key == pygame.K_i:
            self._verdict(Status.INNOCENT)
        elif e.key == pygame.K_ESCAPE:
            self._select(None)
        elif e.key == pygame.K_PAGEUP:
            self._nav(-1)
        elif e.key == pygame.K_PAGEDOWN:
            self._nav(1)
        else:
            return False
        return True

    def handle_event(self, e: pygame.event.Event) -> None:
        if e.type == pygame.QUIT:
            self.running = False
        elif e.type == pygame.VIDEORESIZE:
            w, h = max(e.w, MIN_WINDOW[0]), max(e.h, MIN_WINDOW[1])
            if (w, h) != (e.w, e.h):      # pygame không có min size gốc: tự kéo cửa sổ về ngưỡng
                self.screen = pygame.display.set_mode((w, h), pygame.RESIZABLE)
            self.layout = compute_layout((w, h))
            self._fit_all()
        elif e.type == pygame.KEYDOWN and self._on_key(e):
            return
        else:
            for component in self._event_order():     # component nào nuốt sự kiện thì dừng
                if component.handle_event(e):
                    return

    # ___________________________________________________________________show
    def update(self, dt: float) -> None:
        for component in (self.board, self.toasts):
            component.update(dt)

    def draw(self) -> None:
        self.screen.fill(Color.bg)
        for component in self._draw_order():
            component.draw(self.screen)

    def run(self) -> None:
        while self.running:
            dt = min(self.clock.tick(FPS) / 1000, MAX_FRAME_DT)
            for e in pygame.event.get():
                self.handle_event(e)
            self.update(dt)
            self.draw()
            pygame.display.flip()
        clear_caches()
        pygame.quit()