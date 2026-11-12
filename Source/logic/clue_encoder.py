"""
Chuyển clue có cấu trúc sang CNF.
Dispatch theo loại clue.
Encoder không đọc đáp án ẩn: chỉ dùng clue, board và VariableMap.
"""

from typing import Callable, Iterable

from game.clue import (
    AtLeastClue,
    AtMostClue,
    Clue,
    DifferentClue,
    ExactlyClue,
    FactClue,
    SameClue,
)

from .cardinality import at_least, at_most, exactly
from .cnf import CNF
from .variable_map import VariableMap

# (clue, vmap) sang CNF. Encoder giả định clue đã được validate
Encoder = Callable[[Clue, VariableMap], CNF]

_ENCODERS: dict[type[Clue], Encoder] = {}


def register_encoder(*clue_classes: type[Clue]) -> Callable[[Encoder], Encoder]:
    """Decorator đăng ký hàm mã hóa cho một hay nhiều loại clue"""
    if not clue_classes:
        raise TypeError("[ClueEncoder]: register_encoder cần ít nhất một loại clue")

    def decorator(fn: Encoder) -> Encoder:
        for clue_cls in clue_classes:
            if not (isinstance(clue_cls, type) and issubclass(clue_cls, Clue)):
                raise TypeError(f"[ClueEncoder]: {clue_cls!r} phải là lớp con của Clue")
            if clue_cls in _ENCODERS:
                raise ValueError(f"[ClueEncoder]: Đã có encoder cho {clue_cls.__name__}")
            _ENCODERS[clue_cls] = fn
        return fn

    return decorator


def _find_encoder(clue: Clue) -> Encoder:
    for cls in type(clue).__mro__:
        encoder = _ENCODERS.get(cls)
        if encoder is not None:
            return encoder
    raise TypeError(f"[ClueEncoder]: Chưa hỗ trợ mã hóa loại clue {type(clue).__name__}")


# Encoders
@register_encoder(FactClue)
def _encode_fact(clue: FactClue, vmap: VariableMap) -> CNF:
    # Ci hoặc ¬Ci: một mệnh đơn
    return CNF([[vmap.status_literal(clue.cell, clue.status)]])


@register_encoder(SameClue)
def _encode_same(clue: SameClue, vmap: VariableMap) -> CNF:
    # Ci <-> Cj  ==  (¬Ci ∨ Cj) ∧ (Ci ∨ ¬Cj)
    a, b = vmap.var(clue.a), vmap.var(clue.b)
    return CNF([[-a, b], [a, -b]])


@register_encoder(DifferentClue)
def _encode_different(clue: DifferentClue, vmap: VariableMap) -> CNF:
    # Ci xor Cj  ==  (Ci ∨ Cj) ∧ (¬Ci ∨ Cj)
    a, b = vmap.var(clue.a), vmap.var(clue.b)
    return CNF([[a, b], [-a, -b]])


def _region_literals(clue, vmap: VariableMap) -> list[int]:
    cells = clue.region.cells(vmap.board)
    return [vmap.literal(cell) for cell in cells]


@register_encoder(ExactlyClue)
def _encode_exactly(clue: ExactlyClue, vmap: VariableMap) -> CNF:
    return CNF(exactly(_region_literals(clue, vmap), clue.k))


@register_encoder(AtLeastClue)
def _encode_at_least(clue: AtLeastClue, vmap: VariableMap) -> CNF:
    return CNF(at_least(_region_literals(clue, vmap), clue.k))


@register_encoder(AtMostClue)
def _encode_at_most(clue: AtMostClue, vmap: VariableMap) -> CNF:
    return CNF(at_most(_region_literals(clue, vmap), clue.k))


# API công khai
def encode_clue(clue: Clue, vmap: VariableMap) -> CNF:
    """Validate clue với board của vmap rồi mã hóa sang CNF mới"""
    if not isinstance(clue, Clue):
        raise TypeError(f"[ClueEncoder]: clue phải là thể hiện của Clue, nhận được {clue!r}")
    clue.validate(vmap.board)
    return _find_encoder(clue)(clue, vmap)


def encode_clues(clues: Iterable[Clue], vmap: VariableMap) -> CNF:
    """Mã hóa nhiều clue và gộp thành một CNF (hội của các CNF con)"""
    result = CNF()
    for clue in clues:
        result.extend(encode_clue(clue, vmap))
    return result