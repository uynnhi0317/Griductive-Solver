"""
Test Game Engine: phán xử verdict bằng entailment trên PublicState, không dựa vào đáp án ẩn

Kiểm tra:
+ Phân biệt ACCEPTED, NOT_PROVABLE, CONTRADICTED (và INCONSISTENT khi KB_t UNSAT)
+ Verdict bị từ chối không đổi state, không lộ clue; verdict đúng đáp án nhưng chưa chứng minh được vẫn bị từ chối
+ Đếm SAT query: truy vấn kiểm tra KB_t chỉ tính ở lần nộp đầu tiên trên mỗi state
+ restart, kiểm tra đầu vào, SolverTimeout và EngineInvariantError giữ nguyên state
+ Chơi hết mọi puzzle đi kèm chỉ bằng verdict ép buộc (không đoán)
"""

from pathlib import Path
from typing import Any, Callable

import pytest

import agent.entailment as entailment_module
from agent.entailment import EntailmentTimeout, Verdict, classify_state
from engine.game_engine import EngineInvariantError, GameEngine, VerdictOutcome
from game.cell import Cell
from game.character import Status
from game.clue import FactClue
from game.public_state import RevealedCard
from game.puzzle_loader import PuzzleFull, load_puzzle, parse_puzzle
from solver.dpll import SolverTimeout, solve
from solver.stats import SolverStats

A1, B1, A2, B2 = (Cell.parse(label) for label in ("A1", "B1", "A2", "B2"))

PUZZLE_DIR = Path(__file__).resolve().parents[1] / "puzzles"
PUZZLE_FILES = sorted(PUZZLE_DIR.rglob("*.json"))

# Puzzle 2x2 (fixture puzzle / mini_data) và rig_initial_state nằm trong conftest.py


@pytest.fixture
def engine(puzzle: PuzzleFull) -> GameEngine:
    return GameEngine(puzzle)


# Ba phản hồi chính

def test_forced_verdict_is_accepted_and_reveals_clue(engine: GameEngine, puzzle: PuzzleFull) -> None:
    before = engine.state
    result = engine.submit_verdict(B1, Status.INNOCENT)

    assert result.outcome is VerdictOutcome.ACCEPTED and result.accepted
    assert result.classification.verdict is Verdict.INNOCENT
    assert result.revealed == RevealedCard(B1, Status.INNOCENT, puzzle.clues[B1])
    assert engine.state is not before                       # state mới
    assert engine.state.status_of(B1) is Status.INNOCENT
    assert engine.state.revealed_clues()[B1] == puzzle.clues[B1]
    assert not before.is_known(B1)                          # state cũ bất biến


def test_opposite_of_forced_verdict_is_contradicted(engine: GameEngine) -> None:
    before = engine.state
    result = engine.submit_verdict(B1, Status.CRIMINAL)

    assert result.outcome is VerdictOutcome.CONTRADICTED and not result.accepted
    assert result.classification.verdict is Verdict.INNOCENT    # trạng thái đối nghịch bị ép
    assert result.revealed is None
    assert engine.state is before


@pytest.mark.parametrize("cell, status", [
    (A2, Status.INNOCENT),      # đúng đáp án nhưng chưa chứng minh được
    (A2, Status.CRIMINAL),
    (B2, Status.CRIMINAL),      # đúng đáp án nhưng chưa chứng minh được
    (B2, Status.INNOCENT),
])
def test_unforced_verdict_is_not_provable_even_if_it_matches_solution(
    engine: GameEngine, cell: Cell, status: Status
) -> None:
    before = engine.state
    result = engine.submit_verdict(cell, status)

    assert result.outcome is VerdictOutcome.NOT_PROVABLE
    assert result.classification.verdict is Verdict.UNKNOWN
    assert result.revealed is None
    assert engine.state is before
    assert cell not in engine.state.revealed_clues()        # clue ẩn không bị lộ


def test_not_provable_cell_becomes_accepted_after_new_clue(engine: GameEngine) -> None:
    assert engine.submit_verdict(A2, Status.INNOCENT).outcome is VerdictOutcome.NOT_PROVABLE
    engine.submit_verdict(B1, Status.INNOCENT)               # lộ SAME(B1, A2)
    assert engine.submit_verdict(A2, Status.INNOCENT).outcome is VerdictOutcome.ACCEPTED


def test_rejected_verdicts_never_change_state(engine: GameEngine) -> None:
    before = engine.state
    engine.submit_verdict(B1, Status.CRIMINAL)
    engine.submit_verdict(A2, Status.INNOCENT)
    engine.submit_verdict(B2, Status.CRIMINAL)

    assert engine.state is before
    assert engine.state.active_clue_ids() == ("A1",)
    assert len(engine.history) == 3 and not any(r.accepted for r in engine.history)


def test_full_game_solves_with_forced_verdicts(engine: GameEngine, puzzle: PuzzleFull) -> None:
    for cell, status in ((B1, Status.INNOCENT), (A2, Status.INNOCENT), (B2, Status.CRIMINAL)):
        assert engine.submit_verdict(cell, status).accepted

    assert engine.is_solved()
    assert dict(engine.state.verdicts()) == dict(puzzle.solution)
    assert engine.state.active_clue_ids() == ("A1", "B1", "A2", "B2")


# INCONSISTENT và lỗi bất biến

def test_inconsistent_state_is_reported_without_changing_state(
    rig_initial_state: Callable[[list[RevealedCard]], None], mini_data: dict[str, Any]
) -> None:
    # Thẻ A1 ghi CRIMINAL nhưng clue nói A1 INNOCENT -> KB_t UNSAT
    rig_initial_state([RevealedCard(A1, Status.CRIMINAL, FactClue(A1, Status.INNOCENT))])
    engine = GameEngine(parse_puzzle(mini_data))
    before = engine.state

    result = engine.submit_verdict(B1, Status.INNOCENT)

    assert result.outcome is VerdictOutcome.INCONSISTENT
    assert result.consistency is not None and not result.consistency.sat
    assert result.classification.queries == ()               # KB_t UNSAT thì không phân loại tiếp
    assert engine.state is before


def test_proved_verdict_differing_from_solution_raises_invariant_error(
    rig_initial_state: Callable[[list[RevealedCard]], None], mini_data: dict[str, Any]
) -> None:
    # Clue công khai ép B2 INNOCENT, nhưng đáp án B2 là CRIMINAL
    rig_initial_state([RevealedCard(A1, Status.CRIMINAL, FactClue(B2, Status.INNOCENT))])
    engine = GameEngine(parse_puzzle(mini_data))
    before = engine.state

    with pytest.raises(EngineInvariantError):
        engine.submit_verdict(B2, Status.INNOCENT)

    assert engine.state is before
    assert engine.history == ()


def test_invariant_error_is_not_value_error() -> None:
    # GUI bắt ValueError cho lỗi đầu vào, không được nuốt nhầm lỗi nội bộ
    assert not issubclass(EngineInvariantError, ValueError)
    assert issubclass(EngineInvariantError, RuntimeError)


# Đếm SAT query

def test_consistency_query_counted_once_per_state(engine: GameEngine) -> None:
    first = engine.submit_verdict(A2, Status.CRIMINAL)
    second = engine.submit_verdict(B2, Status.CRIMINAL)     # cùng state, dùng lại KB_t
    accepted = engine.submit_verdict(B1, Status.INNOCENT)   # vẫn cùng state
    after = engine.submit_verdict(B2, Status.CRIMINAL)      # state mới sau khi lật B1

    assert first.consistency is not None and first.consistency.sat
    assert second.consistency is None
    assert accepted.consistency is None
    assert after.consistency is not None


def test_sat_queries_include_consistency_and_classification(engine: GameEngine) -> None:
    result = engine.submit_verdict(A2, Status.CRIMINAL)

    assert result.queries[0] is result.consistency
    assert result.queries[1:] == result.classification.queries
    assert result.sat_queries == len(result.queries) == 1 + result.classification.sat_queries


# restart

def test_restart_returns_to_initial_state(engine: GameEngine, puzzle: PuzzleFull) -> None:
    engine.submit_verdict(B1, Status.INNOCENT)
    engine.submit_verdict(B2, Status.INNOCENT)
    engine.restart()

    assert engine.history == ()
    assert engine.state.active_clue_ids() == tuple(c.label for c in puzzle.initially_revealed)
    assert engine.state.unsolved_cells() == (B1, A2, B2)
    # KB_t được dựng lại: lần nộp đầu sau restart lại tính truy vấn kiểm tra KB_t
    assert engine.submit_verdict(B1, Status.INNOCENT).consistency is not None


# Kiểm tra đầu vào

@pytest.mark.parametrize("cell, status, error", [
    ("B1", Status.INNOCENT, TypeError),            # cell không phải Cell
    (B1, "INNOCENT", TypeError),                   # status không phải Status
    (Cell(3, 1), Status.INNOCENT, ValueError),     # ngoài board 2x2
    (A1, Status.CRIMINAL, ValueError),             # thẻ đã lật
])
def test_invalid_submission_raises_without_recording(
    engine: GameEngine, cell: Any, status: Any, error: type[Exception]
) -> None:
    with pytest.raises(error):
        engine.submit_verdict(cell, status)
    assert engine.history == ()


def test_valid_time_limit_and_public_info(puzzle: PuzzleFull) -> None:
    engine = GameEngine(puzzle, time_limit=5)

    assert (engine.puzzle_id, engine.title, engine.board.size) == ("test_2x2", "", 2)
    assert engine.submit_verdict(B1, Status.INNOCENT).accepted


def test_constructor_requires_puzzle_full(mini_data: dict[str, Any]) -> None:
    with pytest.raises(TypeError):
        GameEngine(mini_data)  # type: ignore[arg-type]


@pytest.mark.parametrize("time_limit, error", [
    (True, TypeError),
    ("1", TypeError),
    (0, ValueError),
    (-0.5, ValueError),
])
def test_invalid_time_limit_rejected(puzzle: PuzzleFull, time_limit: Any, error: type[Exception]) -> None:
    with pytest.raises(error):
        GameEngine(puzzle, time_limit)


# Timeout

def test_solver_timeout_keeps_state_and_rebuilds_checker(
    engine: GameEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    def always_timeout(*args: Any, **kwargs: Any) -> None:
        raise SolverTimeout(SolverStats())

    before = engine.state
    with monkeypatch.context() as patch:
        patch.setattr(entailment_module, "solve", always_timeout)
        with pytest.raises(SolverTimeout):
            engine.submit_verdict(B1, Status.INNOCENT)

    assert engine.state is before and engine.history == ()
    # Checker không được lưu khi timeout nên lần sau chạy lại truy vấn kiểm tra KB_t
    result = engine.submit_verdict(B1, Status.INNOCENT)
    assert result.accepted and result.consistency is not None


def test_timeout_after_consistency_query_is_counted_once(
    engine: GameEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Truy vấn KB_t chạy xong, truy vấn phân loại kế tiếp timeout
    calls = [0]

    def timeout_on_second(*args: Any, **kwargs: Any) -> Any:
        calls[0] += 1
        if calls[0] == 2:
            raise SolverTimeout(SolverStats())
        return solve(*args, **kwargs)

    before = engine.state
    with monkeypatch.context() as patch:
        patch.setattr(entailment_module, "solve", timeout_on_second)
        with pytest.raises(EntailmentTimeout) as info:
            engine.submit_verdict(B1, Status.INNOCENT)

    assert [q.label for q in info.value.completed] == ["KB"]   # truy vấn KB_t được gắn vào lỗi
    assert info.value.num_queries == 2
    assert engine.state is before and engine.history == ()
    # KB_t đã kiểm tra xong và được tính trong lỗi ở trên, lần nộp sau không tính lại
    assert engine.submit_verdict(B1, Status.INNOCENT).consistency is None


# Puzzle đi kèm

@pytest.mark.skipif(not PUZZLE_FILES, reason="không tìm thấy puzzle nào")
@pytest.mark.parametrize("path", PUZZLE_FILES, ids=lambda p: p.name)
def test_bundled_puzzle_playthrough_without_guessing(path: Path) -> None:
    """
    Người chơi chỉ nhìn engine.state (không đọc đáp án):
    mỗi bước ô UNKNOWN phải NOT_PROVABLE, verdict ngược với ô ép buộc phải CONTRADICTED,
    và nộp ô ép buộc đầu tiên (row-major) phải ACCEPTED cho tới khi giải xong
    """
    engine = GameEngine.from_file(path)
    solution = load_puzzle(path).solution       # chỉ dùng để đối chiếu kết quả cuối
    max_steps = len(engine.board.cells())

    for _ in range(max_steps):
        if engine.is_solved():
            break
        report = classify_state(engine.state)
        forced = report.first_forced()
        assert report.consistent, f"{path.name}: KB_t UNSAT"
        assert forced is not None, f"{path.name}: kẹt, không còn ô nào bị ép (cần đoán)"

        for unknown in (r.cell for r in report.results.values() if r.verdict is Verdict.UNKNOWN):
            assert engine.submit_verdict(unknown, Status.CRIMINAL).outcome is VerdictOutcome.NOT_PROVABLE

        status = forced.verdict.to_status()
        assert engine.submit_verdict(forced.cell, status.opposite).outcome is VerdictOutcome.CONTRADICTED
        assert engine.submit_verdict(forced.cell, status).accepted

    assert engine.is_solved(), f"{path.name}: chưa giải xong sau {max_steps} bước"
    assert dict(engine.state.verdicts()) == dict(solution)