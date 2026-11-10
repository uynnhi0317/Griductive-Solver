"""
Bộ đánh giá ngữ nghĩa trực tiếp (Semantic Evaluator) cho các clue.
Kiểm tra một phép gán đầy đủ (Cell -> Status) có thỏa mãn clue hay không
mà tuyệt đối không gọi qua bộ mã hóa CNF.
"""

from typing import Iterable, Mapping

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


def validate_assignment(board: Board, assignment: Assignment) -> None:
    """
    Kiểm tra assignment có chứa đầy đủ mọi ô trên board với kiểu Status hợp lệ hay không.
    Ném ValueError nếu thiếu ô hoặc giá trị không phải là Status.
    """
    missing: list[str] = []
    for cell in board.cells():
        if cell not in assignment:
            missing.append(cell.label)
            continue
        status = assignment[cell]
        if not isinstance(status, Status):
            raise ValueError(
                f"[Semantics]: Trạng thái tại ô {cell.label} phải là Status, nhận được {status!r}"
            )

    if missing:
        raise ValueError(
            f"[Semantics]: Assignment chưa đầy đủ, thiếu các ô: {', '.join(missing)}"
        )


def count_criminals(cells: Iterable[Cell], assignment: Assignment) -> int:
    """Đếm số lượng nhân vật là CRIMINAL trong tập các ô cho trước."""
    return sum(1 for cell in cells if assignment[cell] is Status.CRIMINAL)


def evaluate_clue(clue: Clue, board: Board, assignment: Assignment) -> bool:
    """
    Đánh giá trực tiếp một clue có thỏa mãn dưới phép gán đầy đủ assignment hay không.
    - Tự động gọi clue.validate(board) và validate_assignment(board, assignment).
    - Tuyệt đối không sử dụng CNF.
    """
    if not isinstance(clue, Clue):
        raise TypeError(f"[Semantics]: clue phải là thể hiện của Clue, nhận được {clue!r}")

    # 1. Kiểm tra tính hợp lệ của clue với board và của assignment
    clue.validate(board)
    validate_assignment(board, assignment)

    # 2. Đánh giá theo từng loại template
    if isinstance(clue, FactClue):
        return assignment[clue.cell] is clue.status

    if isinstance(clue, SameClue):
        return assignment[clue.a] is assignment[clue.b]

    if isinstance(clue, DifferentClue):
        return assignment[clue.a] is not assignment[clue.b]

    if isinstance(clue, ExactlyClue):
        cells = clue.region.cells(board)
        return count_criminals(cells, assignment) == clue.k

    if isinstance(clue, AtLeastClue):
        cells = clue.region.cells(board)
        return count_criminals(cells, assignment) >= clue.k

    if isinstance(clue, AtMostClue):
        cells = clue.region.cells(board)
        return count_criminals(cells, assignment) <= clue.k

    raise TypeError(f"[Semantics]: Chưa hỗ trợ đánh giá loại clue {type(clue).__name__}")


def evaluate_clues(
    clues: Iterable[Clue], board: Board, assignment: Assignment
) -> bool:
    """Kiểm tra toàn bộ danh sách clue có đồng thời thỏa mãn với assignment hay không."""
    validate_assignment(board, assignment)
    return all(evaluate_clue(clue, board, assignment) for clue in clues)