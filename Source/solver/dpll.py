"""
SAT solver theo thuật toán DPLL

Thành phần:
+ Unit propagation: gán các biến bị ép bởi mệnh đề chỉ còn một literal chưa gán
+ Pure-literal elimination (tùy chọn): Loại bỏ biến có literal chỉ dương hoặc âm
+ Phát hiện conflict: có mệnh đề mà mọi literal đều sai (kể cả mệnh đề rỗng)
+ Chọn biến xác định: biến chưa gán nhỏ nhất trong các mệnh đề chưa thỏa
+ Rẽ nhánh và backtrack: thử giá trị theo thứ tự cố định, hoàn tác bằng trail
+ Assumptions: các literal được coi là đã chọn từ đầu (không tính decision)
"""

import time
from dataclasses import dataclass
from typing import Iterable, Mapping

from logic.cnf import CNF, Clause, make_clause

from .stats import SolverStats

_VALUE_ORDER = (False, True)


class SolverTimeout(Exception):
    """Solver vượt quá time_limit, stats giữ số liệu tính đến lúc dừng"""

    def __init__(self, stats: SolverStats) -> None:
        super().__init__(f"[DPLL]: Hết thời gian giới hạn ({stats.runtime:.3f}s, {stats.decisions} decisions)")
        self.stats = stats


@dataclass(frozen=True)
class SolveResult:
    """Kết quả thu được từ Solver"""
    sat: bool
    model: dict[int, bool] | None
    stats: SolverStats


def check_model(cnf: CNF, model: Mapping[int, bool]) -> bool:
    """Kiểm tra model có thỏa mọi mệnh đề không"""
    for clause in cnf:
        satisfied = False
        for lit in clause:
            var = abs(lit)
            if var not in model:
                raise ValueError(f"[DPLL]: Model thiếu biến {var}")
            if model[var] == (lit > 0):
                satisfied = True
                break
        if not satisfied:
            return False
    return True


class _Solver:
    def __init__(self, clauses: tuple[Clause, ...], deadline: float | None, start: float, pure_literal: bool) -> None:
        self.clauses = clauses
        self.assignment: dict[int, bool] = {}
        self.stats = SolverStats()
        self.deadline = deadline
        self.start = start
        self.pure_literal = pure_literal

    def assign(self, var: int, value: bool) -> None:
        """Gán giá trị cho một biến"""
        self.assignment[var] = value

    def undo_to(self, mark: int) -> None:
        """Hoàn tác mọi phép gán sau mốc mark"""
        if not isinstance(mark, int) or isinstance(mark, bool):
            raise TypeError(f"[DPLL]: Mark phải là số nguyên, nhận được {mark!r}")
        
        if not 0 <= mark <= len(self.assignment):
            raise ValueError(f"[DPLL]: Mark phải nằm giữa 0 và độ dài assignment ({len(self.assignment)}), nhận được {mark!r}")
        
        while len(self.assignment) > mark:
            self.assignment.popitem()

    def check_time(self) -> None:
        """Hàm kiểm tra thời gian đã vượt deadline"""
        if self.deadline is not None and time.perf_counter() > self.deadline:
            self.stats.runtime = time.perf_counter() - self.start
            raise SolverTimeout(self.stats)

    def propagate(self) -> bool:
        """Unit propagation đến khi không còn thay đổi"""
        assignment = self.assignment
        changed = True
        while changed:
            changed = False
            for clause in self.clauses:
                unit = 0    # Biến được gán nếu propagate được
                free = 0    # Số biến chưa được gán trong 1 mệnh đề đang xét
                satisfied = False
                for lit in clause:
                    value = assignment.get(abs(lit))
                    # Nếu biến chưa được gán, thì đánh dấu free
                    # Nếu biến đã được gán làm cho literal True thì mệnh đề SAT
                    if value is None:
                        free += 1
                        unit = lit
                    elif value == (lit > 0):
                        satisfied = True
                        break
                # Nếu mệnh đề SAT, tiếp tục xét các mệnh đề khác
                if satisfied:
                    continue

                # Trường hợp mệnh đề UNSAT với các biến đã được gán

                # Nếu số biến trong mệnh đề đã được gán hết giá trị -> conflict
                if free == 0:
                    return False
                # Nếu còn 1 biến trong mệnh đề chưa được gán -> có thể propagate biến này
                if free == 1:
                    self.assign(abs(unit), unit > 0)
                    self.stats.propagations += 1
                    changed = True
        return True

    def eliminate_pure_literals(self) -> None:
        """Pure-litaral elimination nếu chỉ có positive hoặc negative literal của 1 biến"""
        assignment = self.assignment
        while True:
            seen: dict[int, int] = {}
            for clause in self.clauses:
                free: list[int] = []
                satisfied = False

                # Lấy các biến chưa được gán trong mệnh đề chưa SAT
                for lit in clause:
                    value = assignment.get(abs(lit))
                    if value is None:
                        free.append(lit)
                    elif value == (lit > 0):
                        satisfied = True
                        break

                if satisfied:
                    continue

                # Xét các biến chưa được gán của mệnh đề chưa SAT
                # Biểu diễn trạng thái tồn tại dấu literal của biến theo số nhị phân 2-bit ab
                # Nếu a = 1 thì tồn tại literal âm của biến, nếu b = 1 thì tồn tại literal dương của biến
                for lit in free:
                    var = abs(lit)
                    seen[var] = seen.get(var, 0) | (1 if lit > 0 else 2)

            pure = sorted(var for var, mask in seen.items() if mask != 3)
            if not pure:
                return

            # Thực hiện gán True cho biến nếu literal dương; False nếu literal âm
            for var in pure:
                self.assign(var, seen[var] == 1)
                self.stats.pure_literals += 1

    def pick_variable(self) -> int | None:
        """Biến chưa gán nhỏ nhất trong các mệnh đề UNSAT còn tiềm năng SAT"""
        assignment = self.assignment
        best: int | None = None
        for clause in self.clauses:
            candidate: int | None = None
            satisfied = False
            for lit in clause:
                var = abs(lit)
                value = assignment.get(var)
                if value is None:
                    if candidate is None or var < candidate:
                        candidate = var
                elif value == (lit > 0):
                    satisfied = True
                    break

            if satisfied or candidate is None:
                continue

            if best is None or candidate < best:
                best = candidate
        return best

    def dpll(self) -> bool:
        """
        Solver DPLL:
        + Trả True nếu SAT
        + Trả False nếu UNSAT
        """
        mark = len(self.assignment)
        # Unit propagation
        if not self.propagate():
            # Conflict: Trả về assignment như ban đầu và rẻ nhánh
            self.undo_to(mark)
            return False

        # Pure-literal elimination
        if self.pure_literal:
            self.eliminate_pure_literals()

        # Propagate đã handle trường hợp mệnh đề UNSAT với tất cả biến
        # Nếu không còn biến chưa gán, CNF thỏa mãn
        var = self.pick_variable()
        if var is None:
            return True
        
        
        # Nếu còn biến chưa gán, vẫn còn clause chưa thỏa mãn
        # Khi đó decide cho biến var 2 trường hợp True, False
        self.check_time()
        for value in _VALUE_ORDER:
            decision_mark = len(self.assignment)
            self.stats.decisions += 1
            self.assign(var, value)
            if self.dpll():
                return True
            # Nếu như decision không cho CNF SAT, hoàn tác các giá trị gán
            self.undo_to(decision_mark)
            self.stats.backtracks += 1

        self.undo_to(mark)
        return False


def solve(
    cnf: CNF,
    num_vars: int | None = None,
    assumptions: Iterable[int] = (),
    time_limit: float | None = None,
    pure_literal: bool = True
) -> SolveResult:
    """
    Giải CNF bằng DPLL:
    + num_vars: số biến cần có trong model
    + assumptions: các literal đã biết giá trị ban đầu
    + time_limit(s): deadline cho solver
    + pure_literal: cần thêm bước cải tiến pure-literal elimination không
    """
    if num_vars is not None and (isinstance(num_vars, bool) or not isinstance(num_vars, int) or num_vars < 0):
        raise ValueError(f"[DPLL]: num_vars phải là số nguyên >= 0, nhận được {num_vars!r}")
    
    if time_limit is not None and (isinstance(time_limit, bool) or not isinstance(time_limit, (int, float)) or time_limit <= 0):
        raise ValueError(f"[DPLL]: time_limit phải là số > 0, nhận được {time_limit!r}")

    if not isinstance(pure_literal, bool):
        raise ValueError(f"[DPLL]: pure_literal phải là bool, nhận được {pure_literal!r}")

    # Chuẩn hóa assumptions
    assumed = make_clause(assumptions)
    n = max(num_vars or 0, cnf.max_var(), max((abs(lit) for lit in (assumed or ())), default=0))

    start = time.perf_counter()
    deadline = None if time_limit is None else start + time_limit
    solver = _Solver(cnf.clauses, deadline, start, pure_literal)
    sat = False
    try:
        if assumed is not None and not cnf.has_empty_clause():
            for lit in assumed:
                solver.assign(abs(lit), lit > 0)
            sat = solver.dpll()
    finally:
        solver.stats.runtime = time.perf_counter() - start

    model = {v: solver.assignment.get(v, False) for v in range(1, n + 1)} if sat else None
    return SolveResult(sat, model, solver.stats)