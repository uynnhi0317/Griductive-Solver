"""
Thống kê kích thước mã hóa: số biến chính, biến phụ, mệnh đề
"""

from dataclasses import dataclass

from .cnf import CNF
from .variable_map import VariableMap


@dataclass(frozen=True)
class EncodingStats:
    main_vars: int      # số biến chính đã khai báo (N*N)
    aux_vars: int       # số biến phụ đã cấp
    clauses: int        # số mệnh đề trong CNF (không tính tautology và duplicates)
    unit_clauses: int   # số mệnh đề đơn (1 literal) trong CNF
    max_clause_len: int # độ dài mệnh đề lớn nhất (0 nếu CNF rỗng)

    @property
    def total_vars(self) -> int:
        return self.main_vars + self.aux_vars

    def as_dict(self) -> dict[str, int]:
        """Mapping cố định để ghi CSV"""
        return {
            "main_vars": self.main_vars,
            "aux_vars": self.aux_vars,
            "clauses": self.clauses,
            "unit_clauses": self.unit_clauses,
            "max_clause_len": self.max_clause_len,
        }

    def __str__(self) -> str:
        return (
            f"{self.main_vars} main vars, {self.aux_vars} aux vars, "
            f"{self.clauses} clauses ({self.unit_clauses} unit, max clause length {self.max_clause_len})"
        )


def compute_stats(cnf: CNF, vmap: VariableMap) -> EncodingStats:
    """Thống kê của một CNF đã mã hóa với variable map"""
    if cnf.max_var() > vmap.max_var:
        raise ValueError(f"[EncodingStats]: CNF dùng biến {cnf.max_var()} nhưng Variable Map chỉ khai báo đến {vmap.max_var}")
    
    lengths = [len(clause) for clause in cnf]
    return EncodingStats(
        main_vars=vmap.num_main,
        aux_vars=vmap.num_aux,
        clauses=len(cnf),
        unit_clauses=sum(1 for n in lengths if n == 1),
        max_clause_len=max(lengths, default=0),
    )
