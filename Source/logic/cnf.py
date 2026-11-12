"""
Kiểu dữ liệu CNF dùng chung giữa logic/ và solver/
Literal theo kiểu DIMACS: số nguyên khác 0, dương là biến, âm là phủ định của biến
"""

from typing import Iterable, Iterator

Literal = int
Clause = tuple[Literal, ...]


def make_clause(literals: Iterable[Literal]) -> Clause | None:
    """
    Chuẩn hóa một mệnh đề: loại literal trùng, sắp theo chỉ số biến
    """
    lits = list(literals)
    for lit in lits:
        if not isinstance(lit, int) or isinstance(lit, bool):
            raise ValueError(f"[CNF]: Literal phải là số nguyên, nhận được {lit!r}")
        if lit == 0:
            raise ValueError("[CNF]: Literal không được bằng 0 (0 là dấu kết thúc mệnh đề trong DIMACS)")

    # Loại literal trùng
    unique = set(lits)

    # Nếu tồn tại 2 literal đối nghịch nhau thì clause vô nghĩa (clause luôn bằng True)
    if any(-lit in unique for lit in unique):
        return None
    
    return tuple(sorted(unique, key=lambda x: (abs(x), x)))


class CNF:
    """
    Dạng chuẩn tắc hội CNF gồm hội các mệnh đề

    + Mệnh đề rỗng được giữ lại: nó có nghĩa là UNSAT
    + Tautology bị bỏ qua và được đếm trong tautologies_skipped
    + Duplicates bị bỏ qua và được đếm trong duplicates_skipped
    """

    def __init__(self, clauses: Iterable[Iterable[Literal]] = ()) -> None:
        self._clauses: dict[Clause, None] = {}
        self._max_var = 0
        self._has_empty = False
        self.tautologies_skipped = 0
        self.duplicates_skipped = 0
        self.add_clauses(clauses)

    def add_clause(self, literals: Iterable[Literal]) -> None:
        """Thêm một mệnh đề"""
        clause = make_clause(literals)

        # Mệnh đề luôn bằng True, không có đóng góp cho CNF (tautology)
        if clause is None:
            self.tautologies_skipped += 1
            return
        
        self._append(clause)

    def add_clauses(self, clauses: Iterable[Iterable[Literal]]) -> None:
        """Thêm nhiều mệnh đề"""
        for clause in clauses:
            self.add_clause(clause)

    def extend(self, other: "CNF") -> None:
        """Thêm toàn bộ mệnh đề của một CNF khác"""
        for clause in other:
            self._append(clause)

        self.tautologies_skipped += other.tautologies_skipped
        self.duplicates_skipped += other.duplicates_skipped

    def copy(self) -> "CNF":
        """Bản sao CNF độc lập"""
        new = CNF()
        new._clauses = dict(self._clauses)
        new._max_var = self._max_var
        new._has_empty = self._has_empty
        new.tautologies_skipped = self.tautologies_skipped
        new.duplicates_skipped = self.duplicates_skipped
        return new

    @property
    def clauses(self) -> tuple[Clause, ...]:
        """Các mệnh đề theo thứ tự thêm vào"""
        return tuple(self._clauses)

    def max_var(self) -> int:
        """Biến số lớn nhất xuất hiện trong CNF"""
        return self._max_var

    def variables(self) -> list[int]:
        """Các biến xuất hiện trong CNF, tăng dần"""
        return sorted({abs(lit) for clause in self._clauses for lit in clause})

    def has_empty_clause(self) -> bool:
        """CNF chứa mệnh đề rỗng thì chắc chắn UNSAT"""
        return self._has_empty

    def to_dimacs(self, num_vars: int | None = None) -> str:
        """Xuất định dạng DIMACS"""
        n = max(self._max_var, num_vars or 0)
        lines = [f"p cnf {n} {len(self._clauses)}"]
        lines.extend(" ".join(map(str, clause + (0,))) for clause in self._clauses)
        return "\n".join(lines) + "\n"

    def __len__(self) -> int:
        return len(self._clauses)

    def __iter__(self) -> Iterator[Clause]:
        return iter(self._clauses)

    def __repr__(self) -> str:
        return f"CNF(clauses={len(self._clauses)}, max_var={self._max_var})"

    def _append(self, clause: Clause) -> None:
        """Thêm mệnh đề đã chuẩn hóa vào CNF, bỏ qua nếu đã tồn tại"""
        if clause in self._clauses:
            self.duplicates_skipped += 1
            return
        self._clauses[clause] = None
        if clause:
            self._max_var = max(self._max_var, abs(clause[-1]))
        else:
            self._has_empty = True
