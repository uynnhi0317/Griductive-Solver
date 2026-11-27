import os
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
from .overlays import GuideOverlay, LoadOverlay, Overlay, peek_stage
from .highlight import highlight_roles
from .layout import MIN_WINDOW, compute_layout
from .sidebar import Sidebar
from .theme import Color, Level, clear_caches
from .verdict_popup import ResultDialog, VerdictDialog
from .action_log import ActionLog
from agent.logic_agent import AgentInvariantError, Hint, LogicAgent, find_hint
from agent.trace import AgentStatus

PUZZLE_ROOT = Path(__file__).resolve().parent.parent / "puzzles"
RESCALE_WINDOW = 0.8
FPS = 60
MAX_FRAME_DT = 0.1       # chặn dt khi một frame bị treo (hộp thoại Load, SAT query chậm) để animation không nhảy vọt
SAT_TIME_LIMIT = 10.0     # giây cho mỗi SAT query; solver chạy trên luồng UI nên giới hạn này cũng là thời gian treo tối đa
DEFAULT_STATUS = "Click a face-down card to give your verdict (or use arrow keys, then Enter / C / I)."

_ARROWS = {pygame.K_UP: (-1, 0), pygame.K_DOWN: (1, 0), pygame.K_LEFT: (0, -1), pygame.K_RIGHT: (0, 1)}
_BLOCKING_MODS = pygame.KMOD_CTRL | pygame.KMOD_ALT | pygame.KMOD_META


class App:
    """
    Giữ layout, GameEngine và định tuyến sự kiện; mọi hit-testing nằm trong từng component.
    GUI chỉ thấy PublicState (engine.state), không bao giờ chạm tới PuzzleFull / đáp án ẩn.
    """

    def __init__(self, puzzle_root: Path = PUZZLE_ROOT) -> None:
        self.puzzle_root = Path(puzzle_root)
        # Windows đang scale 125%/150%: không khai báo thì Windows vẽ ở độ phân giải thấp rồi kéo giãn -> mờ.
        # Báo SDL tự vẽ theo pixel thật (SDL >= 2.24; macOS / Linux bỏ qua biến này)
        os.environ.setdefault("SDL_WINDOWS_DPI_AWARENESS", "permonitorv2")
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
        self.verdict_dialog = VerdictDialog(self._choose_verdict, self._cancel_verdict)
        self.result_dialog = ResultDialog(self._close_overlay)
        self.agent: LogicAgent | None = None
        self.log = ActionLog()
        self.auto_running = False
        self._auto_wait = 0.0
        self.actionbar = ActionBar(
            on_help=self._show_guide,
            on_hint=self._hint_action,
            on_auto_solve=self._toggle_auto,
            on_restart=self._restart,
            on_load=self._open_load
        )
        self._hint: Hint | None = None
        self._hint_stage = 0
        self.overlay: Overlay | None = None
        self.guide = GuideOverlay(self._close_overlay)
        self.loader = LoadOverlay(self._apply_load, self._close_overlay)

        self.stages = discover_puzzles(self.puzzle_root)
        if not self.stages:
            raise SystemExit(f"Không tìm thấy câu đố trong {self.puzzle_root}")
        self.stage_index: int | None = 0   # None khi đang chơi một file nạp từ ngoài danh sách màn
        self.engine: GameEngine | None = None
        self.selected: Cell | None = None   # ô đang chọn; nếu thẻ đã lật thì clue của nó là clue đang chọn
        if not any(self._load_stage(i) for i in range(len(self.stages))):
            raise SystemExit("Không tìm được puzzle tải thành công")

        self._show_guide(first_run=True)

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
        self.board.fit(lay.board)
        self.panel.fit(lay.sidebar)
        screen = self.screen.get_rect()
        self.guide.fit(screen)
        self.loader.fit(screen)
        self.verdict_dialog.fit(screen)
        self.result_dialog.fit(screen)

    def _event_order(self):
        return (self.topbar, self.actionbar, self.statusbar, self.panel, self.board)

    def _draw_order(self):
        return (self.topbar, self.actionbar, self.statusbar, self.panel, self.board)

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
        self._hint = None
        self._hint_stage = 0
        self.actionbar.set_hint_stage(0)
        self.agent = None
        self.log.clear()
        self._stop_auto()
        self.stage_index = stage_index
        self.selected = None
        self.board = BoardView(engine.state, self.layout.board, on_select=self._on_card_click)
        self.panel = Sidebar(engine.state, self._snapshot(), self.layout.sidebar,
                            on_select=lambda cell: self._select(cell, toggle=True))
        self._apply_selection()
        self._refresh_chrome()
        self._say(DEFAULT_STATUS)
        pygame.display.set_caption(f"Griductive Solver - {engine.title or engine.puzzle_id}")
        self._fit_all()
        return True

    def _sync_views(self) -> None:
        """Đẩy PublicState mới của engine xuống các view"""
        self._reset_hint()
        self.board.refresh(self.state)
        self.panel.refresh(self.state, self._snapshot())
        self._apply_selection()
        self._refresh_chrome()

    def _refresh_chrome(self) -> None:
        total = self.state.board.size ** 2
        sat_calls = self._snapshot().total_sat
        self.topbar.set_info(
            self.engine.title or self.engine.puzzle_id,
            "Custom file" if self.stage_index is None else f"Stage {self.stage_index + 1}/{len(self.stages)}",
            f"Revealed {len(self.state.cards)}/{total}   SAT calls {sat_calls}",
        )

    def _can_call(self) -> bool:
        return self.selected is not None and not self.state.is_known(self.selected) and not self.auto_running

    def _snapshot(self):
        return self.log.snapshot(self.engine.history)

    # ______________________________________________________________actions
    def _nav(self, delta: int) -> None:
        if self.stage_index is None:        # đang ở file ngoài danh sách: tiến thì vào màn đầu, lùi thì vào màn cuối
            target = 0 if delta > 0 else len(self.stages) - 1
        else:
            target = (self.stage_index + delta) % len(self.stages)
        if self._load_stage(target):
            self._say(f"Loaded {self.engine.title or self.engine.puzzle_id}.", Level.OK)
        else:
            self._fail(f"Could not load {self.stages[target].name} (see console).")

    def _restart(self) -> None:
        self._stop_auto()
        self.engine.restart()
        self.log.clear()
        self.selected = None
        self._sync_views()
        self._say("Restarted.", Level.OK)

    def _fail(self, message: str) -> None:
        self._say(message, Level.ERROR)

    def _who(self, cell: Cell) -> str:
        return f"{cell.label} {self.state.board.character_at(cell).name}"

    def _warn_select_first(self) -> None:
        """Người chơi gọi verdict khi chưa có thẻ úp nào được chọn (bấm nút xám hoặc phím C / I)"""
        msg = "Auto Solve is running. Press Stop first." if self.auto_running else "Select a face-down card first."
        self._say(msg, Level.WARN)

    def _verdict(self, status: Status) -> None:
        """Người chơi gọi ô đang chọn là status; engine quyết định bằng entailment trên PublicState"""
        if not self._can_call():
            self._warn_select_first()
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
            self.log.clear_end()
            self.selected = None        # bỏ chọn: bàn cờ trở lại bình thường, bấm vào thẻ mới xem clue vừa lộ
            self._sync_views()          # thẻ lật, clue mới vào panel
            if self.engine.is_solved():
                msg = f"Solved! {who} is {status.value}, last card revealed ({queries})."
                self._say(msg, Level.OK)
            else:
                self._say(f"{who} is {status.value}. New clue revealed ({queries}).", Level.OK)
            return

        self.board.shake(cell)
        if outcome is VerdictOutcome.NOT_PROVABLE:
            self._say(f"NOT PROVABLE: neither status of {who} is forced by the revealed clues ({queries}).", Level.WARN)
        elif outcome is VerdictOutcome.CONTRADICTED:
            self._say(f"CONTRADICTED: {who} cannot be {status.value}; the opposite verdict is forced ({queries}).", Level.ERROR)
        else:   # INCONSISTENT
            self._fail("INCONSISTENT: the revealed clues contradict each other (puzzle or encoder bug).")
        if outcome in (VerdictOutcome.NOT_PROVABLE, VerdictOutcome.CONTRADICTED):
            self.result_dialog.open(outcome, self.state.board.character_at(cell).name, status)
            self.overlay = self.result_dialog
        self.panel.refresh(self.state, self._snapshot())   # verdict bị từ chối cũng nằm trong history
        self._refresh_chrome()          # số SAT calls tăng kể cả khi bị từ chối

    # ______________________________________________________________overlays
    def _show_guide(self, first_run: bool = False) -> None:
        if self.auto_running:
            self._toggle_auto()
        self.guide.footer = "Click anywhere to start" if first_run else "Click anywhere to continue"
        self.overlay = self.guide

    def _close_overlay(self) -> None:
        self.overlay = None

    def _open_verdict_dialog(self) -> None:
        """Hộp thoại giữa màn hình cho thẻ úp đang chọn: Innocent / Criminal / Cancel"""
        cell = self.selected
        ch = self.state.board.character_at(cell)
        self.verdict_dialog.open(ch.name, ch.profession, cell.label)
        self.overlay = self.verdict_dialog

    def _choose_verdict(self, status: Status) -> None:
        self.overlay = None
        self._verdict(status)

    def _cancel_verdict(self) -> None:
        self.overlay = None
        self._announce_selection()

    def _open_load(self) -> None:
        """Nút Load / phím L: mở overlay chọn màn (chỉ đọc title và size của từng file)"""
        if self.auto_running:
            self._toggle_auto()
        infos = [peek_stage(path) for path in self.stages]
        self.loader.open(infos, self.stage_index or 0, self.stage_index)
        self.overlay = self.loader

    def _apply_load(self, index: int) -> None:
        self.overlay = None
        if self._load_stage(index):
            self._say(f"Loaded {self.engine.title or self.engine.puzzle_id}.", Level.OK)
        else:
            self._fail(f"Could not load {self.stages[index].name} (see console).")

    # ______________________________________________________________hint
    def _hint_action(self) -> None:
        if self.auto_running:
            self._warn_select_first()
            return
        if self._hint_stage == 0:
            self._hint_show_clues()
        elif self._hint_stage == 1:
            self._hint_show_target()
        else:
            self._reset_hint()
            self._say(DEFAULT_STATUS)

    def _hint_show_clues(self) -> None:
        if self.engine.is_solved():
            self._say("Nothing to hint: the puzzle is solved.")
            return
        try:
            hint = find_hint(self.state, SAT_TIME_LIMIT)    # PublicState only, never the hidden solution
        except SolverTimeout:
            self._fail(f"Solver timed out after {SAT_TIME_LIMIT:g}s; no hint.")
            return
        if hint is None:
            self._say("No hint: no character is forced by the revealed clues. The solver will not guess.", Level.WARN)
            return

        # a selected revealed card would paint its clue regions, which could include the target
        if self.selected is not None and self.state.is_known(self.selected):
            self.selected = None
            self._apply_selection()
            self._refresh_chrome()

        support = [Cell.parse(label) for label in hint.clue_ids]
        self._hint, self._hint_stage = hint, 1
        self.board.set_support(support)
        self.actionbar.set_hint_stage(1)
        if support:
            owners = ", ".join(self._who(c) for c in support)
            self._say(f"Hint 1/2: the highlighted cards hold the clues that prove a verdict ({owners}). Press Reveal for the card.")
        else:
            self._say("Hint 1/2: a verdict follows from the known verdicts alone. Press Reveal for the card.")

    def _hint_show_target(self) -> None:
        self._hint_stage = 2
        self.board.set_support(())
        self.board.set_hint(self._hint.cell)
        self.actionbar.set_hint_stage(2)
        who = self._who(self._hint.cell)
        self._say(f"Hint 2/2: {who} can be proved. Press Clear to dismiss.")

    def _reset_hint(self) -> None:
        self._hint = None
        self._hint_stage = 0
        self.board.set_hint(None)
        self.board.set_support(())
        self.actionbar.set_hint_stage(0)

    # ______________________________________________________________auto solve
    def _toggle_auto(self) -> None:
        if self.auto_running:
            self._stop_auto()
            self._refresh_chrome()
            self._say("Auto Solve stopped.")
            return
        if self.engine.is_solved():
            self._say("Nothing to solve: the puzzle is already solved.")
            return
        if self.agent is None:
            self.agent = LogicAgent(self.engine, SAT_TIME_LIMIT)   # tự reset trace nếu state bị đổi từ ngoài
        self.auto_running = True
        self._auto_wait = 0.0           # bước đầu chạy ngay
        self.board.set_hint(None)
        self.actionbar.set_auto_running(True)
        self._refresh_chrome()
        self._say("Auto Solve running. Press Stop (or Esc) to interrupt.")

    def _stop_auto(self) -> None:
        self.auto_running = False
        self.actionbar.set_auto_running(False)

    def _auto_step(self) -> None:
        self._auto_wait = self.statusbar.speed.value
        try:
            step = self.agent.step()
        except (EngineInvariantError, AgentInvariantError) as exc:
            print(f"[App] {exc}")
            self._stop_auto()
            self._refresh_chrome()
            self._fail("Internal error during Auto Solve (encoder/solver bug), see console.")
            return
        if step is not None:
            self.selected = step.cell       # chọn thẻ vừa giải: flip + highlight clue vừa lộ
            self.log.record_agent_step(len(self.engine.history) - 1, step)
            self._sync_views()
            self._say(f"Auto: {self._who(step.cell)} is {step.verdict.value} "
                      f"(step {step.step}, {step.sat_queries + step.engine_queries} SAT queries).", Level.OK)
        if self.agent.status.is_terminal:
            self._auto_finish(self.agent.status)

    def _auto_finish(self, status):
        self._stop_auto()
        self.log.record_end(self.agent.trace)
        self.panel.refresh(self.state, self._snapshot())
        self._refresh_chrome()
        trace = self.agent.trace
        if status is AgentStatus.SOLVED:
            self._say(f"Auto Solve finished: puzzle solved ({trace.num_steps} verdicts by the agent).", Level.OK)
        elif status is AgentStatus.AMBIGUOUS:
            n = len(trace.final_unknown)
            self._say(f"Auto Solve stopped: {n} card(s) still UNKNOWN and none is forced. The agent will not guess.", Level.WARN)
        elif status is AgentStatus.INCONSISTENT:
            self._fail("INCONSISTENT: the revealed clues contradict each other (puzzle or encoder bug).")
        else:   # TIMEOUT
            self._fail(f"Solver timed out after {SAT_TIME_LIMIT:g}s; Auto Solve stopped.")

    # _____________________________________________________________selection
    def _on_card_click(self, cell: Cell | None) -> None:
        """Bấm thẻ úp: chọn và mở hộp thoại phán quyết; thẻ đã lật / chỗ trống: chọn hoặc bỏ chọn như cũ"""
        if cell is not None and not self.state.is_known(cell) and not self.auto_running:
            self._select(cell)
            self._open_verdict_dialog()
        else:
            self._select(cell, toggle=True)

    def _select(self, cell: Cell | None, toggle: bool = False) -> None:
        """Chọn ô; toggle=True (click chuột): bấm lại ô đang chọn thì bỏ chọn"""
        self.selected = None if toggle and cell is not None and cell == self.selected else cell
        if cell is not None and cell == self.board.hint:
            self._reset_hint()
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
            self._say(f"{self._who(cell)}: press Enter to give your verdict, or C / I.")
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
        elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and self._can_call():
            self._open_verdict_dialog()
        elif e.key == pygame.K_c:
            self._verdict(Status.CRIMINAL)
        elif e.key == pygame.K_i:
            self._verdict(Status.INNOCENT)
        elif e.key == pygame.K_h:
            self._hint_action()
        elif e.key == pygame.K_a:
            self._toggle_auto()
        elif e.key == pygame.K_ESCAPE:
            if self.auto_running:
                self._toggle_auto()
            elif self._hint_stage:
                self._reset_hint()
                self._say(DEFAULT_STATUS)
            else:
                self._select(None)
        elif e.key == pygame.K_PAGEUP:
            self._nav(-1)
        elif e.key == pygame.K_PAGEDOWN:
            self._nav(1)
        elif e.key == pygame.K_F1:
            self._show_guide()
        elif e.key == pygame.K_l:
            self._open_load()
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
        elif self.overlay is not None:
            self.overlay.handle_event(e)
        elif e.type == pygame.KEYDOWN and self._on_key(e):
            return
        else:
            for component in self._event_order():     # component nào nuốt sự kiện thì dừng
                if component.handle_event(e):
                    return

    # ___________________________________________________________________show
    def update(self, dt: float) -> None:
        self.board.update(dt)
        if self.auto_running:
            self._auto_wait -= dt
            if self._auto_wait <= 0:
                self._auto_step()
        if self.overlay is not None:
            self.overlay.update(dt)

    def draw(self) -> None:
        self.screen.fill(Color.bg)
        for component in self._draw_order():
            component.draw(self.screen)
        if self.overlay is not None:
            self.overlay.draw(self.screen)

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