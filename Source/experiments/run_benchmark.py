"""
Benchmark runner: chạy toàn bộ hệ thống trên mọi puzzle và xuất CSV

Mỗi lần chạy trên một puzzle gồm hai phần độc lập:
1. Uniqueness check trên bộ clue đầy đủ (check_puzzle_uniqueness)
2. Vòng suy diễn: GameEngine + LogicAgent chạy tới trạng thái kết thúc
   (SOLVED / AMBIGUOUS / INCONSISTENT / TIMEOUT)

Nguyên tắc ghi nhận:
+ Mọi puzzle đều có đúng một dòng cho mỗi (chế độ, lần chạy), KHÔNG loại bỏ dòng nào
+ Lỗi đọc file -> status LOAD_ERROR; lỗi khi chạy (vd. EngineInvariantError) -> status ERROR,
  kèm thông báo lỗi và số liệu tính tới lúc dừng
+ Timeout được xử lý bởi chính agent / uniqueness check (time_limit cho mỗi SAT query)
  và xuất hiện trong cột status / uniqueness là TIMEOUT
+ Cùng một tập puzzle cho mọi chế độ, duyệt theo thứ tự đường dẫn nên kết quả xác định

Đầu ra:
+ benchmark_summary.csv: một dòng cho mỗi lần chạy, cột theo metrics.SUMMARY_FIELDS
+ benchmark_steps.csv: một dòng cho mỗi bước suy diễn
+ traces/<puzzle>_<chế độ>_run<k>.txt: deduction trace dạng văn bản (khi có --save-traces)

Chạy từ thư mục Source:
    python -m experiments.run_benchmark
    python -m experiments.run_benchmark --sizes 3 4 --model-reuse both --repeat 3 --save-traces
"""

import argparse
import csv
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

SOURCE_ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    # Cho phép chạy trực tiếp file này: thêm Source vào sys.path
    sys.path.insert(0, str(SOURCE_ROOT))

from agent.logic_agent import LogicAgent
from agent.uniqueness import check_puzzle_uniqueness
from engine.game_engine import GameEngine
from game.puzzle_loader import PuzzleFull, discover_puzzles, load_puzzle

from experiments.metrics import (
    STEP_ID_FIELDS,
    SUMMARY_FIELDS,
    Stopwatch,
    deduction_metrics,
    kb_metrics,
    step_rows,
    uniqueness_metrics,
    verdicts_correct,
)

DEFAULT_PUZZLE_DIR = SOURCE_ROOT / "puzzles"
DEFAULT_OUT_DIR = SOURCE_ROOT / "experiments" / "results"
DEFAULT_TIME_LIMIT = 30.0           # giây cho mỗi SAT query

SUMMARY_FILE = "benchmark_summary.csv"
STEPS_FILE = "benchmark_steps.csv"
TRACE_DIR = "traces"

LOAD_ERROR = "LOAD_ERROR"           # không đọc được puzzle
ERROR = "ERROR"                     # lỗi ngoài dự kiến khi chạy

MODEL_REUSE_MODES = {"on": (True,), "off": (False,), "both": (True, False)}


@dataclass
class RunResult:
    """Kết quả một lần chạy trên một puzzle"""
    summary: dict[str, Any]
    steps: list[dict[str, Any]] = field(default_factory=list)
    trace_text: str | None = None


# Chạy một puzzle

def run_puzzle(path: Path, reuse_models: bool, run: int, time_limit: float | None) -> RunResult:
    """
    Chạy uniqueness check và vòng suy diễn trên một file puzzle
    Không bao giờ ném lỗi ra ngoài (trừ KeyboardInterrupt): lỗi được ghi vào dòng kết quả
    """
    row: dict[str, Any] = {
        "puzzle_id": path.stem,
        "size": _size_from_path(path),
        "file": _display_path(path),
        "model_reuse": _mode_name(reuse_models),
        "run": run,
    }

    # Bắt Exception rộng là có chủ đích: benchmark phải ghi lại mọi failure thay vì dừng cả lượt chạy
    try:
        puzzle = load_puzzle(path)
    except Exception as exc:
        row["status"] = LOAD_ERROR
        _add_error(row, "load", exc)
        return RunResult(row)

    row["puzzle_id"] = puzzle.puzzle_id
    row["size"] = puzzle.board.size

    # Lưới an toàn cuối cùng cho lỗi nằm ngoài các vùng đã bắt riêng
    try:
        _run_uniqueness(puzzle, row, time_limit)
        return _run_deduction(puzzle, row, reuse_models, time_limit)
    except Exception as exc:
        row["status"] = ERROR
        _add_error(row, "harness", exc)
        return RunResult(row)


def _run_uniqueness(puzzle: PuzzleFull, row: dict[str, Any], time_limit: float | None) -> None:
    """Uniqueness check trên bộ clue đầy đủ, tách riêng khỏi vòng suy diễn"""
    stopwatch = Stopwatch()
    try:
        with stopwatch:
            result = check_puzzle_uniqueness(puzzle, time_limit)
    except Exception as exc:
        row.update(uniqueness=ERROR, uniq_runtime=stopwatch.elapsed)
        _add_error(row, "uniqueness", exc)
        return
    row.update(uniqueness_metrics(result, stopwatch.elapsed))


def _run_deduction(puzzle: PuzzleFull, row: dict[str, Any], reuse_models: bool,
                   time_limit: float | None) -> RunResult:
    """
    Vòng suy diễn của Logic Agent trên GameEngine
    + Agent tự xử lý timeout (status TIMEOUT); lỗi khác vẫn giữ trace dở dang để ghi số liệu
    + Engine và agent dùng chung time_limit cho mỗi SAT query
    """
    engine = GameEngine(puzzle, time_limit)
    agent = LogicAgent(engine, time_limit=time_limit, reuse_models=reuse_models)
    stopwatch = Stopwatch()
    failure: Exception | None = None
    try:
        with stopwatch:
            agent.run()
    except Exception as exc:
        failure = exc

    row["runtime"] = stopwatch.elapsed
    failed = failure is not None
    if failed:
        _add_error(row, "deduction", failure)

    trace = agent.trace     # trace đầy đủ, hoặc dở dang nếu có lỗi
    try:
        row.update(deduction_metrics(trace, engine))
        row.update(kb_metrics(puzzle.initial_state(), engine.state))
        row["verdicts_correct"] = verdicts_correct(puzzle, engine.state)
    except Exception as exc:
        failed = True
        _add_error(row, "metrics", exc)
    if failed:
        # Ghi đè status của trace (hoặc đặt mới nếu deduction_metrics chưa kịp ghi)
        row["status"] = ERROR

    id_columns = {key: row[key] for key in STEP_ID_FIELDS}
    steps = [{**id_columns, **step} for step in step_rows(trace)]

    # Trace văn bản chỉ là đầu ra phụ: lỗi ở đây được ghi vào cột error nhưng không đổi status
    try:
        trace_text = trace.to_text(puzzle.board)
    except Exception as exc:
        trace_text = None
        _add_error(row, "trace", exc)
    return RunResult(row, steps, trace_text)


# Chạy cả bộ puzzle

def select_puzzles(puzzle_dir: Path, sizes: Iterable[int] | None = None) -> tuple[Path, ...]:
    """Mọi file puzzle trong thư mục (theo thứ tự đường dẫn), lọc theo kích thước nếu có"""
    paths = discover_puzzles(puzzle_dir)
    if sizes is None:
        return paths
    wanted = set(sizes)
    return tuple(p for p in paths if _size_from_path(p) in wanted)


def run_benchmark(paths: Sequence[Path], reuse_modes: Sequence[bool], repeat: int,
                  time_limit: float | None, verbose: bool = True) -> list[RunResult]:
    """Chạy mọi puzzle với mọi chế độ, mỗi tổ hợp lặp repeat lần; thứ tự chạy xác định"""
    results: list[RunResult] = []
    total = len(paths) * len(reuse_modes) * repeat
    for path in paths:
        for reuse in reuse_modes:
            for run in range(1, repeat + 1):
                result = run_puzzle(path, reuse, run, time_limit)
                results.append(result)
                if verbose:
                    print(f"[{len(results)}/{total}] {_progress_line(result.summary)}")
    return results


# Ghi kết quả

def write_results(results: Sequence[RunResult], out_dir: Path, save_traces: bool = False) -> list[Path]:
    """Ghi các file CSV (và trace nếu cần), trả về danh sách file đã ghi"""
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / SUMMARY_FILE
    steps_path = out_dir / STEPS_FILE

    _write_csv(summary_path, SUMMARY_FIELDS, (r.summary for r in results))
    step_list = [step for r in results for step in r.steps]
    _write_csv(steps_path, _step_fields(step_list), step_list)
    written = [summary_path, steps_path]

    if save_traces:
        trace_dir = out_dir / TRACE_DIR
        trace_dir.mkdir(exist_ok=True)
        for r in results:
            if r.trace_text is None:
                continue
            s = r.summary
            path = trace_dir / f"{s['puzzle_id']}_{s['model_reuse']}_run{s['run']}.txt"
            path.write_text(r.trace_text + "\n", encoding="utf-8")
            written.append(path)
    return written


def _write_csv(path: Path, fields: Sequence[str], rows: Iterable[dict[str, Any]]) -> None:
    """Cột thiếu để trống (restval); cột lạ là lỗi lập trình nên để DictWriter báo lỗi"""
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(fields), restval="")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _format_cell(value) for key, value in row.items()})


def _step_fields(steps: Sequence[dict[str, Any]]) -> list[str]:
    """Cột của file steps: cột định danh trước, sau đó khoá của TraceStep.as_dict theo thứ tự xuất hiện"""
    fields = list(STEP_ID_FIELDS)
    seen = set(fields)
    for step in steps:
        for key in step:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    return fields


def _format_cell(value: Any) -> Any:
    """Số thực ghi 6 chữ số thập phân cho dễ đọc, giá trị khác giữ nguyên"""
    return f"{value:.6f}" if isinstance(value, float) else value


# Tiện ích

def _size_from_path(path: Path) -> int | str:
    """Đoán N từ tiền tố tên file hoặc các thư mục cha; dùng cho lọc và cho dòng LOAD_ERROR"""
    candidates = [path.stem.split("_", 1)[0]] + list(reversed(path.parts[:-1]))
    for name in candidates:
        rows, sep, cols = name.partition("x")
        if sep and rows.isdigit() and rows == cols:
            return int(rows)
    return ""


def _display_path(path: Path) -> str:
    """Đường dẫn tương đối với Source nếu được, để CSV không phụ thuộc máy chạy"""
    try:
        return path.resolve().relative_to(SOURCE_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _mode_name(reuse_models: bool) -> str:
    return "on" if reuse_models else "off"


def _add_error(row: dict[str, Any], stage: str, exc: Exception) -> None:
    """Ghép thông báo lỗi theo giai đoạn; một dòng có thể có lỗi ở nhiều giai đoạn"""
    message = f"{stage}: {type(exc).__name__}: {exc}"
    row["error"] = f"{row['error']} | {message}" if row.get("error") else message


def _progress_line(row: dict[str, Any]) -> str:
    """Một dòng tiến độ trên console"""
    line = f"{row['puzzle_id']} (reuse={row['model_reuse']}, run {row['run']}): {row.get('status', '')}"
    if "steps" in row:
        line += (f", {row['steps']} steps, {row['sat_calls']} SAT calls, "
                 f"{row['runtime'] * 1000:.1f} ms, uniqueness {row.get('uniqueness', '-')}")
    if row.get("error"):
        line += f" [{row['error']}]"
    return line


def _print_overview(results: Sequence[RunResult]) -> None:
    """Đếm số lần chạy theo trạng thái; bảng / biểu đồ chi tiết thuộc về plot_results"""
    counts: dict[str, int] = {}
    for r in results:
        key = f"{r.summary.get('status', '')}/{r.summary.get('uniqueness', '-')}"
        counts[key] = counts.get(key, 0) + 1
    detail = ", ".join(f"{key}: {n}" for key, n in sorted(counts.items()))
    print(f"\n{len(results)} runs (status/uniqueness) -> {detail}")


# CLI

def _positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError(f"phải >= 1, nhận được {value}")
    return value


def _time_limit(text: str) -> float | None:
    """Số giây > 0; 0 nghĩa là không giới hạn"""
    value = float(text)
    if value < 0:
        raise argparse.ArgumentTypeError(f"phải >= 0, nhận được {value}")
    return value or None


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m experiments.run_benchmark",
        description="Chạy Logic Agent và uniqueness check trên mọi puzzle, xuất kết quả ra CSV.",
    )
    parser.add_argument("--puzzle-dir", type=Path, default=DEFAULT_PUZZLE_DIR,
                        help="thư mục chứa puzzle JSON (quét đệ quy), mặc định: Source/puzzles")
    parser.add_argument("--sizes", type=int, nargs="+", metavar="N",
                        help="chỉ chạy puzzle kích thước N x N, vd. --sizes 3 4")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR,
                        help="thư mục ghi kết quả, mặc định: Source/experiments/results")
    parser.add_argument("--time-limit", type=_time_limit, default=DEFAULT_TIME_LIMIT, metavar="SEC",
                        help=f"giới hạn giây cho mỗi SAT query, 0 = không giới hạn (mặc định {DEFAULT_TIME_LIMIT:g})")
    parser.add_argument("--model-reuse", choices=tuple(MODEL_REUSE_MODES), default="on",
                        help="bật / tắt tái sử dụng model của agent, 'both' để so sánh (mặc định on)")
    parser.add_argument("--repeat", type=_positive_int, default=1,
                        help="số lần chạy lặp lại mỗi puzzle để lấy trung bình runtime (mặc định 1)")
    parser.add_argument("--save-traces", action="store_true",
                        help="ghi thêm deduction trace dạng văn bản cho từng lần chạy")
    parser.add_argument("--quiet", action="store_true", help="không in tiến độ từng lần chạy")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    paths = select_puzzles(args.puzzle_dir, args.sizes)
    if not paths:
        print(f"Không tìm thấy puzzle nào trong {args.puzzle_dir}", file=sys.stderr)
        return 1

    results = run_benchmark(paths, MODEL_REUSE_MODES[args.model_reuse], args.repeat,
                            args.time_limit, verbose=not args.quiet)
    written = write_results(results, args.out_dir, args.save_traces)

    _print_overview(results)
    print(f"Đã ghi {written[0]} và {written[1]}"
          + (f" cùng {len(written) - 2} file trace" if args.save_traces else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())