"""
Nhật ký hành động của phiên chơi: ai đã nộp verdict nào (người chơi hay Agent)

+ engine.history chỉ biết VerdictResult, không biết verdict do ai nộp
+ ActionLog ghi thêm: bước nào của agent (TraceStep) ứng với mục nào của history,
  và trạng thái kết thúc của agent (SOLVED / AMBIGUOUS / INCONSISTENT / TIMEOUT)
+ snapshot(history) ghép hai nguồn thành LogSnapshot bất biến cho History tab và Stats tab
+ SAT của một mục = truy vấn engine dùng để phán xử + truy vấn agent dùng để phân loại (nếu do agent nộp)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from agent.trace import AgentStatus, DeductionTrace, TraceStep
from engine.game_engine import VerdictResult
from solver.stats import SolverStats


class Actor(Enum):
    PLAYER = "You"
    AGENT = "Agent"


@dataclass(frozen=True)
class HistoryEntry:
    """Một verdict đã nộp cho engine, kể cả verdict bị từ chối"""
    index: int                      # vị trí trong engine.history
    result: VerdictResult
    actor: Actor
    step: TraceStep | None = None   # chỉ có khi actor là AGENT

    @property
    def accepted(self) -> bool:
        return self.result.accepted

    @property
    def engine_queries(self) -> int:
        return self.result.sat_queries

    @property
    def agent_queries(self) -> int:
        return 0 if self.step is None else self.step.sat_queries

    @property
    def sat_queries(self) -> int:
        return self.engine_queries + self.agent_queries

    def stats(self) -> SolverStats:
        """Cộng dồn số liệu solver của engine và (nếu có) của agent"""
        total = SolverStats()
        for q in self.result.queries:
            total.merge(q.stats)
        if self.step is not None:
            total.merge(self.step.stats)
        return total


@dataclass(frozen=True)
class AgentEnd:
    """Trạng thái kết thúc của agent và lần phân loại cuối (không dẫn tới verdict)"""
    status: AgentStatus
    unknown: tuple[str, ...]
    queries: int
    stats: SolverStats


@dataclass(frozen=True)
class LogSnapshot:
    entries: tuple[HistoryEntry, ...]
    end: AgentEnd | None = None

    @property
    def engine_sat(self) -> int:
        return sum(e.engine_queries for e in self.entries)

    @property
    def agent_sat(self) -> int:
        return sum(e.agent_queries for e in self.entries) + (self.end.queries if self.end else 0)

    @property
    def total_sat(self) -> int:
        return self.engine_sat + self.agent_sat

    def stats(self) -> SolverStats:
        total = SolverStats()
        for e in self.entries:
            total.merge(e.stats())
        if self.end is not None:
            total.merge(self.end.stats)
        return total


class ActionLog:
    """App ghi vào đây mỗi khi agent đi một bước hoặc dừng; người chơi không cần ghi gì thêm"""

    def __init__(self) -> None:
        self._agent_steps: dict[int, TraceStep] = {}
        self._end: AgentEnd | None = None

    def clear(self) -> None:
        self._agent_steps.clear()
        self._end = None

    def clear_end(self) -> None:
        self._end = None

    def record_agent_step(self, history_index: int, step: TraceStep) -> None:
        self._agent_steps[history_index] = step

    def record_end(self, trace: DeductionTrace) -> None:
        stats = SolverStats()
        stats.merge(trace.final_stats)
        self._end = AgentEnd(trace.status, trace.final_unknown, trace.final_queries, stats)

    def snapshot(self, history: tuple[VerdictResult, ...]) -> LogSnapshot:
        entries = []
        for i, result in enumerate(history):
            step = self._agent_steps.get(i)
            entries.append(HistoryEntry(i, result, Actor.AGENT if step else Actor.PLAYER, step))
        return LogSnapshot(tuple(entries), self._end)