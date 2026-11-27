"""
Unit tests cho experiments/plot_results.py:
- Kiểm tra nạp và tiền xử lý dữ liệu CSV (summary, steps)
- Kiểm tra phân tích ca lỗi, timeout (bình thường và khi có lỗi giả lập)
- Kiểm tra tính toán tổng hợp theo kích thước và so sánh model reuse
- Kiểm tra xuất bảng báo cáo (Markdown, Text, CSV)
- Kiểm tra vẽ các biểu đồ hiệu năng
- Kiểm tra giao diện dòng lệnh (CLI main)
"""

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from experiments.plot_results import (
    DEFAULT_STEPS_FILE,
    DEFAULT_SUMMARY_FILE,
    OUTCOME_AGENT_TIMEOUT,
    OUTCOME_AMBIGUOUS,
    OUTCOME_ERROR,
    OUTCOME_INCONSISTENT,
    OUTCOME_LOAD_ERROR,
    OUTCOME_ORDER,
    OUTCOME_SOLVED,
    OUTCOME_UNIQ_TIMEOUT,
    analyze_failures_and_timeouts,
    classify_outcomes,
    compute_model_reuse_comparison,
    compute_summary_by_size,
    generate_all_plots_and_tables,
    generate_report_tables,
    load_steps_data,
    load_summary_data,
    main,
    plot_encoding_complexity,
    plot_overview_dashboard,
    plot_runtime_comparison,
    plot_sat_calls,
    plot_solver_operations,
    plot_speedup_and_savings,
    plot_status_distribution,
    plot_step_dynamics,
)


# ==============================================================================
# FIXTURES
# ==============================================================================

@pytest.fixture
def sample_summary_df() -> pd.DataFrame:
    """Tập dữ liệu mẫu nhỏ đầy đủ các cột và kích thước 3x3, 4x4, 5x5"""
    data: list[dict[str, Any]] = [
        # 3x3
        {
            "puzzle_id": "3x3_01", "size": "3", "model_reuse": "on", "run": "1",
            "status": "SOLVED", "verdicts_correct": "True", "error": "",
            "full_main_vars": "9", "full_aux_vars": "0", "full_clauses": "20",
            "kb0_clauses": "3", "kb_final_clauses": "25", "initial_revealed": "1", "steps": "8",
            "sat_calls": "60", "agent_sat_calls": "44", "engine_sat_calls": "16", "skipped_queries": "30",
            "decisions": "10", "propagations": "200", "pure_literals": "0", "backtracks": "0",
            "runtime": "0.003", "solver_time": "0.001", "uniqueness": "UNIQUE",
            "uniq_runtime": "0.0003", "uniq_sat_calls": "2",
        },
        {
            "puzzle_id": "3x3_01", "size": "3", "model_reuse": "off", "run": "1",
            "status": "SOLVED", "verdicts_correct": "True", "error": "",
            "full_main_vars": "9", "full_aux_vars": "0", "full_clauses": "20",
            "kb0_clauses": "3", "kb_final_clauses": "25", "initial_revealed": "1", "steps": "8",
            "sat_calls": "90", "agent_sat_calls": "74", "engine_sat_calls": "16", "skipped_queries": "0",
            "decisions": "20", "propagations": "400", "pure_literals": "0", "backtracks": "0",
            "runtime": "0.005", "solver_time": "0.002", "uniqueness": "UNIQUE",
            "uniq_runtime": "0.0003", "uniq_sat_calls": "2",
        },
        # 4x4
        {
            "puzzle_id": "4x4_01", "size": "4", "model_reuse": "on", "run": "1",
            "status": "SOLVED", "verdicts_correct": "True", "error": "",
            "full_main_vars": "16", "full_aux_vars": "5", "full_clauses": "100",
            "kb0_clauses": "10", "kb_final_clauses": "110", "initial_revealed": "2", "steps": "14",
            "sat_calls": "140", "agent_sat_calls": "110", "engine_sat_calls": "30", "skipped_queries": "90",
            "decisions": "50", "propagations": "1500", "pure_literals": "10", "backtracks": "2",
            "runtime": "0.020", "solver_time": "0.005", "uniqueness": "UNIQUE",
            "uniq_runtime": "0.001", "uniq_sat_calls": "2",
        },
        {
            "puzzle_id": "4x4_01", "size": "4", "model_reuse": "off", "run": "1",
            "status": "SOLVED", "verdicts_correct": "True", "error": "",
            "full_main_vars": "16", "full_aux_vars": "5", "full_clauses": "100",
            "kb0_clauses": "10", "kb_final_clauses": "110", "initial_revealed": "2", "steps": "14",
            "sat_calls": "230", "agent_sat_calls": "200", "engine_sat_calls": "30", "skipped_queries": "0",
            "decisions": "100", "propagations": "2500", "pure_literals": "20", "backtracks": "2",
            "runtime": "0.030", "solver_time": "0.010", "uniqueness": "UNIQUE",
            "uniq_runtime": "0.001", "uniq_sat_calls": "2",
        },
        # 5x5
        {
            "puzzle_id": "5x5_01", "size": "5", "model_reuse": "on", "run": "1",
            "status": "SOLVED", "verdicts_correct": "True", "error": "",
            "full_main_vars": "25", "full_aux_vars": "10", "full_clauses": "250",
            "kb0_clauses": "20", "kb_final_clauses": "260", "initial_revealed": "3", "steps": "22",
            "sat_calls": "300", "agent_sat_calls": "250", "engine_sat_calls": "50", "skipped_queries": "240",
            "decisions": "250", "propagations": "4000", "pure_literals": "50", "backtracks": "1",
            "runtime": "0.080", "solver_time": "0.035", "uniqueness": "UNIQUE",
            "uniq_runtime": "0.002", "uniq_sat_calls": "2",
        },
        {
            "puzzle_id": "5x5_01", "size": "5", "model_reuse": "off", "run": "1",
            "status": "SOLVED", "verdicts_correct": "True", "error": "",
            "full_main_vars": "25", "full_aux_vars": "10", "full_clauses": "250",
            "kb0_clauses": "20", "kb_final_clauses": "260", "initial_revealed": "3", "steps": "22",
            "sat_calls": "550", "agent_sat_calls": "500", "engine_sat_calls": "50", "skipped_queries": "0",
            "decisions": "500", "propagations": "8000", "pure_literals": "100", "backtracks": "2",
            "runtime": "0.150", "solver_time": "0.090", "uniqueness": "UNIQUE",
            "uniq_runtime": "0.002", "uniq_sat_calls": "2",
        },
    ]
    df = pd.DataFrame(data)
    # Gán các cột số
    numeric_cols = [
        "size", "full_main_vars", "full_aux_vars", "full_clauses",
        "kb0_clauses", "kb_final_clauses", "initial_revealed", "steps",
        "sat_calls", "agent_sat_calls", "engine_sat_calls", "skipped_queries",
        "decisions", "propagations", "pure_literals", "backtracks",
        "runtime", "solver_time", "uniq_runtime", "uniq_sat_calls",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["size_label"] = df["size"].apply(lambda s: f"{int(s)}x{int(s)}")
    return df


# ==============================================================================
# TESTS CHO ĐỌC VÀ TIỀN XỬ LÝ DỮ LIỆU
# ==============================================================================

def test_load_summary_data_real_file() -> None:
    """Nạp file benchmark_summary.csv thực tế trong experiments/results"""
    if not DEFAULT_SUMMARY_FILE.is_file():
        pytest.skip("benchmark_summary.csv chưa được tạo")

    df = load_summary_data(DEFAULT_SUMMARY_FILE)
    assert not df.empty
    assert "size_label" in df.columns
    assert set(df["size_label"].unique()) == {"3x3", "4x4", "5x5"}
    assert "status" in df.columns
    assert "model_reuse" in df.columns
    assert "runtime" in df.columns
    assert df["runtime"].dtype in ("float64", "float32")


def test_load_summary_data_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_summary_data(tmp_path / "nonexistent.csv")


def test_load_steps_data_real_or_none(tmp_path: Path) -> None:
    res = load_steps_data(tmp_path / "nonexistent.csv")
    assert res is None

    if DEFAULT_STEPS_FILE.is_file():
        steps_df = load_steps_data(DEFAULT_STEPS_FILE)
        assert steps_df is not None
        assert "step" in steps_df.columns


# ==============================================================================
# TESTS PHÂN TÍCH CA LỖI VÀ TIMEOUT (MỤC 4.5 & 4.6)
# ==============================================================================

def test_analyze_failures_all_success(sample_summary_df: pd.DataFrame) -> None:
    res = analyze_failures_and_timeouts(sample_summary_df)
    assert res["total_runs"] == 6
    assert res["solved_count"] == 6
    assert res["timeout_count"] == 0
    assert res["exec_error_count"] == 0
    assert res["load_error_count"] == 0
    assert res["failure_count"] == 0
    assert res["unique_count"] == 6
    assert res["verdicts_correct_count"] == 6
    assert res["outcome_counts"][OUTCOME_SOLVED] == 6
    assert sum(res["outcome_counts"].values()) == res["total_runs"]
    assert len(res["failure_rows"]) == 0
    assert "3x3" in res["breakdown_by_size"]


def test_analyze_failures_with_injected_errors() -> None:
    """Kiểm tra phát hiện và ghi nhận đầy đủ khi có TIMEOUT, ERROR và LOAD_ERROR"""
    df = pd.DataFrame([
        {"puzzle_id": "3x3_01", "size": 3, "size_label": "3x3", "model_reuse": "on", "run": 1, "status": "SOLVED", "error": "", "uniqueness": "UNIQUE"},
        {"puzzle_id": "4x4_bad", "size": 4, "size_label": "4x4", "model_reuse": "on", "run": 1, "status": "LOAD_ERROR", "error": "load: FileNotFoundError: bad.json", "uniqueness": "-"},
        {"puzzle_id": "5x5_crash", "size": 5, "size_label": "5x5", "model_reuse": "off", "run": 1, "status": "ERROR", "error": "deduction: EngineInvariantError: rejected", "uniqueness": "UNIQUE"},
        {"puzzle_id": "5x5_slow", "size": 5, "size_label": "5x5", "model_reuse": "off", "run": 1, "status": "TIMEOUT", "error": "TimeoutError: exceeded limit", "uniqueness": "TIMEOUT"},
    ])
    res = analyze_failures_and_timeouts(df)
    assert res["total_runs"] == 4
    assert res["solved_count"] == 1
    assert res["load_error_count"] == 1
    assert res["exec_error_count"] == 1  # LOAD_ERROR và TIMEOUT không cộng vào ERROR
    assert res["agent_timeout_count"] == 1
    assert res["uniq_timeout_count"] == 0
    assert res["timeout_count"] == 1
    assert res["failure_count"] == 3

    assert res["outcome_counts"] == {
        OUTCOME_SOLVED: 1,
        OUTCOME_AGENT_TIMEOUT: 1,
        OUTCOME_UNIQ_TIMEOUT: 0,
        OUTCOME_AMBIGUOUS: 0,
        OUTCOME_INCONSISTENT: 0,
        OUTCOME_LOAD_ERROR: 1,
        OUTCOME_ERROR: 1,
    }
    assert sum(res["outcome_counts"].values()) == res["total_runs"]

    assert len(res["failure_rows"]) == 3
    failed_puzzles = {r["puzzle_id"] for r in res["failure_rows"]}
    assert failed_puzzles == {"4x4_bad", "5x5_crash", "5x5_slow"}

    # Kiểm tra breakdown theo size, các nhóm không chồng lấn
    b = res["breakdown_by_size"]
    assert b["3x3"]["solved"] == 1
    assert b["4x4"]["load_error"] == 1
    assert b["4x4"]["error"] == 0
    assert b["5x5"]["agent_timeout"] == 1
    assert b["5x5"]["timeout"] == 1
    assert b["5x5"]["error"] == 1
    for stats in b.values():
        assert sum(stats["outcome_counts"].values()) == stats["total"]


def test_solved_but_non_unique_or_wrong_verdict_is_failure() -> None:
    """SOLVED chỉ được coi là thành công khi uniqueness=UNIQUE và verdicts_correct=True"""
    df = pd.DataFrame([
        {"puzzle_id": "a", "size": 3, "size_label": "3x3", "model_reuse": "on", "run": 1, "status": "SOLVED", "error": "", "uniqueness": "MULTIPLE", "verdicts_correct": "True"},
        {"puzzle_id": "b", "size": 3, "size_label": "3x3", "model_reuse": "on", "run": 1, "status": "SOLVED", "error": "", "uniqueness": "NO_SOLUTION", "verdicts_correct": "True"},
        {"puzzle_id": "c", "size": 3, "size_label": "3x3", "model_reuse": "on", "run": 1, "status": "SOLVED", "error": "", "uniqueness": "UNIQUE", "verdicts_correct": "False"},
        {"puzzle_id": "d", "size": 3, "size_label": "3x3", "model_reuse": "on", "run": 1, "status": "SOLVED", "error": "", "uniqueness": "UNIQUE", "verdicts_correct": "True"},
    ])
    res = analyze_failures_and_timeouts(df)
    assert res["solved_count"] == 1
    assert res["ambiguous_count"] == 1
    assert res["inconsistent_count"] == 1
    assert res["exec_error_count"] == 1
    assert res["failure_count"] == 3
    assert res["unique_count"] == 2
    assert res["verdicts_correct_count"] == 3
    assert set(classify_outcomes(df)) == {
        OUTCOME_AMBIGUOUS, OUTCOME_INCONSISTENT, OUTCOME_ERROR, OUTCOME_SOLVED,
    }


def test_solved_with_uniq_timeout_is_not_double_counted() -> None:
    df = pd.DataFrame([
        {"puzzle_id": "a", "size": 4, "size_label": "4x4", "model_reuse": "on", "run": 1, "status": "SOLVED", "error": "", "uniqueness": "TIMEOUT", "verdicts_correct": "True"},
    ])
    res = analyze_failures_and_timeouts(df)
    assert res["solved_count"] == 0
    assert res["agent_timeout_count"] == 0
    assert res["uniq_timeout_count"] == 1
    assert res["failure_count"] == 1
    assert res["outcome_counts"][OUTCOME_UNIQ_TIMEOUT] == 1


def test_outcomes_are_mutually_exclusive(sample_summary_df: pd.DataFrame) -> None:
    outcome = classify_outcomes(sample_summary_df)
    assert len(outcome) == len(sample_summary_df)
    assert set(outcome).issubset(set(OUTCOME_ORDER))
    res = analyze_failures_and_timeouts(sample_summary_df)
    assert sum(res["outcome_counts"].values()) == res["total_runs"]


def test_load_summary_data_missing_error_is_not_exec_error() -> None:
    """Ô error trống phải là NaN/chuỗi rỗng, không được biến thành 'nan' và bị đếm là lỗi"""
    if not DEFAULT_SUMMARY_FILE.is_file():
        pytest.skip("benchmark_summary.csv chưa được tạo")

    df = load_summary_data(DEFAULT_SUMMARY_FILE)
    solved_rows = df[df["status"] == "SOLVED"]
    assert not (solved_rows["error"] == "nan").any()
    res = analyze_failures_and_timeouts(df)
    assert res["exec_error_count"] == 0


# ==============================================================================
# TESTS TÍNH TOÁN VÀ BẢNG SỐ LIỆU
# ==============================================================================

def test_compute_summary_by_size(sample_summary_df: pd.DataFrame) -> None:
    res = compute_summary_by_size(sample_summary_df)
    assert not res.empty
    assert len(res) == 6  # 3 kích thước x 2 chế độ on/off
    assert "Kích thước" in res.columns
    assert "Tổng SAT calls" in res.columns
    assert "Runtime TB (ms)" in res.columns


def test_compute_model_reuse_comparison(sample_summary_df: pd.DataFrame) -> None:
    res = compute_model_reuse_comparison(sample_summary_df)
    assert not res.empty
    assert len(res) == 3  # 3x3, 4x4, 5x5
    assert "Kích thước" in res.columns
    assert "Tiết kiệm SAT (%)" in res.columns
    assert "Hệ số tăng tốc (Speedup)" in res.columns

    # Kiểm tra hệ số speedup > 1.0 trên dữ liệu mẫu
    for speedup in res["_raw_speedup"]:
        assert speedup > 1.0


def test_generate_report_tables(sample_summary_df: pd.DataFrame, tmp_path: Path) -> None:
    res = generate_report_tables(sample_summary_df, tmp_path)
    assert "text" in res
    assert (tmp_path / "summary_by_size.csv").is_file()
    assert (tmp_path / "model_reuse_comparison.csv").is_file()

    txt_text = res["text"]
    assert "FAILURES & TIMEOUTS" in txt_text
    assert "MODEL REUSE" in txt_text
    assert "AGENT_TIMEOUT" in txt_text
    assert "UNIQ_TIMEOUT" in txt_text
    assert "AMBIGUOUS" in txt_text
    assert "INCONSISTENT" in txt_text


def test_report_note_uses_real_counts(sample_summary_df: pd.DataFrame, tmp_path: Path) -> None:
    """Thông báo phải sinh từ dữ liệu thật, không hardcode 100% đúng/duy nhất"""
    df = sample_summary_df.copy()
    df.loc[df.index[0], "uniqueness"] = "MULTIPLE"

    res = generate_report_tables(df, tmp_path)
    text = res["text"]

    assert "5/6 lượt có uniqueness=UNIQUE" in text
    assert "6/6 lượt có verdicts_correct=True" in text
    assert "100% các câu đố" not in text
    assert "AMBIGUOUS" in text


# ==============================================================================
# TESTS VẼ BIỂU ĐỒ (MATPLOTLIB)
# ==============================================================================

def test_all_plots_generation(sample_summary_df: pd.DataFrame, tmp_path: Path) -> None:
    """Kiểm tra gọi tất cả các hàm vẽ biểu đồ sinh file ảnh hợp lệ (không rỗng)"""
    dpi = 50  # DPI thấp để test chạy nhanh

    assert plot_runtime_comparison(sample_summary_df, tmp_path / "runtime.png", dpi) is True
    assert plot_sat_calls(sample_summary_df, tmp_path / "sat_calls.png", dpi) is True
    assert plot_solver_operations(sample_summary_df, tmp_path / "solver_ops.png", dpi) is True
    assert plot_encoding_complexity(sample_summary_df, tmp_path / "encoding.png", dpi) is True
    assert plot_speedup_and_savings(sample_summary_df, tmp_path / "savings.png", dpi) is True
    assert plot_status_distribution(sample_summary_df, tmp_path / "status.png", dpi) is True
    assert plot_overview_dashboard(sample_summary_df, tmp_path / "dashboard.png", dpi) is True

    expected_plots = [
        "runtime.png", "sat_calls.png", "solver_ops.png",
        "encoding.png", "savings.png", "status.png", "dashboard.png",
    ]
    for p in expected_plots:
        f = tmp_path / p
        assert f.is_file(), f"Biểu đồ {p} không được tạo"
        assert f.stat().st_size > 0, f"Biểu đồ {p} bị rỗng"


def test_plot_functions_return_false_without_data(tmp_path: Path) -> None:
    empty = pd.DataFrame({"status": [], "size_label": [], "model_reuse": []})
    assert plot_runtime_comparison(empty, tmp_path / "runtime.png") is False
    assert plot_sat_calls(empty, tmp_path / "sat_calls.png") is False
    assert plot_solver_operations(empty, tmp_path / "solver_ops.png") is False
    assert plot_encoding_complexity(empty, tmp_path / "encoding.png") is False
    assert plot_speedup_and_savings(empty, tmp_path / "savings.png") is False
    assert plot_status_distribution(empty, tmp_path / "status.png") is False
    assert plot_overview_dashboard(empty, tmp_path / "dashboard.png") is False
    assert not list(tmp_path.glob("*.png"))


def test_step_dynamics_plot(tmp_path: Path) -> None:
    steps_df = pd.DataFrame([
        {"puzzle_id": "3x3_01", "size": 3, "model_reuse": "on", "run": 1, "step": 1, "num_active_clues": 1, "sat_queries": 9},
        {"puzzle_id": "3x3_01", "size": 3, "model_reuse": "on", "run": 1, "step": 2, "num_active_clues": 2, "sat_queries": 8},
        {"puzzle_id": "4x4_01", "size": 4, "model_reuse": "on", "run": 1, "step": 1, "num_active_clues": 2, "sat_queries": 15},
    ])
    out_file = tmp_path / "step_dynamics.png"
    assert plot_step_dynamics(steps_df, out_file, dpi=50) is True
    assert out_file.is_file()
    assert out_file.stat().st_size > 0


# ==============================================================================
# TESTS GIAO DIỆN DÒNG LỆNH (CLI)
# ==============================================================================

def test_cli_main_help() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0


def test_generate_all_returns_files_and_no_failures(tmp_path: Path) -> None:
    if not DEFAULT_SUMMARY_FILE.is_file():
        pytest.skip("benchmark_summary.csv chưa có")

    files, failures = generate_all_plots_and_tables(
        summary_path=DEFAULT_SUMMARY_FILE,
        steps_path=DEFAULT_STEPS_FILE,
        out_dir=tmp_path,
        dpi=50,
        quiet=True,
    )
    assert failures == []
    assert files
    assert all(p.is_file() for p in files)
    assert (tmp_path / "overview_dashboard.png") in files


def test_cli_main_plot_failure_returns_nonzero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if not DEFAULT_SUMMARY_FILE.is_file():
        pytest.skip("benchmark_summary.csv chưa có")

    def boom(*args: Any, **kwargs: Any) -> bool:
        raise RuntimeError("boom")

    monkeypatch.setattr("experiments.plot_results.plot_runtime_comparison", boom)
    exit_code = main([
        "--summary-csv", str(DEFAULT_SUMMARY_FILE),
        "--steps-csv", str(DEFAULT_STEPS_FILE),
        "--out-dir", str(tmp_path),
        "--dpi", "50",
        "--quiet",
    ])
    assert exit_code == 3


def test_cli_main_execution(tmp_path: Path) -> None:
    if not DEFAULT_SUMMARY_FILE.is_file():
        pytest.skip("benchmark_summary.csv chưa có")

    exit_code = main([
        "--summary-csv", str(DEFAULT_SUMMARY_FILE),
        "--steps-csv", str(DEFAULT_STEPS_FILE),
        "--out-dir", str(tmp_path),
        "--dpi", "50",
        "--quiet",
    ])
    assert exit_code == 0
    assert (tmp_path / "summary_by_size.csv").is_file()
    assert (tmp_path / "model_reuse_comparison.csv").is_file()
    assert (tmp_path / "overview_dashboard.png").is_file()


def test_cli_main_not_found_csv(tmp_path: Path) -> None:
    exit_code = main(["--summary-csv", str(tmp_path / "nonexistent.csv")])
    assert exit_code == 1


def test_solved_but_non_unique_or_wrong_verdict_excluded_from_metrics(sample_summary_df: pd.DataFrame) -> None:
    """Lượt SOLVED nhưng uniqueness != UNIQUE hoặc verdicts_correct=False không được tính vào bảng hiệu năng"""
    df = sample_summary_df.copy()
    df.loc[df.index[0], "uniqueness"] = "MULTIPLE"
    df.loc[df.index[1], "verdicts_correct"] = "False"

    summary = compute_summary_by_size(df)
    assert "3x3" not in set(summary["Kích thước"])
    assert summary["Số lượt chạy"].sum() == 4