"""
Sinh câu tiếng Anh tự nhiên cho clue
Phục vụ hiển thị (GUI, trace)
"""

from .board import Board
from .character import Status
from .region import ExplicitList, Neighbors, Region, join_names, possessive

_QUANTIFIER = {"EXACTLY": "exactly", "AT_LEAST": "at least", "AT_MOST": "at most"}


# Từ ngữ theo trạng thái
def status_word(status: Status) -> str:
    """Tính từ / danh từ số ít: 'criminal' hoặc 'innocent'"""
    return "criminal" if status is Status.CRIMINAL else "innocent"


def status_noun(status: Status, count: int) -> str:
    """Danh từ theo số lượng: 'criminal' / 'criminals', 'innocent' / 'innocents'"""
    return status_word(status) + ("" if count == 1 else "s")


def status_phrase(status: Status) -> str:
    """Vị ngữ số ít sau 'is': 'a criminal' hoặc 'innocent'"""
    return "a criminal" if status is Status.CRIMINAL else "innocent"


def _predicate(status: Status, count: int) -> str:
    """Vị ngữ theo số lượng: 'is a criminal' / 'are criminals', 'is innocent' / 'are innocent'"""
    if count == 1:
        return f"is {status_phrase(status)}"
    return "are " + ("criminals" if status is Status.CRIMINAL else "innocent")


def _be(count: int) -> str:
    return "is" if count == 1 else "are"


def _single(name: str, status: Status, holds: bool) -> str:
    """Vùng chỉ có một người: 'Eve is a criminal' hoặc 'Eve is innocent'"""
    return f"{name} is {status_phrase(status if holds else status.opposite)}"


# Thông tin vùng dùng trong câu
def _owner(region: Neighbors, board: Board) -> str:
    return board.character_at(region.center).name


def _names(region: ExplicitList, board: Board) -> list[str]:
    return [board.character_at(c).name for c in region.members]


def among(region: Region, board: Board) -> str:
    """Cụm chỉ phạm vi: 'in row 2', 'among Eve's neighbors', 'among Alice and Ivy'"""
    if isinstance(region, (Neighbors, ExplicitList)):
        return f"among {region.describe(board)}"
    return f"in {region.describe(board)}"


# Mẫu câu
def count_sentence(region: Region, board: Board, op: str, k: int, status: Status = Status.CRIMINAL) -> str:
    """Câu cho EXACTLY / AT_LEAST / AT_MOST k người có trạng thái status trong vùng"""
    quantifier = _QUANTIFIER[op]
    none = k == 0 and op in ("EXACTLY", "AT_MOST")
    word = status_word(status)

    if isinstance(region, Neighbors):
        owner = _owner(region, board)
        if none:
            return f"{owner} has no {word} neighbors"
        return f"{owner} has {quantifier} {k} {word} neighbor{'' if k == 1 else 's'}"

    if isinstance(region, ExplicitList):
        names = _names(region, board)
        everyone = k == len(names) and op != "AT_MOST"
        if len(names) == 1 and (none or everyone):
            return _single(names[0], status, holds=everyone)
        if none:
            if len(names) == 2:
                return f"Neither {names[0]} nor {names[1]} is {status_phrase(status)}"
            return f"None of {join_names(names)} {_predicate(status, 2)}"
        if everyone:
            lead = "Both" if len(names) == 2 else "All of"
            return f"{lead} {join_names(names)} {_predicate(status, 2)}"
        return f"{quantifier.capitalize()} {k} of {join_names(names)} {_predicate(status, k)}"

    where = region.describe(board)
    if none:
        return f"There are no {status_noun(status, 2)} in {where}"
    return f"There {_be(k)} {quantifier} {k} {status_noun(status, k)} in {where}"


def parity_sentence(region: Region, board: Board, odd: bool, status: Status = Status.CRIMINAL) -> str:
    """Câu cho số người có trạng thái status trong vùng là lẻ / chẵn"""
    amount = "an odd" if odd else "an even"
    if isinstance(region, Neighbors):
        return f"{_owner(region, board)} has {amount} number of {status_word(status)} neighbors"
    if isinstance(region, ExplicitList):
        names = _names(region, board)
        if len(names) == 1:
            return _single(names[0], status, holds=odd)
        return f"{amount.capitalize()} number of {join_names(names)} {_predicate(status, 2)}"
    return f"There is {amount} number of {status_noun(status, 2)} in {region.describe(board)}"


def one_of_k_sentence(name: str, region: Region, board: Board, k: int, status: Status) -> str:
    """Câu cho 'name là một trong đúng k người có trạng thái status trong vùng'"""
    word = status_word(status)
    if isinstance(region, Neighbors):
        owner = possessive(_owner(region, board))
        if k == 1:
            return f"{name} is {owner} only {word} neighbor"
        return f"{name} is one of {owner} {k} {word} neighbors"
    if k == 1:
        return f"{name} is the only {word} {among(region, board)}"
    return f"{name} is one of the {k} {status_noun(status, k)} {among(region, board)}"