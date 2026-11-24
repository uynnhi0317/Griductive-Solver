"""
Test Logic Agent, entailment classifier, deduction trace và Hint

Kiểm tra:
+ Entailment: CRIMINAL / INNOCENT / UNKNOWN / INCONSISTENT đúng định nghĩa KB ∧ ¬C_i, KB ∧ C_i
  (ví dụ trong đề, đối chiếu vét cạn trên CNF ngẫu nhiên, ModelPool không làm đổi kết quả)
+ Không đoán: mọi verdict agent nộp đều là ô ép buộc đầu tiên theo row-major, engine luôn ACCEPTED
+ Kết thúc đúng trạng thái: SOLVED, AMBIGUOUS (không nộp gì thêm), INCONSISTENT, TIMEOUT
+ Trace: số bước, clue đang dùng, clue mới lộ, số SAT query khớp với những gì đã xảy ra
+ Hint không đọc đáp án ẩn: chỉ nhận PublicState, hai puzzle chung public state thì cho cùng hint
+ Ranh giới kiến trúc: code agent không import PuzzleFull, không truy cập đáp án / clue ẩn
+ Chạy hết mọi puzzle đi kèm tới SOLVED và khớp đáp án
"""

import ast
import dataclasses
import itertools
import random
from pathlib import Path
from typing import Any, Callable

import pytest

import agent.entailment as entailment_module
from agent.entailment import (
    EntailmentChecker, EntailmentTimeout, ModelPool, Verdict, classify_state, classify_var,
)
from agent.logic_agent import AgentInvariantError, Hint, LogicAgent, find_hint, run_agent
from agent.trace import AgentStatus, DeductionTrace
from engine.game_engine import GameEngine, VerdictOutcome, VerdictResult
from game.cell import Cell
from game.character import Status
from game.clue import FactClue
from game.public_state import RevealedCard
from game.puzzle_loader import PuzzleFull, load_puzzle, parse_puzzle
from logic.cnf import CNF
from solver.dpll import SolverTimeout, solve
from solver.stats import SolverStats

A1, B1, A2, B2 = (Cell.parse(label) for label in ("A1", "B1", "A2", "B2"))

SOURCE_DIR = Path(__file__).resolve().parents[1]
PUZZLE_DIR = SOURCE_DIR / "puzzles"
PUZZLE_FILES = sorted(PUZZLE_DIR.rglob("*.json"))

# Puzzle 2x2 (fixture puzzle / mini_data) và rig_initial_state nằm trong conftest.py
# Lời giải mong đợi: B1 INNOCENT -> A2 INNOCENT -> B2 CRIMINAL
_MINI_STEPS = ((B1, Verdict.INNOCENT), (A2, Verdict.INNOCENT), (B2, Verdict.CRIMINAL))


@pytest.fixture
def engine(puzzle: PuzzleFull) -> GameEngine:
    return GameEngine(puzzle)


@pytest.fixture
def ambiguous_puzzle(mini_data: dict[str, Any]) -> PuzzleFull:
    """
    Biến thể: thẻ B1 chỉ lặp lại điều đã biết (A1 CRIMINAL)
    -> sau khi lật B1 thì A2, B2 không bao giờ bị ép
    """
    mini_data["clues"]["B1"] = {"type": "FACT", "cell": "A1", "status": "CRIMINAL"}
    return parse_puzzle(mini_data)


@pytest.fixture
def twin_puzzle(mini_data: dict[str, Any]) -> PuzzleFull:
    """
    Cùng board và cùng thẻ mở sẵn A1 với puzzle gốc, nhưng phần ẩn khác hẳn:
    đáp án A2 CRIMINAL, B2 INNOCENT và clue của B1 là SAME(B1, B2)
    -> agent / hint chỉ nhìn public state thì không phân biệt được hai puzzle ở bước đầu
    """
    mini_data["solution"].update({"A2": "CRIMINAL", "B2": "INNOCENT"})
    mini_data["clues"]["B1"] = {"type": "SAME", "cells": ["B1", "B2"]}
    return parse_puzzle(mini_data)


def _spy_submissions(engine: GameEngine, monkeypatch: pytest.MonkeyPatch) -> list[VerdictResult]:
    """
    Bọc engine.submit_verdict: trước mỗi lần nộp, tự phân loại lại state công khai
    và kiểm tra verdict nộp lên đúng là ô ép buộc đầu tiên theo row-major
    """
    real_submit = engine.submit_verdict
    results: list[VerdictResult] = []

    def spy(cell: Cell, status: Status) -> VerdictResult:
        expected = classify_state(engine.state).first_forced()
        assert expected is not None, "agent nộp verdict khi không còn ô nào bị ép (đoán mò)"
        assert (cell, status) == (expected.cell, expected.verdict.to_status())
        result = real_submit(cell, status)
        results.append(result)
        return result

    monkeypatch.setattr(engine, "submit_verdict", spy)
    return results


def _moves(trace: DeductionTrace) -> list[tuple[Cell, Verdict]]:
    return [(s.cell, s.verdict) for s in trace.steps]


def _brute_force_verdict(cnf: CNF, var: int, n: int) -> Verdict:
    """Duyệt mọi phép gán để biết var bị ép thế nào, không dùng solver"""
    values = {
        bits[var - 1]
        for bits in itertools.product((False, True), repeat=n)
        if all(any(bits[abs(lit) - 1] == (lit > 0) for lit in clause) for clause in cnf)
    }
    if not values:
        return Verdict.INCONSISTENT
    if values == {True}:
        return Verdict.CRIMINAL
    if values == {False}:
        return Verdict.INNOCENT
    return Verdict.UNKNOWN


# Entailment classifier

def test_entailment_example_from_spec() -> None:
    # KB = (C_A ∨ C_B) ∧ (¬C_A ∨ C_B): KB ∧ ¬C_B UNSAT nên B CRIMINAL, A còn UNKNOWN
    a, b = 1, 2
    kb = CNF([[a, b], [-a, b]])

    criminal = classify_var(kb, b)
    assert criminal.verdict is Verdict.CRIMINAL
    assert [q.label for q in criminal.queries] == ["KB", "KB ∧ ¬x2"]
    assert [q.sat for q in criminal.queries] == [True, False]

    unknown = classify_var(kb, a)
    assert unknown.verdict is Verdict.UNKNOWN
    assert [q.sat for q in unknown.queries] == [True, True, True]


@pytest.mark.parametrize("clauses, verdict, queries", [
    ([[-1]], Verdict.INNOCENT, 3),               # KB SAT, KB ∧ ¬x1 SAT, KB ∧ x1 UNSAT
    ([[1], [-1]], Verdict.INCONSISTENT, 1),      # dừng ngay sau truy vấn KB
])
def test_entailment_innocent_and_inconsistent(clauses: list[list[int]], verdict: Verdict, queries: int) -> None:
    result = classify_var(CNF(clauses), 1)
    assert result.verdict is verdict
    assert len(result.queries) == queries


@pytest.mark.parametrize("use_pool", [False, True])
def test_entailment_matches_brute_force_on_random_cnfs(use_pool: bool) -> None:
    rng = random.Random(2026)
    for _ in range(150):
        n = rng.randint(1, 5)
        cnf = CNF([[rng.choice((-1, 1)) * rng.randint(1, n) for _ in range(rng.randint(1, 3))]
                   for _ in range(rng.randint(1, 3 * n))])
        pool = ModelPool() if use_pool else None
        for var in range(1, n + 1):
            got = classify_var(cnf, var, num_vars=n, pool=pool).verdict
            assert got is _brute_force_verdict(cnf, var, n), f"{cnf!r}, x{var}"


@pytest.mark.parametrize("bad", [0, -1, True, 1.5])
def test_classify_var_rejects_invalid_variable(bad: Any) -> None:
    with pytest.raises(ValueError):
        classify_var(CNF([[1]]), bad)


@pytest.mark.parametrize("verdict", [Verdict.UNKNOWN, Verdict.INCONSISTENT])
def test_unforced_verdict_has_no_status(verdict: Verdict) -> None:
    assert not verdict.is_forced
    with pytest.raises(ValueError):
        verdict.to_status()


def test_checker_only_accepts_public_state(puzzle: PuzzleFull) -> None:
    with pytest.raises(TypeError):
        EntailmentChecker(puzzle)  # type: ignore[arg-type]


def test_checker_rejects_non_bool_reuse_models(engine: GameEngine) -> None:
    with pytest.raises(ValueError):
        EntailmentChecker(engine.state, reuse_models=1)  # type: ignore[arg-type]


@pytest.mark.parametrize("cell", [A1, Cell(3, 3)])      # thẻ đã lật, ô ngoài board 2x2
def test_checker_rejects_known_or_outside_cell(engine: GameEngine, cell: Cell) -> None:
    with pytest.raises(ValueError):
        EntailmentChecker(engine.state).classify(cell)


def test_analyze_classifies_every_unsolved_cell(engine: GameEngine) -> None:
    report = LogicAgent(engine).analyze()

    assert report.consistent
    assert {c.label: r.verdict for c, r in report.results.items()} == {
        "B1": Verdict.INNOCENT, "A2": Verdict.UNKNOWN, "B2": Verdict.UNKNOWN,
    }
    assert list(report.results) == list(engine.state.unsolved_cells())    # row-major
    assert report.kb.clue_ids == ("A1",)                                   # KB_t chỉ có clue đã lộ
    assert EntailmentChecker(engine.state).kb.clue_ids == ("A1",)
    assert report.sat_queries == 1 + sum(r.sat_queries for r in report.results.values())


@pytest.mark.skipif(not PUZZLE_FILES, reason="không tìm thấy puzzle nào")
@pytest.mark.parametrize("path", PUZZLE_FILES, ids=lambda p: p.name)
def test_model_reuse_never_changes_verdicts(path: Path) -> None:
    state = load_puzzle(path).initial_state()
    reused = classify_state(state)
    plain = classify_state(state, reuse_models=False)

    assert [r.verdict for r in reused.results.values()] == [r.verdict for r in plain.results.values()]
    assert plain.skipped_queries == 0
    assert reused.sat_queries + reused.skipped_queries <= plain.sat_queries + plain.skipped_queries


def test_entailment_timeout_counts_completed_queries(engine: GameEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = [0]

    def timeout_on_second(*args: Any, **kwargs: Any) -> Any:
        calls[0] += 1
        if calls[0] == 2:
            raise SolverTimeout(SolverStats())
        return solve(*args, **kwargs)

    monkeypatch.setattr(entailment_module, "solve", timeout_on_second)
    with pytest.raises(EntailmentTimeout) as info:
        classify_state(engine.state)

    assert len(info.value.completed) == 1               # truy vấn KB_t đã chạy xong
    assert info.value.num_queries == 2                  # cộng thêm truy vấn bị timeout
    expected = SolverStats()
    expected.merge(info.value.completed[0].stats)
    expected.merge(info.value.stats)
    assert info.value.total_stats().as_dict() == expected.as_dict()


# Không đoán và trạng thái SOLVED

def test_agent_solves_mini_puzzle_with_forced_moves_only(
    engine: GameEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    submissions = _spy_submissions(engine, monkeypatch)
    trace = LogicAgent(engine).run()

    assert trace.status is AgentStatus.SOLVED
    assert _moves(trace) == list(_MINI_STEPS)
    assert all(r.outcome is VerdictOutcome.ACCEPTED for r in submissions)
    assert len(submissions) == trace.num_steps
    assert engine.is_solved()


def test_trace_records_clues_and_reveals_per_step(engine: GameEngine) -> None:
    trace = LogicAgent(engine).run()

    assert trace.puzzle_id == "test_2x2"
    assert trace.initial_clue_ids == ("A1",)
    assert [s.step for s in trace.steps] == [1, 2, 3]
    assert [s.active_clue_ids for s in trace.steps] == [("A1",), ("A1", "B1"), ("A1", "B1", "A2")]
    assert [s.revealed_clue_id for s in trace.steps] == ["B1", "A2", "B2"]
    assert [s.forced_cells for s in trace.steps] == [("B1",), ("A2",), ("B2",)]
    assert [s.unknown_cells for s in trace.steps] == [("A2", "B2"), ("B2",), ()]


def test_trace_query_counts_match_steps(engine: GameEngine) -> None:
    trace = LogicAgent(engine).run()

    assert all(s.sat_queries >= 1 and s.engine_queries >= 1 for s in trace.steps)  # có ít nhất truy vấn KB_t
    assert trace.agent_queries == sum(s.sat_queries for s in trace.steps) + trace.final_queries
    assert trace.engine_queries == sum(s.engine_queries for s in trace.steps)
    assert trace.total_queries == trace.agent_queries + trace.engine_queries
    assert trace.final_queries == 0      # SOLVED ngay sau verdict cuối, không cần phân loại thêm


def test_trace_text_and_summary(engine: GameEngine) -> None:
    trace = LogicAgent(engine).run()
    text = trace.to_text(engine.board)
    summary = trace.summary()

    assert text.splitlines()[0] == "Puzzle test_2x2: initial clues [Ann]"
    assert "Finished: SOLVED" in text
    assert len(text.splitlines()) == 1 + trace.num_steps + 2     # tiêu đề + mỗi bước + kết thúc + tổng
    assert (summary["status"], summary["steps"]) == ("SOLVED", 3)
    assert trace.steps[0].as_dict()["revealed_clue"] == "B1"


def test_step_by_step_then_stops(engine: GameEngine) -> None:
    agent = LogicAgent(engine)
    first = agent.step()

    assert first is not None and (first.cell, first.verdict) == _MINI_STEPS[0]
    assert agent.status is AgentStatus.RUNNING
    assert len(list(agent.iter_steps())) == 2
    assert agent.status is AgentStatus.SOLVED
    assert agent.step() is None                         # đã kết thúc thì không nộp thêm
    assert len(engine.history) == 3


def test_agent_on_solved_engine_does_nothing(engine: GameEngine) -> None:
    run_agent(engine)
    agent = LogicAgent(engine)

    assert agent.status is AgentStatus.SOLVED
    assert agent.run().num_steps == 0
    assert len(engine.history) == 3


def test_reuse_models_only_changes_query_counts(puzzle: PuzzleFull) -> None:
    reused = run_agent(GameEngine(puzzle))
    plain = run_agent(GameEngine(puzzle), reuse_models=False)

    assert _moves(plain) == _moves(reused)
    assert plain.skipped_queries == 0
    assert plain.agent_queries >= reused.agent_queries


# Các trạng thái kết thúc khác

def test_ambiguous_stops_without_guessing(ambiguous_puzzle: PuzzleFull) -> None:
    engine = GameEngine(ambiguous_puzzle)
    trace = LogicAgent(engine).run()

    assert trace.status is AgentStatus.AMBIGUOUS
    assert _moves(trace) == [_MINI_STEPS[0]]
    assert trace.final_unknown == ("A2", "B2")
    assert trace.final_queries >= 1
    assert len(engine.history) == 1                     # chỉ verdict B1, không đoán A2 / B2
    assert not engine.is_solved()
    assert "Finished: AMBIGUOUS, still UNKNOWN: Cal, Dee" in trace.to_text(engine.board)
    assert trace.summary()["unknown_left"] == "A2 B2"


def test_inconsistent_state_stops_before_submitting(
    rig_initial_state: Callable[[list[RevealedCard]], None], mini_data: dict[str, Any]
) -> None:
    # Thẻ A1 ghi CRIMINAL nhưng clue nói A1 INNOCENT -> KB_t UNSAT
    rig_initial_state([RevealedCard(A1, Status.CRIMINAL, FactClue(A1, Status.INNOCENT))])
    engine = GameEngine(parse_puzzle(mini_data))
    trace = LogicAgent(engine).run()

    assert trace.status is AgentStatus.INCONSISTENT
    assert trace.num_steps == 0
    assert trace.final_queries == 1                     # chỉ truy vấn kiểm tra KB_t
    assert engine.history == ()


def test_timeout_while_analyzing(engine: GameEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    def always_timeout(*args: Any, **kwargs: Any) -> None:
        raise SolverTimeout(SolverStats())

    monkeypatch.setattr(entailment_module, "solve", always_timeout)
    before = engine.state
    trace = LogicAgent(engine, time_limit=1.0).run()

    assert trace.status is AgentStatus.TIMEOUT
    assert trace.num_steps == 0
    assert trace.final_queries == 1                     # truy vấn KB_t bị timeout vẫn được đếm
    assert engine.state is before and engine.history == ()


def test_timeout_while_engine_judges(engine: GameEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    def engine_timeout(cell: Cell, status: Status) -> None:
        raise SolverTimeout(SolverStats())

    monkeypatch.setattr(engine, "submit_verdict", engine_timeout)
    trace = LogicAgent(engine).run()

    assert trace.status is AgentStatus.TIMEOUT
    assert trace.num_steps == 0
    assert trace.final_queries >= 2                     # truy vấn phân loại của agent + truy vấn bị timeout


def test_engine_rejecting_forced_verdict_raises(engine: GameEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    real_submit = engine.submit_verdict

    def disagreeing(cell: Cell, status: Status) -> VerdictResult:
        return dataclasses.replace(real_submit(cell, status), outcome=VerdictOutcome.CONTRADICTED)

    monkeypatch.setattr(engine, "submit_verdict", disagreeing)
    with pytest.raises(AgentInvariantError):
        LogicAgent(engine).step()


def test_external_restart_resets_trace(engine: GameEngine) -> None:
    agent = LogicAgent(engine)
    agent.run()
    old_trace = agent.trace
    engine.restart()                                    # state đổi từ bên ngoài (vd. nút Restart trên GUI)

    step = agent.step()

    assert agent.trace is not old_trace
    assert step is not None and step.step == 1
    assert agent.trace.num_steps == 1


def test_agent_continues_after_manual_moves(engine: GameEngine) -> None:
    # Người chơi tự lật B1 trên GUI rồi mới bấm Auto Solve: agent đi tiếp từ state hiện tại
    agent = LogicAgent(engine)
    engine.submit_verdict(B1, Status.INNOCENT)

    trace = agent.run()

    assert trace.status is AgentStatus.SOLVED
    assert trace.initial_clue_ids == ("A1", "B1")
    assert _moves(trace) == list(_MINI_STEPS[1:])


def test_agent_stops_when_player_finishes_manually(engine: GameEngine) -> None:
    agent = LogicAgent(engine)
    for cell, verdict in _MINI_STEPS:
        engine.submit_verdict(cell, verdict.to_status())

    assert agent.step() is None
    assert agent.status is AgentStatus.SOLVED and agent.trace.num_steps == 0


def test_agent_requires_game_engine(puzzle: PuzzleFull) -> None:
    with pytest.raises(TypeError):
        LogicAgent(puzzle)  # type: ignore[arg-type]


# Hint

def test_hint_on_initial_state(engine: GameEngine) -> None:
    assert find_hint(engine.state) == Hint(B1, Verdict.INNOCENT, ("A1",))


def test_hint_keeps_only_needed_clues(engine: GameEngine) -> None:
    # Sau khi lật B1: A2 bị ép nhờ SAME(B1, A2) và unit clause B1 INNOCENT,
    # clue DIFFERENT(A1, B1) của A1 không còn cần nên bị bỏ khỏi tập clue gợi ý
    engine.submit_verdict(B1, Status.INNOCENT)
    assert find_hint(engine.state) == Hint(A2, Verdict.INNOCENT, ("B1",))


def test_hint_does_not_change_game(engine: GameEngine) -> None:
    before = engine.state
    agent = LogicAgent(engine)

    assert agent.hint() == find_hint(before)
    assert engine.state is before and engine.history == ()


def test_hint_none_when_nothing_forced(ambiguous_puzzle: PuzzleFull) -> None:
    engine = GameEngine(ambiguous_puzzle)
    engine.submit_verdict(B1, Status.INNOCENT)
    assert find_hint(engine.state) is None


def test_hint_none_when_inconsistent(
    rig_initial_state: Callable[[list[RevealedCard]], None], mini_data: dict[str, Any]
) -> None:
    rig_initial_state([RevealedCard(A1, Status.CRIMINAL, FactClue(A1, Status.INNOCENT))])
    assert find_hint(GameEngine(parse_puzzle(mini_data)).state) is None


@pytest.mark.parametrize("source", ["engine", "puzzle"])
def test_hint_only_accepts_public_state(engine: GameEngine, puzzle: PuzzleFull, source: str) -> None:
    with pytest.raises(TypeError):
        find_hint({"engine": engine, "puzzle": puzzle}[source])  # type: ignore[arg-type]


# Không đọc đáp án ẩn: hai puzzle chung public state nhưng khác phần ẩn

def test_hint_independent_of_hidden_data(puzzle: PuzzleFull, twin_puzzle: PuzzleFull) -> None:
    assert puzzle.solution != twin_puzzle.solution
    assert find_hint(GameEngine(puzzle).state) == find_hint(GameEngine(twin_puzzle).state)


def test_first_agent_step_independent_of_hidden_data(puzzle: PuzzleFull, twin_puzzle: PuzzleFull) -> None:
    def first_step(p: PuzzleFull) -> tuple[Any, ...]:
        step = LogicAgent(GameEngine(p)).step()
        assert step is not None
        return (step.cell, step.verdict, step.active_clue_ids, step.forced_cells, step.unknown_cells)

    assert first_step(puzzle) == first_step(twin_puzzle)


# Ranh giới kiến trúc: agent chỉ thấy public state

# uniqueness.py không nằm trong danh sách: đề yêu cầu nó kiểm tra bộ clue đầy đủ nên được phép nhận PuzzleFull
_PUBLIC_ONLY_MODULES = ("entailment.py", "logic_agent.py", "trace.py")
_HIDDEN_ATTRIBUTES = {"_puzzle", "solution", "clues", "initially_revealed"}


@pytest.mark.parametrize("name", _PUBLIC_ONLY_MODULES)
def test_agent_modules_never_touch_hidden_data(name: str) -> None:
    tree = ast.parse((SOURCE_DIR / "agent" / name).read_text(encoding="utf-8"))
    imported: list[str] = []
    attributes: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
            imported += [alias.name for alias in node.names]
        elif isinstance(node, ast.Import):
            imported += [alias.name for alias in node.names]
        elif isinstance(node, ast.Attribute):
            attributes.add(node.attr)

    assert not any("puzzle_loader" in m or m == "PuzzleFull" for m in imported), name
    assert not attributes & _HIDDEN_ATTRIBUTES, f"{name} truy cập {attributes & _HIDDEN_ATTRIBUTES}"


# Puzzle đi kèm

@pytest.mark.skipif(not PUZZLE_FILES, reason="không tìm thấy puzzle nào")
@pytest.mark.parametrize("path", PUZZLE_FILES, ids=lambda p: p.name)
def test_bundled_puzzle_solved_without_guessing(path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = GameEngine.from_file(path)
    unsolved = len(engine.state.unsolved_cells())
    submissions = _spy_submissions(engine, monkeypatch)

    trace = LogicAgent(engine).run()

    assert trace.status is AgentStatus.SOLVED, f"{path.name}: {trace.status.value}"
    assert trace.num_steps == len(submissions) == unsolved   # mỗi ô chưa giải đúng một verdict
    solution = load_puzzle(path).solution                    # chỉ dùng để đối chiếu kết quả cuối
    assert all(solution[s.cell] is s.verdict.to_status() for s in trace.steps)