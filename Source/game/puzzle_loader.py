"""
Đọc puzzle JSON và tách thành PuzzleFull (cho Game Engine) và PublicState ban đầu (cho Agent / GUI)

Định dạng JSON cho puzzle N x N (1 <= N <= Board.MAX_SIZE)
Mọi ô dùng nhãn '<cột><hàng>': cột là chữ cái từ 'A', hàng là số từ 1 (vd. 'A1', 'C2').
{   
  "title": "<tên màn chơi>",                                                # tuỳ chọn, mặc định ""
  "description": "<mô tả ngắn>",                                            # tuỳ chọn, mặc định ""
  "id": "<định danh puzzle>",
  "size": N,
  "characters": {"<ô>": {"name": "<tên>", "profession": "<nghề>"}, ...},   # đủ N*N ô, tên phân biệt
  "solution":   {"<ô>": "CRIMINAL" | "INNOCENT", ...},                     # đáp án ẩn, đủ N*N ô
  "clues":      {"<ô>": <clue>, ...},                                       # clue trên thẻ của ô đó, đủ N*N ô
  "initially_revealed": ["<ô>", ...]                                        # thẻ mở sẵn: ít nhất 1, phân biệt
}

<clue> gồm 6 loại lõi; clue mở rộng đăng ký qua register_clue
dùng định dạng to_dict() của chính nó:
  {"type": "FACT", "cell": "<ô>", "status": "CRIMINAL" | "INNOCENT"}
  {"type": "SAME" | "DIFFERENT", "cells": ["<ô>", "<ô khác>"]}
  {"type": "EXACTLY" | "AT_LEAST" | "AT_MOST", "k": <số nguyên>, "region": <region>}   # 0 <= k <= số ô của region

<region> (đúng to_dict() của game/region.py):
  {"type": "ROW", "number": <hàng>}
  {"type": "COLUMN", "letter": "<cột>"}
  {"type": "NEIGHBORS", "cell": "<ô>"}                  # các ô kề 8 hướng, không gồm chính ô đó
  {"type": "CELLS", "cells": ["<ô>", ...]}              # danh sách ô phân biệt, không rỗng

Mọi ô được nhắc tới phải nằm trong board; vi phạm bất kỳ ràng buộc nào đều báo PuzzleFormatError.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping, TypeVar

from .board import Board
from .cell import Cell
from .character import Status
from .clue import Clue, clue_from_dict
from .public_state import PublicState, RevealedCard

T = TypeVar("T")

PUZZLE_SUFFIX = ".json"
_REQUIRED_FIELDS = ("id", "size", "characters", "solution", "clues", "initially_revealed")


class PuzzleFormatError(ValueError):
    """Puzzle sai định dạng hoặc dữ liệu không nhất quán"""


@dataclass(frozen=True, eq=False)
class PuzzleFull:
    """
    Toàn bộ puzzle, chỉ Game Engine được giữ:
    gồm đáp án ẩn và clue của mọi thẻ (kể cả thẻ chưa lật)

    eq=False: Board không định nghĩa __eq__ nên so sánh hai PuzzleFull bằng == không có ý nghĩa;
    muốn so nội dung thì so to_dict()
    """
    puzzle_id: str
    board: Board
    solution: Mapping[Cell, Status]
    clues: Mapping[Cell, Clue]
    initially_revealed: tuple[Cell, ...]
    title: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        cells = self.board.cells()
        _require_every_cell(self.solution, cells, "solution")
        _require_every_cell(self.clues, cells, "clues")

        for cell in cells:
            if not isinstance(self.solution[cell], Status):
                raise ValueError(f"[Puzzle]: Trạng thái của {cell.label} không hợp lệ: {self.solution[cell]!r}")
            try:
                self.clues[cell].validate(self.board)
            except ValueError as exc:
                raise ValueError(f"[Puzzle]: Clue của {cell.label} không hợp lệ: {exc}") from None

        self._validate_initially_revealed()

        # Sắp theo row-major và khoá lại để không ai sửa được đáp án / clue sau khi load
        object.__setattr__(self, "solution", MappingProxyType({c: self.solution[c] for c in cells}))
        object.__setattr__(self, "clues", MappingProxyType({c: self.clues[c] for c in cells}))
        object.__setattr__(self, "initially_revealed", tuple(self.initially_revealed))

    def initial_state(self) -> PublicState:
        """PublicState ban đầu: chỉ gồm các thẻ mở sẵn"""
        return PublicState(
            self.board,
            (RevealedCard(c, self.solution[c], self.clues[c]) for c in self.initially_revealed),
        )

    def to_dict(self) -> dict[str, Any]:
        """Chuyển ngược về dict đúng định dạng JSON"""
        cells = self.board.cells()
        return {
            "id": self.puzzle_id,
            "title": self.title,
            "description": self.description,
            "size": self.board.size,
            "characters": {c.label: asdict(self.board.character_at(c)) for c in cells},
            "solution": {c.label: self.solution[c].value for c in cells},
            "clues": {c.label: self.clues[c].to_dict() for c in cells},
            "initially_revealed": [c.label for c in self.initially_revealed],
        }

    def _validate_initially_revealed(self) -> None:
        revealed = self.initially_revealed
        if not revealed:
            raise ValueError("[Puzzle]: Cần ít nhất một thẻ mở sẵn")
        if len(set(revealed)) != len(revealed):
            raise ValueError("[Puzzle]: Các thẻ mở sẵn phải phân biệt")
        for cell in revealed:
            if not self.board.contains(cell):
                raise ValueError(f"[Puzzle]: Thẻ mở sẵn {cell.label} ngoài board")


def parse_puzzle(data: Mapping[str, Any]) -> PuzzleFull:
    """Dựng PuzzleFull từ dict (đã đọc từ JSON); mọi lỗi được gói thành PuzzleFormatError"""
    if not isinstance(data, Mapping):
        raise PuzzleFormatError("[Puzzle]: Dữ liệu puzzle phải là một object JSON")

    puzzle_id = data.get("id", "<unknown>")
    try:
        return _build_puzzle(data)
    except KeyError as exc:
        raise PuzzleFormatError(f"[Puzzle {puzzle_id}]: Thiếu trường {exc}") from exc
    except (ValueError, TypeError) as exc:
        raise PuzzleFormatError(f"[Puzzle {puzzle_id}]: {exc}") from exc


def load_puzzle(path: str | Path) -> PuzzleFull:
    """Đọc một file puzzle JSON"""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PuzzleFormatError(f"[Puzzle]: File {path} không phải JSON hợp lệ: {exc}") from exc
    return parse_puzzle(data)


def discover_puzzles(root: str | Path) -> tuple[Path, ...]:
    """Liệt kê mọi file puzzle trong thư mục, sắp xếp xác định theo đường dẫn"""
    return tuple(sorted(Path(root).rglob(f"*{PUZZLE_SUFFIX}")))


def _build_puzzle(data: Mapping[str, Any]) -> PuzzleFull:
    missing = [f for f in _REQUIRED_FIELDS if f not in data]
    if missing:
        raise ValueError(f"Thiếu trường {', '.join(repr(f) for f in missing)}")

    size = data["size"]
    if not isinstance(size, int) or isinstance(size, bool):
        raise ValueError(f"'size' phải là số nguyên, nhận được {size!r}")

    revealed = data["initially_revealed"]
    if not isinstance(revealed, list):
        raise ValueError("'initially_revealed' phải là danh sách nhãn ô")

    characters = _require_mapping(data["characters"], "characters")
    for label, info in characters.items():
        _require_mapping(info, f"characters.{label}")

    return PuzzleFull(
        puzzle_id=str(data["id"]),
        board=Board.from_dict(size, characters),
        solution=_parse_cell_map(data["solution"], "solution", _parse_status),
        clues=_parse_cell_map(data["clues"], "clues", _parse_clue),
        initially_revealed=tuple(_parse_label(label) for label in revealed),
        title=_optional_text(data, "title"),
        description=_optional_text(data, "description"),
    )


def _parse_cell_map(raw: Any, field: str, parse_value: Callable[[Any], T]) -> dict[Cell, T]:
    """Đọc object {nhãn ô: giá trị} thành {Cell: giá trị đã parse}"""
    mapping = _require_mapping(raw, field)
    result: dict[Cell, T] = {}
    for label, value in mapping.items():
        try:
            result[_parse_label(label)] = parse_value(value)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"'{field}' tại {label}: {exc}") from None
    return result


def _parse_label(label: Any) -> Cell:
    """Nhãn ô phải là chuỗi dạng 'A1' trước khi đưa cho Cell.parse"""
    if not isinstance(label, str):
        raise ValueError(f"Nhãn ô phải là chuỗi, nhận được {label!r}")
    return Cell.parse(label)


def _optional_text(data: Mapping[str, Any], field: str) -> str:
    """Trường văn bản tuỳ chọn (title, description): thiếu thì là chuỗi rỗng"""
    value = data.get(field, "")
    if not isinstance(value, str):
        raise ValueError(f"'{field}' phải là chuỗi, nhận được {type(value).__name__}")
    return value
    

def _parse_clue(raw: Any) -> Clue:
    return clue_from_dict(_require_mapping(raw, "clue"))


def _parse_status(raw: Any) -> Status:
    try:
        return Status(raw)
    except (ValueError, TypeError):
        raise ValueError(f"Trạng thái không hợp lệ: {raw!r}") from None


def _require_mapping(raw: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError(f"'{field}' phải là object JSON, nhận được {type(raw).__name__}")
    return raw


def _require_every_cell(mapping: Mapping[Cell, Any], cells: tuple[Cell, ...], field: str) -> None:
    """Mapping phải có đúng một mục cho mỗi ô trên board, không thiếu không thừa"""
    keys, expected = set(mapping), set(cells)
    missing = sorted(expected - keys)
    extra = sorted(keys - expected)
    if missing:
        raise ValueError(f"'{field}' thiếu ô: {', '.join(c.label for c in missing)}")
    if extra:
        raise ValueError(f"'{field}' có ô ngoài board: {', '.join(c.label for c in extra)}")
