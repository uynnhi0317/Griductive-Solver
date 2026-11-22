"""
Logic Agent: vòng suy diễn không đoán trên public state

Vòng lặp tại bước t:
1. Phân loại mọi ô chưa giải trên KB_t
2. KB_t UNSAT                      -> dừng, INCONSISTENT
3. Không ô nào bị ép buộc          -> dừng, AMBIGUOUS
4. Chọn ô ép buộc đầu tiên theo row-major, nộp verdict cho GameEngine
5. Engine chấp nhận -> thẻ lật, clue mới lộ, state mới cho KB_{t+1}; lặp lại tới khi SOLVED

Ranh giới thông tin:
+ Agent chỉ đọc engine.state (PublicState: clue đã lộ và verdict đã chứng minh)
và dùng engine.submit_verdict để xin lật thẻ; không chạm tới đáp án ẩn
+ Hint chỉ nhận PublicState nên không thể đọc đáp án ẩn

Hint:
+ Chọn ô ép buộc đầu tiên theo row-major
+ Tìm một tập clue đã lộ tối thiểu vẫn đủ ép buộc verdict đó:
lần lượt thử bỏ từng clue, nếu KB còn lại vẫn suy ra được verdict thì bỏ hẳn clue đó.
Verdict đã chứng minh luôn được giữ dưới dạng unit clause
+ Tập clue thu được là tập bỏ thêm clue nào cũng không suy ra được nữa, không nhất thiết nhỏ nhất về số lượng
"""

from dataclasses import dataclass
from typing import Iterator

from engine.game_engine import GameEngine, VerdictOutcome
from game.cell import Cell
from game.clue import Clue
from game.public_state import PublicState
from logic.clue_encoder import encode_clue
from logic.cnf import CNF
from logic.variable_map import VariableMap
from solver.dpll import SolverTimeout, solve

from .entailment import EntailmentReport, Verdict, classify_state
from .trace import AgentStatus, DeductionTrace, TraceStep


class AgentInvariantError(RuntimeError):
    """Engine từ chối một verdict mà agent đã chứng minh là ép buộc (agent và engine bất đồng)"""


@dataclass(frozen=True)
class Hint:
    """Gợi ý cho bước kế tiếp"""
    cell: Cell                  # nhân vật mục tiêu
    verdict: Verdict            # CRIMINAL hoặc INNOCENT
    clue_ids: tuple[str, ...]   # tập clue đã lộ tối thiểu đủ để suy ra verdict


class LogicAgent:
    """
    Agent suy diễn tự động trên một GameEngine
    + time_limit: giới hạn giây cho mỗi SAT query của agent (None = không giới hạn)
    + reuse_models: dùng ModelPool để bỏ qua truy vấn chắc chắn SAT (tắt để đo số truy vấn gốc)
    + Mỗi lần step() nộp đúng một verdict; run() lặp step() tới trạng thái kết thúc
    + Sau engine.restart() cần gọi agent.reset() để bắt đầu trace mới
    """

    def __init__(self, engine: GameEngine, time_limit: float | None = None, reuse_models: bool = True) -> None:
        """Gắn agent vào engine, trace bắt đầu từ state hiện tại"""
        if not isinstance(engine, GameEngine):
            raise TypeError(f"[LogicAgent]: Cần GameEngine, nhận được {type(engine).__name__}")
        self._engine = engine
        self._time_limit = time_limit
        self._reuse_models = reuse_models
        self._trace = self._new_trace()

    # Thông tin

    @property
    def state(self) -> PublicState:
        """Public state hiện tại"""
        return self._engine.state

    @property
    def trace(self) -> DeductionTrace:
        """Trace của lần chạy hiện tại"""
        return self._trace

    @property
    def status(self) -> AgentStatus:
        """Trạng thái hiện tại của agent"""
        return self._trace.status

    def reset(self) -> None:
        """Bắt đầu trace mới từ state hiện tại của engine"""
        self._trace = self._new_trace()

    def analyze(self) -> EntailmentReport:
        """Phân loại mọi ô chưa giải trên state hiện tại"""
        return classify_state(self.state, self._time_limit, self._reuse_models)

    def hint(self) -> Hint | None:
        """Gợi ý ô suy ra được tiếp theo trên state hiện tại, None nếu không có"""
        return find_hint(self.state, self._time_limit)

    # Vòng suy diễn

    def step(self) -> TraceStep | None:
        """
        Thực hiện một bước suy diễn
        + Trả về TraceStep nếu đã nộp một verdict ép buộc
        + Trả về None nếu đã ở trạng thái kết thúc
        """
        if self._trace.status.is_terminal:
            return None
        state = self.state
        if state.is_solved():
            return self._finish(AgentStatus.SOLVED)

        try:
            report = self.analyze()
        except SolverTimeout as exc:
            self._trace.final_stats.merge(exc.stats)
            return self._finish(AgentStatus.TIMEOUT)

        if not report.consistent:
            self._record_final(report)
            return self._finish(AgentStatus.INCONSISTENT)

        choice = report.first_forced()
        if choice is None:
            self._record_final(report, unknown=True)
            return self._finish(AgentStatus.AMBIGUOUS)

        try:
            result = self._engine.submit_verdict(choice.cell, choice.verdict.to_status())
        except SolverTimeout as exc:
            self._record_final(report)
            self._trace.final_stats.merge(exc.stats)
            return self._finish(AgentStatus.TIMEOUT)

        if result.outcome is not VerdictOutcome.ACCEPTED:
            raise AgentInvariantError(
                f"[LogicAgent]: Engine trả {result.outcome.value} cho verdict ép buộc "
                f"{choice.verdict.value} tại {choice.cell.label}"
            )

        revealed = result.revealed
        trace_step = TraceStep(
            step=self._trace.num_steps + 1,
            active_clue_ids=report.kb.clue_ids,
            forced_cells=tuple(r.cell.label for r in report.forced()),
            unknown_cells=_unknown_labels(report),
            cell=choice.cell,
            verdict=choice.verdict,
            sat_queries=report.sat_queries,
            skipped_queries=report.skipped_queries,
            engine_queries=result.sat_queries,
            stats=report.stats,
            revealed_clue_id=revealed.clue_id if revealed else None,
        )
        self._trace.steps.append(trace_step)

        if self.state.is_solved():
            self._finish(AgentStatus.SOLVED)
        return trace_step

    def iter_steps(self) -> Iterator[TraceStep]:
        """Sinh từng bước một tới trạng thái kết thúc"""
        while (step := self.step()) is not None:
            yield step

    def run(self) -> DeductionTrace:
        """Chạy tới trạng thái kết thúc, trả về trace"""
        for _ in self.iter_steps():
            pass
        return self._trace

    # Nội bộ

    def _new_trace(self) -> DeductionTrace:
        """Tạo trace rỗng cho state hiện tại; state đã giải xong thì đánh dấu SOLVED luôn"""
        state = self._engine.state
        trace = DeductionTrace(self._engine.puzzle_id, state.active_clue_ids())
        if state.is_solved():
            trace.status = AgentStatus.SOLVED
        return trace

    def _record_final(self, report: EntailmentReport, unknown: bool = False) -> None:
        """Ghi lần phân loại cuối (không dẫn tới verdict) vào trace"""
        self._trace.final_queries += report.sat_queries
        self._trace.final_stats.merge(report.stats)
        if unknown:
            self._trace.final_unknown = _unknown_labels(report)

    def _finish(self, status: AgentStatus) -> None:
        """Ghi trạng thái kết thúc vào trace; trả None để step() return gọn"""
        self._trace.status = status
        return None


def run_agent(engine: GameEngine, time_limit: float | None = None, reuse_models: bool = True) -> DeductionTrace:
    """Tiện ích: tạo agent trên engine và chạy tới khi kết thúc"""
    return LogicAgent(engine, time_limit, reuse_models).run()


# Hint

def find_hint(state: PublicState, time_limit: float | None = None) -> Hint | None:
    """
    Gợi ý ô suy ra được tiếp theo, chỉ dựa trên PublicState
    + None nếu KB_t UNSAT hoặc không ô nào bị ép buộc
    + SolverTimeout được để nguyên cho tầng trên xử lý
    """
    if not isinstance(state, PublicState):
        raise TypeError(f"[Hint]: Chỉ nhận PublicState, nhận được {type(state).__name__}")

    report = classify_state(state, time_limit)
    choice = report.first_forced() if report.consistent else None
    if choice is None:
        return None

    core = _minimal_support(state, choice.cell, choice.verdict, time_limit)
    return Hint(choice.cell, choice.verdict, tuple(owner.label for owner in core))


def _minimal_support(state: PublicState, cell: Cell, verdict: Verdict, time_limit: float | None) -> tuple[Cell, ...]:
    """
    Tập clue tối thiểu vẫn suy ra verdict tại cell
    Duyệt clue theo thứ tự lật nên kết quả xác định
    """
    clues = state.revealed_clues()
    keep = list(clues)
    for owner in list(keep):
        candidate = [c for c in keep if c != owner]
        if _entails(state, [clues[c] for c in candidate], cell, verdict, time_limit):
            keep = candidate
    return tuple(keep)


def _entails(state: PublicState, clues: list[Clue], cell: Cell, verdict: Verdict, time_limit: float | None) -> bool:
    """CNF(clues) ∧ verdict units |= verdict tại cell  <=>  thêm literal đối nghịch thì UNSAT"""
    vmap = VariableMap(state.board)
    cnf = CNF()
    for clue in clues:
        cnf.extend(encode_clue(clue, vmap))
    for known, status in state.verdicts().items():
        cnf.add_clause([vmap.status_literal(known, status)])
    opposite = -vmap.status_literal(cell, verdict.to_status())
    return not solve(cnf, num_vars=vmap.max_var, assumptions=(opposite,), time_limit=time_limit).sat


def _unknown_labels(report: EntailmentReport) -> tuple[str, ...]:
    """Nhãn các ô còn UNKNOWN trong report, theo row-major"""
    return tuple(r.cell.label for r in report.results.values() if r.verdict is Verdict.UNKNOWN)
