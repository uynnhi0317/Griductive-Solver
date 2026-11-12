from dataclasses import dataclass
from types import MappingProxyType
from typing import Iterable, Mapping

from .board import Board
from .cell import Cell
from .character import Status
from .clue import Clue


@dataclass(frozen=True)
class RevealedCard:
    """Một thẻ đã lật: trạng thái đã chứng minh và clue của thẻ"""
    cell: Cell
    status: Status
    clue: Clue

    @property
    def clue_id(self) -> str:
        """Định danh clue = nhãn ô sở hữu clue (vd. 'B2'), dùng cho deduction trace"""
        return self.cell.label


class PublicState:
    def __init__(self, board: Board, cards: Iterable[RevealedCard] = ()) -> None:
        cards = tuple(cards)
        by_cell: dict[Cell, RevealedCard] = {}
        for card in cards:
            _check_card(board, card, by_cell)
            by_cell[card.cell] = card
        self._init_fields(board, cards, by_cell)

    @classmethod
    def empty(cls, board: Board) -> "PublicState":
        """State chưa có thẻ nào được lật"""
        return cls(board)

    @property
    def board(self) -> Board:
        return self._board

    @property
    def cards(self) -> tuple[RevealedCard, ...]:
        """Các thẻ đã lật theo thứ tự lật"""
        return self._cards

    def verdicts(self) -> Mapping[Cell, Status]:
        """Verdict đã chứng minh, chỉ đọc"""
        return self._verdicts

    def revealed_clues(self) -> Mapping[Cell, Clue]:
        """Clue đã lộ theo thứ tự lật, khoá là ô sở hữu clue, chỉ đọc"""
        return self._clues

    def active_clue_ids(self) -> tuple[str, ...]:
        """Định danh các clue đang có trong KB_t, theo thứ tự lật"""
        return tuple(card.clue_id for card in self._cards)

    def is_known(self, cell: Cell) -> bool:
        """Ô đã có verdict được chứng minh hay chưa"""
        return cell in self._by_cell

    def status_of(self, cell: Cell) -> Status | None:
        """Trạng thái đã chứng minh của ô, None nếu chưa biết"""
        return self._verdicts.get(cell)

    def unsolved_cells(self) -> tuple[Cell, ...]:
        """Các ô chưa có verdict, theo thứ tự row-major (thứ tự chọn của agent)"""
        return tuple(c for c in self._board.cells() if c not in self._by_cell)

    def is_solved(self) -> bool:
        return len(self._by_cell) == len(self._board.cells())

    def with_verdict(self, cell: Cell, status: Status, clue: Clue) -> "PublicState":
        """Trả về state mới sau khi lật thẻ ở ô cell; state hiện tại giữ nguyên"""
        card = RevealedCard(cell, status, clue)
        _check_card(self._board, card, self._by_cell)  # chỉ kiểm tra thẻ mới, thẻ cũ đã hợp lệ

        new_state = PublicState.__new__(PublicState)
        new_state._init_fields(self._board, self._cards + (card,), {**self._by_cell, cell: card})
        return new_state

    def _init_fields(self, board: Board, cards: tuple[RevealedCard, ...],
                     by_cell: dict[Cell, RevealedCard]) -> None:
        """Gán dữ liệu và dựng sẵn các view chỉ đọc một lần (state bất biến nên không bao giờ phải dựng lại)"""
        self._board = board
        self._cards = cards
        self._by_cell = by_cell
        self._verdicts = MappingProxyType({card.cell: card.status for card in cards})
        self._clues = MappingProxyType({card.cell: card.clue for card in cards})


def _check_card(board: Board, card: RevealedCard, known: Mapping[Cell, RevealedCard]) -> None:
    """Kiểm tra một thẻ trước khi thêm vào state: ô, trạng thái, và clue hợp lệ với board"""
    if not isinstance(card, RevealedCard):
        raise ValueError(f"[PublicState]: Phần tử phải là RevealedCard, nhận được {card!r}")
    if not board.contains(card.cell):
        raise ValueError(f"[PublicState]: Ô {card.cell.label} ngoài board {board.size} x {board.size}")
    if card.cell in known:
        raise ValueError(f"[PublicState]: Ô {card.cell.label} đã có verdict")
    if not isinstance(card.status, Status):
        raise ValueError(f"[PublicState]: Trạng thái không hợp lệ: {card.status!r}")
    if not isinstance(card.clue, Clue):
        raise ValueError(f"[PublicState]: Clue không hợp lệ: {card.clue!r}")
    card.clue.validate(board)
    