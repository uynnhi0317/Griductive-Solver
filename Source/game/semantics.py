"""
Bộ đánh giá ngữ nghĩa trực tiếp (Semantic Evaluator) cho các clue.

Mở rộng: để hỗ trợ một loại clue mới, chỉ cần viết một hàm evaluator và gắn
@register_evaluator(LoaiClueMoi).
"""

from typing import Callable, Iterable, Mapping

from .board import Board
from .cell import Cell
from .character import Status
from .clue import (
    AtLeastClue,
    AtMostClue,
    Clue,
    DifferentClue,
    ExactlyClue,
    FactClue,
    SameClue,
)

# Phép gán đầy đủ từ từng ô trên bàn cờ sang trạng thái CRIMINAL / INNOCENT
Assignment = Mapping[Cell, Status]

# Hàm đánh giá không validate: (clue, board, assignment) -> bool
Evaluator = Callable[[Clue, Board, Assignment], bool]

_EVALUATORS: dict[type[Clue], Evaluator] = {}


def register_evaluator(*clue_classes: type[Clue]) -> Callable[[Evaluator], Evaluator]:
    """Decorator đăng ký một hàm đánh giá cho một hay nhiều loại clue."""
    if not clue_classes:
        raise TypeError("[Semantics]: register_evaluator cần ít nhất một loại clue")

    def decorator(fn: Evaluator) -> Evaluator:
        for clue_cls in clue_classes:
            if not (isinstance(clue_cls, type) and issubclass(clue_cls, Clue)):
                raise TypeError(
                    f"[Semantics]: {clue_cls!r} phải là lớp con của Clue"
                )
            if clue_cls in _EVALUATORS:
                raise ValueError(
                    f"[Semantics]: Đã có evaluator cho {clue_cls.__name__}"
                )
            _EVALUATORS[clue_cls] = fn
        return fn

    return decorator


def _find_evaluator(clue: Clue) -> Evaluator:
    """Tìm evaluator theo MRO để clue con (subclass) tự dùng lại evaluator của lớp cha."""
    for cls in type(clue).__mro__:
        evaluator = _EVALUATORS.get(cls)
        if evaluator is not None:
            return evaluator
    raise TypeError(f"[Semantics]: Chưa hỗ trợ đánh giá loại clue {type(clue).__name__}")


# validation
def validate_assignment(board: Board, assignment: Assignment) -> None:
    """
    Kiểm tra assignment có đúng tập ô của board với kiểu Status hợp lệ hay không.
    Ném ValueError nếu thiếu ô, thừa ô hoặc giá trị không phải là Status.
    """
    board_cells = set(board.cells())

    missing = [c.label for c in board.cells() if c not in assignment]
    if missing:
        raise ValueError(
            f"[Semantics]: Assignment chưa đầy đủ, thiếu các ô: {', '.join(missing)}"
        )

    extra = sorted(c.label for c in assignment if c not in board_cells)
    if extra:
        raise ValueError(
            f"[Semantics]: Assignment có ô ngoài board: {', '.join(extra)}"
        )

    for cell in board.cells():
        if not isinstance(assignment[cell], Status):
            raise ValueError(
                f"[Semantics]: Trạng thái tại ô {cell.label} phải là Status, "
                f"nhận được {assignment[cell]!r}"
            )


def count_criminals(cells: Iterable[Cell], assignment: Assignment) -> int:
    """Đếm số lượng nhân vật là CRIMINAL trong tập các ô cho trước."""
    return sum(1 for cell in cells if assignment[cell] is Status.CRIMINAL)


# evaluators
@register_evaluator(FactClue)
def _eval_fact(clue: FactClue, board: Board, assignment: Assignment) -> bool:
    return assignment[clue.cell] is clue.status


@register_evaluator(SameClue)
def _eval_same(clue: SameClue, board: Board, assignment: Assignment) -> bool:
    return assignment[clue.a] is assignment[clue.b]


@register_evaluator(DifferentClue)
def _eval_different(clue: DifferentClue, board: Board, assignment: Assignment) -> bool:
    return assignment[clue.a] is not assignment[clue.b]


def _criminals_in_region(
    clue: ExactlyClue | AtLeastClue | AtMostClue,
    board: Board,
    assignment: Assignment,
) -> int:
    return count_criminals(clue.region.cells(board), assignment)


@register_evaluator(ExactlyClue)
def _eval_exactly(clue: ExactlyClue, board: Board, assignment: Assignment) -> bool:
    return _criminals_in_region(clue, board, assignment) == clue.k


@register_evaluator(AtLeastClue)
def _eval_at_least(clue: AtLeastClue, board: Board, assignment: Assignment) -> bool:
    return _criminals_in_region(clue, board, assignment) >= clue.k


@register_evaluator(AtMostClue)
def _eval_at_most(clue: AtMostClue, board: Board, assignment: Assignment) -> bool:
    return _criminals_in_region(clue, board, assignment) <= clue.k


# public API
def _check_clue(clue: Clue, board: Board) -> None:
    if not isinstance(clue, Clue):
        raise TypeError(f"[Semantics]: clue phải là thể hiện của Clue, nhận được {clue!r}")
    clue.validate(board)


def evaluate_clue_unchecked(clue: Clue, board: Board, assignment: Assignment) -> bool:
    """Đánh giá clue mà không thực hiện kiểm tra tính hợp lệ."""
    return _find_evaluator(clue)(clue, board, assignment)


def evaluate_clue(clue: Clue, board: Board, assignment: Assignment) -> bool:
    """
    Đánh giá trực tiếp một clue dưới phép gán đầy đủ.
    Tự validate clue và assignment.
    """
    _check_clue(clue, board)
    validate_assignment(board, assignment)
    return evaluate_clue_unchecked(clue, board, assignment)


def evaluate_clues(clues: Iterable[Clue], board: Board, assignment: Assignment) -> bool:
    """
    Kiểm tra toàn bộ clue có đồng thời thỏa mãn hay không.
    Validate assignment và từng clue đúng một lần.
    """
    clue_list = list(clues)
    for clue in clue_list:
        _check_clue(clue, board)
    validate_assignment(board, assignment)
    return all(evaluate_clue_unchecked(c, board, assignment) for c in clue_list)