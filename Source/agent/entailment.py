"""
Phân loại tất suy cho từng nhân vật chưa giải tại bước t

Với biến chính C_i của ô i và cơ sở tri thức KB_t:
+ KB_t |= C_i   <=>  KB_t ∧ ¬C_i UNSAT  -> CRIMINAL
+ KB_t |= ¬C_i  <=>  KB_t ∧ C_i UNSAT   -> INNOCENT
+ Cả hai đều SAT                        -> UNKNOWN (không được đoán)
+ Bản thân KB_t UNSAT                   -> INCONSISTENT

Quy ước:
+ Chỉ đọc PublicState (qua build_kb), không bao giờ nhận PuzzleFull hay đáp án ẩn
+ Literal tạm thời (¬C_i hoặc C_i) được truyền vào solver dưới dạng assumptions,
  KB_t không bị sửa giữa các truy vấn
+ Mỗi lần gọi solve() là một SAT query, được ghi lại kèm SolverStats để làm trace/benchmark
+ Kiểm tra KB_t SAT đúng một lần cho mỗi state, sau đó mỗi ô tốn 1 hoặc 2 query
+ Duyệt ô chưa giải theo row-major nên kết quả luôn xác định

Tái sử dụng model:
+ Mọi model của KB_t ∧ (literal) cũng là model của KB_t
+ Nếu đã có một model của KB_t với C_i = False thì KB_t ∧ ¬C_i chắc chắn SAT, không cần hỏi lại
  (tương tự với C_i = True và KB_t ∧ C_i)
+ ModelPool gom các model thu được để bỏ qua những truy vấn đã biết chắc là SAT
+ Chỉ bỏ được truy vấn SAT, không bao giờ bỏ truy vấn có thể UNSAT nên kết quả không đổi
"""

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from game.cell import Cell
from game.character import Status
from game.public_state import PublicState
from logic.cnf import CNF
from logic.kb_builder import KnowledgeBase, build_kb
from solver.dpll import solve
from solver.stats import SolverStats


class Verdict(Enum):
    """Kết quả phân loại một nhân vật dựa trên KB_t"""
    CRIMINAL = "CRIMINAL"
    INNOCENT = "INNOCENT"
    UNKNOWN = "UNKNOWN"
    INCONSISTENT = "INCONSISTENT"

    @property
    def is_forced(self) -> bool:
        """Verdict bị ép buộc (được phép nộp cho engine)"""
        return self in (Verdict.CRIMINAL, Verdict.INNOCENT)

    def to_status(self) -> Status:
        """Đổi verdict ép buộc sang Status, chỉ hợp lệ với CRIMINAL / INNOCENT"""
        if not self.is_forced:
            raise ValueError(f"[Entailment]: {self.value} không phải verdict ép buộc")
        return Status.CRIMINAL if self is Verdict.CRIMINAL else Status.INNOCENT


@dataclass(frozen=True)
class SatQuery:
    label: str                  # mô tả truy vấn
    assumption: int | None      # literal tạm thời, None nếu chỉ kiểm tra KB
    sat: bool
    stats: SolverStats
    model: Mapping[int, bool] | None = field(default=None, repr=False, compare=False)


class ModelPool:
    """
    Tập các model đã biết của KB_t
    """

    def __init__(self) -> None:
        self._seen: dict[bool, set[int]] = {True: set(), False: set()}
        self.models_added = 0

    def add(self, model: Mapping[int, bool] | None) -> None:
        """Thêm một model"""
        if model is None:
            return
        for var, value in model.items():
            self._seen[value].add(var)
        self.models_added += 1

    def has(self, var: int, value: bool) -> bool:
        return var in self._seen[value]


@dataclass(frozen=True)
class VarClassification:
    """Kết quả phân loại một biến, kèm các truy vấn đã dùng và số truy vấn được bỏ qua"""
    verdict: Verdict
    queries: tuple[SatQuery, ...]
    skipped: int = 0


@dataclass(frozen=True)
class CellClassification:
    """Kết quả phân loại một ô chưa giải"""
    cell: Cell
    verdict: Verdict
    queries: tuple[SatQuery, ...]
    skipped: int = 0    # số truy vấn bỏ qua nhờ ModelPool

    @property
    def sat_queries(self) -> int:
        return len(self.queries)


@dataclass(frozen=True)
class EntailmentReport:
    """Kết quả phân loại toàn bộ ô chưa giải tại bước t"""
    consistent: bool
    results: Mapping[Cell, CellClassification]   # theo row-major
    consistency_query: SatQuery
    kb: KnowledgeBase
    stats: SolverStats = field(compare=False)    # cộng dồn mọi truy vấn

    @property
    def sat_queries(self) -> int:
        """Tổng số SAT query, gồm cả truy vấn kiểm tra KB"""
        return 1 + sum(r.sat_queries for r in self.results.values())

    @property
    def skipped_queries(self) -> int:
        """Tổng số truy vấn tránh được nhờ tái sử dụng model"""
        return sum(r.skipped for r in self.results.values())

    def forced(self) -> tuple[CellClassification, ...]:
        """Các ô có verdict ép buộc, theo row-major"""
        return tuple(r for r in self.results.values() if r.verdict.is_forced)

    def first_forced(self) -> CellClassification | None:
        """Ô ép buộc đầu tiên theo row-major, None nếu không có"""
        return next((r for r in self.results.values() if r.verdict.is_forced), None)


def _query(cnf: CNF, num_vars: int, assumption: int | None, label: str,
           time_limit: float | None) -> SatQuery:
    """Gọi solver một lần; SolverTimeout được để nguyên cho tầng trên xử lý"""
    assumptions = () if assumption is None else (assumption,)
    result = solve(cnf, num_vars=num_vars, assumptions=assumptions, time_limit=time_limit)
    return SatQuery(label, assumption, result.sat, result.stats, result.model)


def classify_var(
    cnf: CNF,
    var: int,
    num_vars: int | None = None,
    time_limit: float | None = None,
    check_consistency: bool = True,
    name: str | None = None,
    pool: ModelPool | None = None,
) -> VarClassification:
    """
    Phân loại một biến trên CNF bất kỳ
    + check_consistency=False khi nơi gọi đã chắc chắn CNF SAT
    + name: tên hiển thị của biến trong label truy vấn
    + pool: nếu có, dùng model đã biết để bỏ qua truy vấn chắc chắn SAT,
      và thêm model của mọi truy vấn SAT mới vào pool
    """
    if isinstance(var, bool) or not isinstance(var, int) or var <= 0:
        raise ValueError(f"[Entailment]: Biến phải là số nguyên dương, nhận được {var!r}")

    n = max(num_vars or 0, cnf.max_var(), var)
    name = name or f"x{var}"
    queries: list[SatQuery] = []
    skipped = 0

    def ask(assumption: int | None, label: str) -> SatQuery:
        q = _query(cnf, n, assumption, label, time_limit)
        queries.append(q)
        if pool is not None:
            pool.add(q.model)
        return q

    def known_sat(value: bool) -> bool:
        return pool is not None and pool.has(var, value)

    # Bản thân KB có thỏa được không
    if check_consistency:
        if not ask(None, "KB").sat:
            return VarClassification(Verdict.INCONSISTENT, tuple(queries), skipped)

    # Giả sử vô tội: KB ∧ ¬C_i UNSAT thì C_i bị ép là True
    # Đã có model với C_i = False thì truy vấn này chắc chắn SAT, bỏ qua
    if known_sat(False):
        skipped += 1
    elif not ask(-var, f"KB ∧ ¬{name}").sat:
        return VarClassification(Verdict.CRIMINAL, tuple(queries), skipped)

    # Giả sử tội phạm: KB ∧ C_i UNSAT thì C_i bị ép là False
    if known_sat(True):
        skipped += 1
    elif not ask(var, f"KB ∧ {name}").sat:
        return VarClassification(Verdict.INNOCENT, tuple(queries), skipped)

    # Cả hai giả sử đều thỏa được: chưa đủ thông tin
    return VarClassification(Verdict.UNKNOWN, tuple(queries), skipped)


class EntailmentChecker:
    """
    Bộ phân loại cho một PublicState cố định
    + KB_t được dựng một lần khi khởi tạo
    + Kết quả kiểm tra KB_t SAT được nhớ lại, dùng chung cho mọi ô
    + reuse_models=True: các ô dùng chung một ModelPool;
      tắt đi để đo số truy vấn gốc khi làm thực nghiệm
    """

    def __init__(self, state: PublicState, time_limit: float | None = None,
                 reuse_models: bool = True) -> None:
        if not isinstance(reuse_models, bool):
            raise ValueError(f"[Entailment]: reuse_models phải là bool, nhận được {reuse_models!r}")
        if not isinstance(state, PublicState):
            raise TypeError(f"[Entailment]: Chỉ nhận PublicState, nhận được {type(state).__name__}")
        self._state = state
        self._time_limit = time_limit
        self._kb = build_kb(state)
        self._consistency: SatQuery | None = None
        self._pool = ModelPool() if reuse_models else None

    @property
    def kb(self) -> KnowledgeBase:
        return self._kb

    def consistency_query(self) -> SatQuery:
        """Truy vấn KB_t"""
        if self._consistency is None:
            self._consistency = _query(self._kb.cnf, self._kb.num_vars, None, "KB", self._time_limit)
            if self._pool is not None:
                self._pool.add(self._consistency.model)
        return self._consistency

    def is_consistent(self) -> bool:
        return self.consistency_query().sat

    def classify(self, cell: Cell) -> CellClassification:
        """Phân loại một ô chưa giải (không tính truy vấn kiểm tra KB vào kết quả của ô)"""
        if not self._state.board.contains(cell):
            raise ValueError(f"[Entailment]: Ô {cell!r} ngoài board")
        if self._state.is_known(cell):
            raise ValueError(f"[Entailment]: Ô {cell.label} đã có verdict, không cần phân loại")

        if not self.is_consistent():
            return CellClassification(cell, Verdict.INCONSISTENT, ())

        result = classify_var(
            self._kb.cnf, self._kb.var(cell),
            num_vars=self._kb.num_vars, time_limit=self._time_limit,
            check_consistency=False, name=f"C_{cell.label}", pool=self._pool,
        )
        return CellClassification(cell, result.verdict, result.queries, result.skipped)

    def classify_all(self) -> EntailmentReport:
        """Phân loại mọi ô chưa giải theo row-major"""
        consistency = self.consistency_query()
        results = {cell: self.classify(cell) for cell in self._state.unsolved_cells()}

        total = SolverStats()
        total.merge(consistency.stats)
        for r in results.values():
            for q in r.queries:
                total.merge(q.stats)

        return EntailmentReport(
            consistent=consistency.sat,
            results=MappingProxyType(results),
            consistency_query=consistency,
            kb=self._kb,
            stats=total,
        )


def classify_state(state: PublicState, time_limit: float | None = None,
                   reuse_models: bool = True) -> EntailmentReport:
    """Phân loại toàn bộ ô chưa giải của một state"""
    return EntailmentChecker(state, time_limit, reuse_models).classify_all()
    