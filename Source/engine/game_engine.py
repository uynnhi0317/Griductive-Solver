"""
Game Engine

+ Là thành phần DUY NHẤT giữ PuzzleFull (đáp án ẩn và clue của mọi thẻ, kể cả thẻ chưa lật)
+ Bên ngoài chỉ thấy PublicState qua thuộc tính state
+ Một verdict chỉ được chấp nhận khi nó là hệ quả logic của KB_t dựng từ PublicState,
  KHÔNG phải vì nó khớp với đáp án ẩn:
    ACCEPTED      verdict nộp lên bị ép buộc bởi KB_t      -> lật thẻ, lộ clue mới
    NOT_PROVABLE  cả hai trạng thái đều còn khả năng       -> giữ nguyên state
    CONTRADICTED  trạng thái đối nghịch mới bị ép buộc     -> giữ nguyên state
    INCONSISTENT  bản thân KB_t UNSAT                      -> giữ nguyên state
  INCONSISTENT không xảy ra với puzzle hợp lệ (đáp án luôn là một model của KB_t),
  chỉ giữ lại để không báo nhầm thành NOT_PROVABLE khi dữ liệu / encoder có lỗi
+ PublicState bất biến nên verdict bị từ chối không thể làm đổi state hay lộ clue
+ Lật thẻ (_reveal) private: mọi lần lật đều phải đi qua submit_port vòng.
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from agent.entailment import CellClassification, EntailmentChecker, Verdict
from game.board import Board
from game.cell import Cell
from game.character import Status
from game.public_state import PublicState, RevealedCard
from game.puzzle_loader import PuzzleFull, load_puzzle


class VerdictOutcome(Enum):
    """Phản hồi của engine cho một verdict"""
    ACCEPTED = "ACCEPTED"
    NOT_PROVABLE = "NOT_PROVABLE"
    CONTRADICTED = "CONTRADICTED"
    INCONSISTENT = "INCONSISTENT"


@dataclass(frozen=True)
class VerdictResult:
    """Kết quả một lần submit_verdict"""
    cell: Cell
    submitted: Status
    outcome: VerdictOutcome
    classification: CellClassification      # SAT query engine đã dùng để phán xử (tách riêng với query của agent)
    revealed: RevealedCard | None = None    # thẻ vừa lật, chỉ có khi ACCEPTED

    @property
    def accepted(self) -> bool:
        return self.outcome is VerdictOutcome.ACCEPTED

    @property
    def sat_queries(self) -> int:
        return self.classification.sat_queries


class GameEngine:
    """
    Quản lý vòng đời một ván chơi trên một PuzzleFull
    + submit_verdict: phán xử verdict bằng entailment trên PublicState hiện tại
    + restart: quay về state ban đầu (chỉ các thẻ mở sẵn)
    + time_limit: giới hạn giây cho mỗi SAT query (None hoặc số > 0);
      SolverTimeout được để nguyên cho tầng trên xử lý, khi đó state và history không đổi
    """

    def __init__(self, puzzle: PuzzleFull, time_limit: float | None = None) -> None:
        if not isinstance(puzzle, PuzzleFull):
            raise TypeError(f"[GameEngine]: Cần PuzzleFull, nhận được {type(puzzle).__name__}")
        _check_time_limit(time_limit)

        self._puzzle = puzzle
        self._time_limit = time_limit
        self._state: PublicState = puzzle.initial_state()
        self._checker: EntailmentChecker | None = None   # dựng lười, bỏ đi mỗi khi state đổi
        self._history: list[VerdictResult] = []

    @classmethod
    def from_file(cls, path: str | Path, time_limit: float | None = None) -> "GameEngine":
        """Load puzzle JSON rồi tạo engine"""
        return cls(load_puzzle(path), time_limit)

    # Thông tin công khai

    @property
    def state(self) -> PublicState:
        """PublicState hiện tại"""
        return self._state

    @property
    def board(self) -> Board:
        return self._puzzle.board

    @property
    def puzzle_id(self) -> str:
        return self._puzzle.puzzle_id

    @property
    def title(self) -> str:
        return self._puzzle.title

    @property
    def history(self) -> tuple[VerdictResult, ...]:
        """Mọi verdict đã nộp từ lần restart gần nhất, kể cả verdict bị từ chối"""
        return tuple(self._history)

    def is_solved(self) -> bool:
        return self._state.is_solved()

    # Điều khiển ván chơi

    def restart(self) -> None:
        """Quay về state ban đầu; dùng lại PuzzleFull đã load nên không đọc lại file"""
        self._state = self._puzzle.initial_state()
        self._checker = None
        self._history = []

    def submit_verdict(self, cell: Cell, status: Status) -> VerdictResult:
        """Phán xử verdict 'ô cell có trạng thái status'; chỉ đổi state khi ACCEPTED"""
        self._check_submission(cell, status)

        classification = self._entailment().classify(cell)
        outcome = _decide(classification.verdict, status)

        revealed = None
        if outcome is VerdictOutcome.ACCEPTED:
            revealed = self._reveal(cell, status)

        result = VerdictResult(cell, status, outcome, classification, revealed)
        self._history.append(result)
        return result

    # Nội bộ

    def _entailment(self) -> EntailmentChecker:
        """
        Checker cho state hiện tại, chỉ dựng lại khi state đổi
        (nhiều verdict bị từ chối liên tiếp trên cùng state dùng chung một KB_t)
        """
        if self._checker is None:
            self._checker = EntailmentChecker(self._state, self._time_limit)
        return self._checker

    def _reveal(self, cell: Cell, status: Status) -> RevealedCard:
        """Lật thẻ: thêm verdict và clue của ô vào public state"""
        # solution luôn là một model của KB_t (clue đều đúng, verdict cũ đều đúng),
        # nên verdict đã được chứng minh mà khác đáp án nghĩa là encoder / solver có lỗi
        if self._puzzle.solution[cell] is not status:
            raise RuntimeError(
                f"[GameEngine]: Verdict {status.value} tại {cell.label} được chứng minh "
                f"nhưng khác đáp án, kiểm tra lại encoder / solver"
            )
        self._state = self._state.with_verdict(cell, status, self._puzzle.clues[cell])
        self._checker = None  # state mới thì KB_t mới
        return self._state.cards[-1]

    def _check_submission(self, cell: Cell, status: Status) -> None:
        """Sai kiểu -> TypeError, sai giá trị -> ValueError"""
        if not isinstance(cell, Cell):
            raise TypeError(f"[GameEngine]: Cần Cell, nhận được {type(cell).__name__}")
        if not isinstance(status, Status):
            raise TypeError(f"[GameEngine]: Cần Status, nhận được {type(status).__name__}")
        if not self.board.contains(cell):
            raise ValueError(f"[GameEngine]: Ô {cell.label} ngoài board {self.board.size} x {self.board.size}")
        if self._state.is_known(cell):
            raise ValueError(f"[GameEngine]: Ô {cell.label} đã được lật")


def _check_time_limit(time_limit: float | None) -> None:
    """Kiểm tra ngay khi tạo engine, thay vì để DPLL báo lỗi ở lần nộp verdict đầu tiên"""
    if time_limit is None:
        return
    if isinstance(time_limit, bool) or not isinstance(time_limit, (int, float)):
        raise TypeError(f"[GameEngine]: time_limit phải là số, nhận được {type(time_limit).__name__}")
    if time_limit <= 0:
        raise ValueError(f"[GameEngine]: time_limit phải > 0, nhận được {time_limit!r}")


def _decide(verdict: Verdict, submitted: Status) -> VerdictOutcome:
    """Đổi kết quả entailment thành phản hồi cho người chơi"""
    if verdict is Verdict.INCONSISTENT:
        return VerdictOutcome.INCONSISTENT
    if verdict is Verdict.UNKNOWN:
        return VerdictOutcome.NOT_PROVABLE
    if verdict.to_status() is submitted:
        return VerdictOutcome.ACCEPTED
    return VerdictOutcome.CONTRADICTED