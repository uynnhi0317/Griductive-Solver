"""
Mã hóa ràng buộc đếm sang CNF bằng cách liệt kê tổ hợp trực tiếp (không dùng biến phụ)

Với vùng gồm n literal l_1..l_n (mỗi l_i là "ô i là Criminal"):

+ AT_MOST(k):  mọi tập con k+1 ô không thể cùng là Criminal
               -> với mỗi tập con S có |S| = k+1: (OR_{i in S} ¬l_i)     [C(n, k+1) mệnh đề]
+ AT_LEAST(k): mọi tập con n-k+1 ô phải có ít nhất một Criminal
               -> với mỗi tập con S có |S| = n-k+1: (OR_{i in S} l_i)    [C(n, n-k+1) mệnh đề]
+ EXACTLY(k):  AT_MOST(k) ∧ AT_LEAST(k)

Các hàm ở đây chỉ làm việc với literal (int kiểu DIMACS), không phụ thuộc game/
Kết quả là danh sách mệnh đề thô, CNF.add_clause sẽ chuẩn hóa sau
"""

from itertools import combinations
from math import comb
from typing import Sequence

from .cnf import Clause, Literal


def _check(lits: Sequence[Literal], k: int) -> None:
    if not isinstance(k, int) or isinstance(k, bool):
        raise ValueError(f"[Cardinality]: k phải là số nguyên, nhận được {k!r}")
    for lit in lits:
        if not isinstance(lit, int) or isinstance(lit, bool) or lit == 0:
            raise ValueError(f"[Cardinality]: Literal không hợp lệ: {lit!r}")
    if len({abs(l) for l in lits}) != len(lits):
        raise ValueError("[Cardinality]: Các literal phải thuộc các biến phân biệt")
    if not 0 <= k <= len(lits):
        raise ValueError(f"[Cardinality]: k = {k} ngoài đoạn [0, {len(lits)}]")


def at_most(lits: Sequence[Literal], k: int) -> list[Clause]:
    """Nhiều nhất k literal đúng. k = n thì luôn thỏa nên không sinh mệnh đề"""
    _check(lits, k)
    if k >= len(lits):
        return []
    return [tuple(-l for l in subset) for subset in combinations(lits, k + 1)]


def at_least(lits: Sequence[Literal], k: int) -> list[Clause]:
    """Ít nhất k literal đúng. k = 0 thì luôn thỏa nên không sinh mệnh đề"""
    _check(lits, k)
    n = len(lits)
    if k == 0:
        return []
    return [tuple(subset) for subset in combinations(lits, n - k + 1)]


def exactly(lits: Sequence[Literal], k: int) -> list[Clause]:
    """Đúng k literal đúng"""
    return at_most(lits, k) + at_least(lits, k)


# Số mệnh đề dự kiến (trước khi chuẩn hóa), dùng cho báo cáo và test
def at_most_clause_count(n: int, k: int) -> int:
    return comb(n, k + 1) if k < n else 0


def at_least_clause_count(n: int, k: int) -> int:
    return comb(n, n - k + 1) if k > 0 else 0


def exactly_clause_count(n: int, k: int) -> int:
    return at_most_clause_count(n, k) + at_least_clause_count(n, k)