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
+ Lật thẻ (_reveal) private: mọi lần lật đều phải đi qua submit_verdict
+ Đếm SAT query: mỗi VerdictResult ghi đủ các lần gọi solver trong lần nộp đó,
  gồm cả truy vấn kiểm tra KB_t (chỉ chạy ở lần nộp đầu tiên trên mỗi state)
+ EngineInvariantError: verdict đã chứng minh lại khác đáp án (lỗi encoder / solver),
  GUI bắt riêng loại lỗi này để báo lỗi nội bộ thay vì sập app
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from agent.entailment import CellClassification, EntailmentChecker, EntailmentTimeout, SatQuery, Verdict
from game.board import Board
from game.cell import Cell
from game.character import Status
from game.public_state import PublicState, RevealedCard
from game.puzzle_loader import PuzzleFull, load_puzzle


class EngineInvariantError(RuntimeError):
    """
    Bất biến của engine bị vi phạm: verdict đã được chứng minh từ KB_t nhưng khác đáp án ẩn
    + Không phải lỗi đầu vào nên kế thừa RuntimeError, KHÔNG kế thừa ValueError
      (tránh bị các khối except ValueError bắt nhầm)
    + Khi lỗi xảy ra, state và history giữ nguyên
    """


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
    classification: CellClassification      # truy vấn phân loại ô (tách riêng với query của agent)
    consistency: SatQuery | None = None     # truy vấn kiểm tra KB_t, chỉ có ở lần nộp đầu tiên trên mỗi state
    revealed: RevealedCard | None = None    # thẻ vừa lật, chỉ có khi ACCEPTED

    @property
    def accepted(self) -> bool:
        return self.outcome is VerdictOutcome.ACCEPTED

    @property
    def queries(self) -> tuple[SatQuery, ...]:
        """Mọi lần gọi solver trong lần nộp này, theo thứ tự chạy"""
        head = () if self.consistency is None else (self.consistency,)
        return head + self.classification.queries

    @property
    def sat_queries(self) -> int:
        """Số lần gọi solver trong lần nộp này, gồm cả truy vấn kiểm tra KB_t nếu có"""
        return len(self.queries)


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

        checker, consistency = self._entailment()
        try:
            classification = checker.classify(cell)
        except EntailmentTimeout as exc:
            raise EntailmentTimeout.wrap(exc, () if consistency is None else (consistency,)) from exc
        outcome = _decide(classification.verdict, status)

        revealed = None
        if outcome is VerdictOutcome.ACCEPTED:
            revealed = self._reveal(cell, status)

        result = VerdictResult(cell, status, outcome, classification,
                               consistency=consistency, revealed=revealed)
        self._history.append(result)
        return result

    # Nội bộ

    def _entailment(self) -> tuple[EntailmentChecker, SatQuery | None]:
        """
        Checker cho state hiện tại, chỉ dựng lại khi state đổi
        (nhiều verdict bị từ chối liên tiếp trên cùng state dùng chung một KB_t)
        + Khi dựng mới: chạy luôn truy vấn kiểm tra KB_t và trả về để tính vào lần nộp này;
          checker lưu kết quả nên classify không gọi solver lần nữa cho truy vấn này
        + Khi dùng lại: trả None vì truy vấn đó đã được tính ở lần nộp trước
        + Chỉ lưu checker sau khi truy vấn chạy xong: nếu SolverTimeout thì lần sau dựng lại từ đầu
        """
        if self._checker is not None:
            return self._checker, None
        checker = EntailmentChecker(self._state, self._time_limit)
        consistency = checker.consistency_query()
        self._checker = checker
        return checker, consistency

    def _reveal(self, cell: Cell, status: Status) -> RevealedCard:
        """Lật thẻ: thêm verdict và clue của ô vào public state"""
        # solution luôn là một model của KB_t (clue đều đúng, verdict cũ đều đúng),
        # nên verdict đã được chứng minh mà khác đáp án nghĩa là encoder / solver có lỗi
        if self._puzzle.solution[cell] is not status:
            raise EngineInvariantError(
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