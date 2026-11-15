"""
Chuyển clue có cấu trúc sang CNF.
Dispatch theo loại clue.
Encoder không đọc đáp án ẩn: chỉ dùng clue, board và VariableMap.
"""

from itertools import combinations
from typing import Callable, Iterable

from game.character import Status

from game.clue import (
    AtLeastClue,
    AtMostClue,
    Clue,
    DifferentClue,
    ExactlyClue,
    FactClue,
    SameClue,
    ConnectedClue,
    IfThenClue,
    NoAdjacentClue,
    OneOfKClue,
    ParityClue,
    adjacent_pairs,
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
    # Ci xor Cj  ==  (Ci ∨ Cj) ∧ (¬Ci ∨ ¬Cj)
    a, b = vmap.var(clue.a), vmap.var(clue.b)
    return CNF([[a, b], [-a, -b]])


def _region_literals(clue, vmap: VariableMap, status: Status = Status.CRIMINAL) -> list[int]:
    """Literal ô có trạng thái status cho từng ô trong vùng của clue, theo thứ tự của vùng"""
    return [vmap.status_literal(cell, status) for cell in clue.region.cells(vmap.board)]


@register_encoder(ExactlyClue)
def _encode_exactly(clue: ExactlyClue, vmap: VariableMap) -> CNF:
    return CNF(exactly(_region_literals(clue, vmap), clue.k))


@register_encoder(AtLeastClue)
def _encode_at_least(clue: AtLeastClue, vmap: VariableMap) -> CNF:
    return CNF(at_least(_region_literals(clue, vmap), clue.k))


@register_encoder(AtMostClue)
def _encode_at_most(clue: AtMostClue, vmap: VariableMap) -> CNF:
    return CNF(at_most(_region_literals(clue, vmap), clue.k))


# Extension encoders (T10)
# Mọi clue mở rộng làm việc trên literal "ô có trạng thái status" (+C_i nếu CRIMINAL, ¬C_i nếu INNOCENT),
# nên cùng một công thức CNF dùng được cho cả hai trạng thái
def _xor_definition(t: int, a: int, b: int) -> list[tuple[int, ...]]:
    """Tseitin cho t <-> (a XOR b): 4 mệnh đề"""
    return [(-t, a, b), (-t, -a, -b), (t, -a, b), (t, a, -b)]


@register_encoder(ParityClue)
def _encode_parity(clue: ParityClue, vmap: VariableMap) -> CNF:
    """
    Chuỗi XOR Tseitin, dùng biến phụ:
        p_1 = l_1,  p_i = p_{i-1} XOR l_i  (p_i là biến phụ, i = 2..n-1)
    Bước cuối không cần biến phụ: ép trực tiếp p_{n-1} XOR l_n = (parity == ODD)
    -> n-2 biến phụ, 4(n-2) + 2 mệnh đề (n >= 2)
    """
    lits = _region_literals(clue, vmap, clue.status)
    want_odd = clue.parity == "ODD"
    if not lits:
        return CNF([[]]) if want_odd else CNF()     # validate đã chặn ODD trên vùng rỗng
    if len(lits) == 1:
        return CNF([[lits[0] if want_odd else -lits[0]]])

    cnf = CNF()
    acc = lits[0]
    for i, lit in enumerate(lits[1:-1], start=2):
        t = vmap.new_aux(f"{clue.kind}:{clue.region.describe()}:p{i}")
        cnf.add_clauses(_xor_definition(t, acc, lit))
        acc = t

    # acc XOR last == want_odd: ODD <-> acc khác last, EVEN <-> acc bằng last
    last = lits[-1] if want_odd else -lits[-1]
    cnf.add_clauses([[acc, last], [-acc, -last]])
    return cnf


@register_encoder(ConnectedClue)
def _encode_connected(clue: ConnectedClue, vmap: VariableMap) -> CNF:
    # Cấm mẫu S ... (không S) ... S trên đường: với mọi i < j < k: (¬l_i ∨ l_j ∨ ¬l_k)
    lits = _region_literals(clue, vmap, clue.status)   # Row/Column trả ô theo đúng thứ tự trên đường
    return CNF([-a, b, -c] for a, b, c in combinations(lits, 3))


@register_encoder(NoAdjacentClue)
def _encode_no_adjacent(clue: NoAdjacentClue, vmap: VariableMap) -> CNF:
    # Mỗi cặp ô kề nhau trong vùng không thể cùng có trạng thái status: (¬l_a ∨ ¬l_b)
    lit = lambda cell: vmap.status_literal(cell, clue.status)
    return CNF([-lit(a), -lit(b)] for a, b in adjacent_pairs(clue.region.cells(vmap.board)))


@register_encoder(OneOfKClue)
def _encode_one_of_k(clue: OneOfKClue, vmap: VariableMap) -> CNF:
    # l_cell ∧ EXACTLY(k) trên các literal "có trạng thái status" của vùng
    cnf = CNF([[vmap.status_literal(clue.cell, clue.status)]])
    cnf.add_clauses(exactly(_region_literals(clue, vmap, clue.status), clue.k))
    return cnf


@register_encoder(IfThenClue)
def _encode_if_then(clue: IfThenClue, vmap: VariableMap) -> CNF:
    """
    g -> φ  ==  AND_{c in CNF(φ)} (¬g ∨ c)
    Vẫn đúng khi CNF(φ) có biến phụ (vd. PARITY): khi g sai, biến phụ chỉ xuất hiện
    trong các mệnh đề đã thỏa nên tự do -> tương đương thỏa mãn trên biến chính
    """
    guard = vmap.status_literal(clue.cell, clue.status)
    inner = _find_encoder(clue.then_clue)(clue.then_clue, vmap)  # then_clue đã được validate cùng clue cha
    return CNF((-guard, *c) for c in inner)

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