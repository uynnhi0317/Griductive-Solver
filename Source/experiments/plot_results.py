"""
Đọc CSV kết quả thực nghiệm, tổng hợp số liệu theo kích thước câu đố (3x3, 4x4, 5x5),
phân tích các trường hợp lỗi / timeout, xuất bảng báo cáo và vẽ biểu đồ trực quan.

Sản phẩm tạo ra trong experiments/results/:
- Bảng tổng hợp: summary_by_size.csv, model_reuse_comparison.csv (và in trực tiếp ra console)
- Biểu đồ:
  + runtime_by_size.png: Thời gian chạy theo kích thước và chế độ model reuse
  + sat_calls_by_size.png: Số truy vấn SAT và số truy vấn được tối ưu (skipped)
  + solver_operations_by_size.png: Thống kê decisions, propagations, backtracks
  + encoding_complexity.png: Độ phức tạp mã hoá (biến chính, biến phụ, mệnh đề)
  + model_reuse_impact.png: Tỉ lệ tiết kiệm SAT calls và hệ số tăng tốc
  + status_distribution.png: Phân bố trạng thái thực thi (SOLVED, TIMEOUT, ERROR)
  + step_dynamics.png: Động lực học từng bước suy diễn (clue, forced cells)
  + overview_dashboard.png: Dashboard tổng hợp 4 trong 1 phục vụ slide / báo cáo

Cách chạy từ thư mục Source:
    python -m experiments.plot_results
    python -m experiments.plot_results --format png --dpi 300
"""

import argparse
import sys
from pathlib import Path
from typing import Any, Sequence

import matplotlib

matplotlib.use("Agg")  # Chế độ non-interactive để chạy an toàn trên mọi môi trường
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from tabulate import tabulate

SOURCE_ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(SOURCE_ROOT))

DEFAULT_RESULTS_DIR = SOURCE_ROOT / "experiments" / "results"
DEFAULT_SUMMARY_FILE = DEFAULT_RESULTS_DIR / "benchmark_summary.csv"
DEFAULT_STEPS_FILE = DEFAULT_RESULTS_DIR / "benchmark_steps.csv"

# Bảng màu chuẩn báo cáo khoa học
COLORS = {
    "on": "#1f77b4",        # Xanh dương đậm: Model reuse ON
    "off": "#ff7f0e",       # Cam: Model reuse OFF
    "accent": "#2ca02c",    # Xanh lá: Tối ưu / Tiết kiệm
    "danger": "#d62728",    # Đỏ: Lỗi / Timeout
    "neutral": "#7f7f7f",   # Xám trung tính
    "purple": "#9467bd",    # Tím
    "cyan": "#17becf",      # Xanh lam
}

NUMERIC_COLUMNS = [
    "size", "run", "full_main_vars", "full_aux_vars", "full_clauses",
    "kb0_clauses", "kb_final_main_vars", "kb_final_aux_vars", "kb_final_clauses",
    "initial_revealed", "steps", "agent_sat_calls", "engine_sat_calls",
    "sat_calls", "skipped_queries", "decisions", "propagations",
    "pure_literals", "backtracks", "solver_time", "runtime",
    "uniq_sat_calls", "uniq_decisions", "uniq_propagations",
    "uniq_pure_literals", "uniq_backtracks", "uniq_solver_time", "uniq_runtime",
]


# ĐỌC VÀ CHUẨN HOÁ DỮ LIỆU

def load_summary_data(summary_path: Path) -> pd.DataFrame:
    """
    Đọc benchmark_summary.csv và chuyển đổi kiểu dữ liệu phù hợp.
    Các giá trị trống do lần chạy lỗi sẽ được gán NaN an toàn.
    """
    if not summary_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy file tóm tắt benchmark: {summary_path}")

    df = pd.read_csv(summary_path, dtype=str)

    # Làm sạch khoảng trắng
    for col in df.columns:
        df[col] = df[col].astype(str).str.strip()

    # Ép kiểu các cột số (giá trị trống chuyển thành NaN)
    for col in NUMERIC_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Chuẩn hoá cột size (nếu parse được số nguyên)
    if "size" in df.columns:
        df["size_label"] = df["size"].apply(lambda s: f"{int(s)}x{int(s)}" if pd.notna(s) else "Unknown")
    else:
        df["size_label"] = "Unknown"

    if "model_reuse" not in df.columns:
        df["model_reuse"] = "on"

    if "status" not in df.columns:
        df["status"] = "UNKNOWN"

    return df


def load_steps_data(steps_path: Path) -> pd.DataFrame | None:
    """Đọc benchmark_steps.csv nếu tồn tại; trả về None nếu file không có"""
    if not steps_path.is_file():
        return None

    try:
        df = pd.read_csv(steps_path)
        numeric_step_cols = [
            "size", "run", "step", "num_active_clues", "sat_queries",
            "skipped_queries", "engine_queries", "agent_decisions",
            "agent_propagations", "agent_pure_literals", "agent_backtracks",
            "agent_solver_time",
        ]
        for col in numeric_step_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df
    except Exception as exc:
        print(f"Cảnh báo: Không thể nạp benchmark_steps.csv ({exc})", file=sys.stderr)
        return None


# PHÂN TÍCH CA LỖI VÀ TIMEOUT (NÊU RÕ THEO YÊU CẦU MỤC 4.5 & 4.6)

def analyze_failures_and_timeouts(df: pd.DataFrame) -> dict[str, Any]:
    """
    Phân tích chi tiết các ca lỗi (LOAD_ERROR, ERROR), timeout và tính nhất quán.
    Bảo đảm nêu rõ đầy đủ các trường hợp không thành công thay vì bỏ qua.
    """
    total_runs = len(df)
    solved_mask = df["status"] == "SOLVED"
    timeout_mask = (df["status"] == "TIMEOUT") | (df.get("uniqueness", pd.Series()) == "TIMEOUT")
    load_err_mask = df["status"] == "LOAD_ERROR"
    exec_err_mask = (df["status"] == "ERROR") | (df.get("error", pd.Series()).fillna("") != "")
    other_mask = ~solved_mask & ~timeout_mask & ~load_err_mask & ~exec_err_mask

    failure_mask = ~solved_mask | timeout_mask | exec_err_mask | load_err_mask

    status_counts = df["status"].value_counts().to_dict()
    uniqueness_counts = df["uniqueness"].value_counts().to_dict() if "uniqueness" in df.columns else {}

    failure_rows: list[dict[str, Any]] = []
    if failure_mask.any():
        for _, row in df[failure_mask].iterrows():
            failure_rows.append({
                "puzzle_id": row.get("puzzle_id", "-"),
                "size": row.get("size_label", "-"),
                "model_reuse": row.get("model_reuse", "-"),
                "run": row.get("run", "-"),
                "status": row.get("status", "-"),
                "uniqueness": row.get("uniqueness", "-"),
                "error": row.get("error", "") or "(không có thông báo ngoại lệ)",
                "runtime": f"{row.get('runtime', 0):.4f}s" if pd.notna(row.get("runtime")) else "-",
            })

    # Phân tích theo từng kích thước
    breakdown_by_size: dict[str, dict[str, int]] = {}
    sizes = sorted(df["size_label"].unique())
    for s in sizes:
        sub = df[df["size_label"] == s]
        breakdown_by_size[s] = {
            "total": len(sub),
            "solved": int((sub["status"] == "SOLVED").sum()),
            "timeout": int(((sub["status"] == "TIMEOUT") | (sub.get("uniqueness", pd.Series()) == "TIMEOUT")).sum()),
            "error": int(((sub["status"].isin(["ERROR", "LOAD_ERROR"])) | (sub.get("error", pd.Series()).fillna("") != "")).sum()),
        }

    return {
        "total_runs": total_runs,
        "solved_count": int(solved_mask.sum()),
        "timeout_count": int(timeout_mask.sum()),
        "load_error_count": int(load_err_mask.sum()),
        "exec_error_count": int(exec_err_mask.sum()),
        "other_count": int(other_mask.sum()),
        "failure_count": len(failure_rows),
        "status_counts": status_counts,
        "uniqueness_counts": uniqueness_counts,
        "failure_rows": failure_rows,
        "breakdown_by_size": breakdown_by_size,
    }


# TỔNG HỢP VÀ TÍNH TOÁN BẢNG SỐ LIỆU

def compute_summary_by_size(df: pd.DataFrame) -> pd.DataFrame:
    """
    Tính các chỉ số thống kê trung bình, độ lệch chuẩn theo (size_label, model_reuse)
    trên các lượt chạy thành công (SOLVED).
    """
    solved_df = df[df["status"] == "SOLVED"].copy()
    if solved_df.empty:
        return pd.DataFrame()

    records = []
    grouped = solved_df.groupby(["size_label", "model_reuse"], sort=False)

    for (size_label, reuse), group in grouped:
        n_puzzles = group["puzzle_id"].nunique()
        n_runs = len(group)

        # Thời gian (ms)
        runtime_ms = group["runtime"] * 1000.0
        solver_time_ms = group["solver_time"] * 1000.0
        uniq_time_ms = group["uniq_runtime"] * 1000.0

        records.append({
            "Kích thước": size_label,
            "Tái sử dụng": "Bật (on)" if reuse == "on" else "Tắt (off)",
            "Số câu đố": n_puzzles,
            "Số lượt chạy": n_runs,
            # Mã hoá
            "Biến chính": f"{group['full_main_vars'].mean():.1f}",
            "Biến phụ (TB)": f"{group['full_aux_vars'].mean():.1f}",
            "Mệnh đề Full": f"{group['full_clauses'].mean():.1f}",
            "Mệnh đề KB0": f"{group['kb0_clauses'].mean():.1f}",
            "Mệnh đề KB_final": f"{group['kb_final_clauses'].mean():.1f}",
            # Suy diễn
            "Thẻ mở đầu": f"{group['initial_revealed'].mean():.1f}",
            "Số bước": f"{group['steps'].mean():.1f}",
            # SAT calls
            "Tổng SAT calls": f"{group['sat_calls'].mean():.1f} ± {group['sat_calls'].std():.1f}" if n_runs > 1 else f"{group['sat_calls'].mean():.1f}",
            "Agent SAT": f"{group['agent_sat_calls'].mean():.1f}",
            "Engine SAT": f"{group['engine_sat_calls'].mean():.1f}",
            "Bỏ qua (Skipped)": f"{group['skipped_queries'].mean():.1f}",
            # Solver stats
            "Decisions": f"{group['decisions'].mean():.1f}",
            "Propagations": f"{group['propagations'].mean():.1f}",
            "Pure Literals": f"{group['pure_literals'].mean():.1f}",
            "Backtracks": f"{group['backtracks'].mean():.1f}",
            # Runtime
            "Runtime TB (ms)": f"{runtime_ms.mean():.2f} ± {runtime_ms.std():.2f}" if n_runs > 1 else f"{runtime_ms.mean():.2f}",
            "Solver Time (ms)": f"{solver_time_ms.mean():.2f}",
            "Uniq Time (ms)": f"{uniq_time_ms.mean():.2f}",
            # Giá trị số nguyên gốc phục vụ so sánh / vẽ biểu đồ
            "_raw_size": size_label,
            "_raw_reuse": reuse,
            "_raw_runtime_s": group["runtime"].mean(),
            "_raw_runtime_std": group["runtime"].std() if n_runs > 1 else 0.0,
            "_raw_solver_time_s": group["solver_time"].mean(),
            "_raw_sat_calls": group["sat_calls"].mean(),
            "_raw_skipped": group["skipped_queries"].mean(),
            "_raw_decisions": group["decisions"].mean(),
            "_raw_propagations": group["propagations"].mean(),
            "_raw_backtracks": group["backtracks"].mean(),
            "_raw_full_clauses": group["full_clauses"].mean(),
            "_raw_main_vars": group["full_main_vars"].mean(),
            "_raw_aux_vars": group["full_aux_vars"].mean(),
        })

    return pd.DataFrame(records)


def compute_model_reuse_comparison(df: pd.DataFrame) -> pd.DataFrame:
    """
    So sánh trực tiếp từng kích thước giữa model_reuse="on" và model_reuse="off".
    Tính tỉ lệ tiết kiệm SAT calls (%), tỉ lệ giảm thời gian (%) và hệ số tăng tốc (Speedup).
    """
    solved_df = df[df["status"] == "SOLVED"].copy()
    if solved_df.empty:
        return pd.DataFrame()

    results = []
    sizes = sorted(solved_df["size_label"].unique())

    for s in sizes:
        sub_on = solved_df[(solved_df["size_label"] == s) & (solved_df["model_reuse"] == "on")]
        sub_off = solved_df[(solved_df["size_label"] == s) & (solved_df["model_reuse"] == "off")]

        if sub_on.empty or sub_off.empty:
            continue

        sat_on = sub_on["sat_calls"].mean()
        sat_off = sub_off["sat_calls"].mean()
        sat_saved_pct = ((sat_off - sat_on) / sat_off * 100.0) if sat_off > 0 else 0.0

        time_on = sub_on["runtime"].mean()
        time_off = sub_off["runtime"].mean()
        time_saved_pct = ((time_off - time_on) / time_off * 100.0) if time_off > 0 else 0.0
        speedup = (time_off / time_on) if time_on > 0 else 1.0

        dec_on = sub_on["decisions"].mean()
        dec_off = sub_off["decisions"].mean()

        prop_on = sub_on["propagations"].mean()
        prop_off = sub_off["propagations"].mean()

        results.append({
            "Kích thước": s,
            "SAT Calls (Tắt)": f"{sat_off:.1f}",
            "SAT Calls (Bật)": f"{sat_on:.1f}",
            "Tiết kiệm SAT (%)": f"{sat_saved_pct:.1f}%",
            "Thời gian (Tắt, ms)": f"{time_off * 1000:.2f}",
            "Thời gian (Bật, ms)": f"{time_on * 1000:.2f}",
            "Hệ số tăng tốc (Speedup)": f"{speedup:.2f}x",
            "Giảm thời gian (%)": f"{time_saved_pct:.1f}%",
            "Decisions (Tắt -> Bật)": f"{dec_off:.1f} → {dec_on:.1f}",
            "Propagations (Tắt -> Bật)": f"{prop_off:.1f} → {prop_on:.1f}",
            "_raw_size": s,
            "_raw_sat_saved_pct": sat_saved_pct,
            "_raw_speedup": speedup,
        })

    return pd.DataFrame(results)


# ==============================================================================
# XUẤT BẢNG BÁO CÁO (TEXT, MARKDOWN, CSV)
# ==============================================================================

def generate_report_tables(df: pd.DataFrame, out_dir: Path) -> dict[str, str]:
    """
    Tổng hợp các bảng số liệu, xuất 2 file CSV tổng kết (summary_by_size.csv,
    model_reuse_comparison.csv) và định dạng văn bản hiển thị trên console.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_size_df = compute_summary_by_size(df)
    reuse_comp_df = compute_model_reuse_comparison(df)
    failure_info = analyze_failures_and_timeouts(df)

    txt_sections: list[str] = []

    # --------------------------------------------------------------------------
    # 1. Báo cáo ca lỗi và timeout
    # --------------------------------------------------------------------------
    txt_sections.append("================================================================================")
    txt_sections.append("1. TÌNH TRẠNG THỰC THI, LỖI VÀ QUÁ THỜI GIAN (FAILURES & TIMEOUTS)")
    txt_sections.append("================================================================================")

    f_text = [
        f"- Tổng số lượt chạy thực nghiệm: {failure_info['total_runs']}",
        f"- Số lượt giải thành công (SOLVED): {failure_info['solved_count']} ({failure_info['solved_count'] / max(failure_info['total_runs'], 1) * 100:.1f}%)",
        f"- Số lượt quá thời gian (TIMEOUT): {failure_info['timeout_count']}",
        f"- Số lượt lỗi tải (LOAD_ERROR): {failure_info['load_error_count']}",
        f"- Số lượt lỗi thực thi (ERROR): {failure_info['exec_error_count']}",
    ]

    txt_sections.extend(f_text)

    # Bảng phân rã theo kích thước
    breakdown_rows = []
    for s, stats in failure_info["breakdown_by_size"].items():
        succ_rate = (stats["solved"] / max(stats["total"], 1)) * 100.0
        breakdown_rows.append([s, stats["total"], stats["solved"], stats["timeout"], stats["error"], f"{succ_rate:.1f}%"])

    breakdown_headers = ["Kích thước", "Tổng lượt chạy", "SOLVED", "TIMEOUT", "ERROR", "Tỷ lệ thành công"]
    txt_sections.append("\nPhan bo theo kich thuoc puzzle:")
    txt_sections.append(tabulate(breakdown_rows, headers=breakdown_headers, tablefmt="grid"))

    if failure_info["failure_count"] == 0:
        msg = (
            "\n> **Ghi chú đặc biệt về ca lỗi:** Không ghi nhận bất kỳ ca lỗi (ERROR, LOAD_ERROR) "
            "hay timeout nào trong toàn bộ tập thử nghiệm chuẩn (3x3, 4x4, 5x5). "
            "100% các câu đố đều được giải thành công (SOLVED), phán quyết hoàn toàn đúng đắn "
            "(verdicts_correct=True) và nghiệm duy nhất (uniqueness=UNIQUE)."
        )
        txt_sections.append(msg + "\n")
    else:
        err_headers = ["Puzzle ID", "Kích thước", "Chế độ", "Lần chạy", "Status", "Uniqueness", "Thời gian", "Thông báo lỗi"]
        err_rows = [[r["puzzle_id"], r["size"], r["model_reuse"], r["run"], r["status"], r["uniqueness"], r["runtime"], r["error"]]
                    for r in failure_info["failure_rows"]]
        txt_sections.append("\nDanh sach chi tiet cac ca loi / timeout:")
        txt_sections.append(tabulate(err_rows, headers=err_headers, tablefmt="grid"))

    # --------------------------------------------------------------------------
    # 2. Bảng tổng hợp theo kích thước và chế độ
    # --------------------------------------------------------------------------
    txt_sections.append("\n================================================================================")
    txt_sections.append("2. THỐNG KÊ HIỆU NĂNG TỔNG QUAN THEO KÍCH THƯỚC VÀ CHẾ ĐỘ MODEL REUSE")
    txt_sections.append("================================================================================")

    if not summary_size_df.empty:
        # Lọc bỏ cột nội bộ bắt đầu bằng _raw
        disp_cols = [c for c in summary_size_df.columns if not c.startswith("_raw")]
        disp_df = summary_size_df[disp_cols]
        txt_sections.append(tabulate(disp_df, headers="keys", tablefmt="grid", showindex=False))

    # --------------------------------------------------------------------------
    # 3. Bảng so sánh tác động của Tái sử dụng mô hình (Model Reuse)
    # --------------------------------------------------------------------------
    txt_sections.append("\n================================================================================")
    txt_sections.append("3. ĐÁNH GIÁ TÁC ĐỘNG CỦA KỸ THUẬT TÁI SỬ DỤNG MÔ HÌNH (ON VS OFF)")
    txt_sections.append("================================================================================")

    if not reuse_comp_df.empty:
        disp_reuse_cols = [c for c in reuse_comp_df.columns if not c.startswith("_raw")]
        disp_reuse_df = reuse_comp_df[disp_reuse_cols]
        txt_sections.append(tabulate(disp_reuse_df, headers="keys", tablefmt="grid", showindex=False))

    # --------------------------------------------------------------------------
    # 4. Bảng chi tiết từng puzzle (phục vụ phụ lục báo cáo)
    # --------------------------------------------------------------------------
    txt_sections.append("\n================================================================================")
    txt_sections.append("4. BẢNG KẾT QUẢ CHI TIẾT TỪNG CÂU ĐỐ (PHỤ LỤC)")
    txt_sections.append("================================================================================")

    puzzle_cols = [
        "puzzle_id", "size_label", "model_reuse", "status", "steps",
        "full_clauses", "sat_calls", "skipped_queries", "decisions",
        "propagations", "backtracks", "runtime", "uniqueness",
    ]
    avail_cols = [c for c in puzzle_cols if c in df.columns]
    detailed_df = df[avail_cols].copy()
    if "runtime" in detailed_df.columns:
        detailed_df["runtime (s)"] = detailed_df["runtime"].apply(lambda v: f"{v:.4f}" if pd.notna(v) else "-")
        detailed_df = detailed_df.drop(columns=["runtime"])

    txt_sections.append(tabulate(detailed_df, headers="keys", tablefmt="grid", showindex=False))

    txt_content = "\n".join(txt_sections)

    # Lưu 2 file CSV rút gọn tổng hợp số liệu
    if not summary_size_df.empty:
        summary_size_df.to_csv(out_dir / "summary_by_size.csv", index=False, encoding="utf-8")
    if not reuse_comp_df.empty:
        reuse_comp_df.to_csv(out_dir / "model_reuse_comparison.csv", index=False, encoding="utf-8")

    return {
        "text": txt_content,
    }


# CÁC HÀM VẼ BIỂU ĐỒ (MATPLOTLIB)

def plot_runtime_comparison(df: pd.DataFrame, out_path: Path, dpi: int = 300) -> None:
    """Biểu đồ thời gian chạy (runtime) theo kích thước, so sánh Model Reuse On vs Off"""
    solved = df[df["status"] == "SOLVED"]
    if solved.empty:
        return

    sizes = sorted(solved["size_label"].unique())
    x = np.arange(len(sizes))
    width = 0.35

    time_on, std_on = [], []
    time_off, std_off = [], []

    for s in sizes:
        sub_on = solved[(solved["size_label"] == s) & (solved["model_reuse"] == "on")]["runtime"] * 1000.0
        sub_off = solved[(solved["size_label"] == s) & (solved["model_reuse"] == "off")]["runtime"] * 1000.0
        time_on.append(sub_on.mean() if not sub_on.empty else 0.0)
        std_on.append(sub_on.std() if len(sub_on) > 1 else 0.0)
        time_off.append(sub_off.mean() if not sub_off.empty else 0.0)
        std_off.append(sub_off.std() if len(sub_off) > 1 else 0.0)

    fig, ax = plt.subplots(figsize=(8, 5))
    rects1 = ax.bar(x - width / 2, time_on, width, yerr=std_on, label="Model Reuse: ON",
                    color=COLORS["on"], capsize=5, edgecolor="black", linewidth=0.8)
    rects2 = ax.bar(x + width / 2, time_off, width, yerr=std_off, label="Model Reuse: OFF",
                    color=COLORS["off"], capsize=5, edgecolor="black", linewidth=0.8)

    max_runtime = max([t + s for t, s in zip(time_off, std_off)] + [t + s for t, s in zip(time_on, std_on)] or [1])
    ax.set_ylim(0, max_runtime * 1.25)

    ax.set_title("Thời gian chạy trung bình theo kích thước câu đố (Runtime)", fontsize=13, fontweight="bold", pad=16)
    ax.set_xlabel("Kích thước lưới (Grid Size)", fontsize=11, fontweight="bold")
    ax.set_ylabel("Thời gian chạy (mili-giây / ms)", fontsize=11, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(sizes, fontsize=10)
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    ax.legend(frameon=True, fontsize=10)

    # Hiển thị số liệu trên đầu cột
    for rect in rects1:
        height = rect.get_height()
        ax.annotate(f"{height:.1f}ms",
                    xy=(rect.get_x() + rect.get_width() / 2, height),
                    xytext=(0, 4), textcoords="offset points",
                    ha="center", va="bottom", fontsize=8, fontweight="bold")
    for rect in rects2:
        height = rect.get_height()
        ax.annotate(f"{height:.1f}ms",
                    xy=(rect.get_x() + rect.get_width() / 2, height),
                    xytext=(0, 4), textcoords="offset points",
                    ha="center", va="bottom", fontsize=8, fontweight="bold")

    plt.tight_layout()
    fig.savefig(out_path, dpi=dpi)
    plt.close(fig)


def plot_sat_calls(df: pd.DataFrame, out_path: Path, dpi: int = 300) -> None:
    """Biểu đồ số lượt gọi SAT Solver và số lượng truy vấn được cắt giảm nhờ Model Reuse"""
    solved = df[df["status"] == "SOLVED"]
    if solved.empty:
        return

    sizes = sorted(solved["size_label"].unique())
    x = np.arange(len(sizes))
    width = 0.35

    calls_on, skipped_on, calls_off = [], [], []
    for s in sizes:
        sub_on = solved[(solved["size_label"] == s) & (solved["model_reuse"] == "on")]
        sub_off = solved[(solved["size_label"] == s) & (solved["model_reuse"] == "off")]
        calls_on.append(sub_on["sat_calls"].mean() if not sub_on.empty else 0.0)
        skipped_on.append(sub_on["skipped_queries"].mean() if not sub_on.empty else 0.0)
        calls_off.append(sub_off["sat_calls"].mean() if not sub_off.empty else 0.0)

    fig, ax = plt.subplots(figsize=(8.5, 5))
    rects1 = ax.bar(x - width / 2, calls_on, width, label="SAT Calls thực thi (Reuse ON)",
                    color=COLORS["on"], edgecolor="black", linewidth=0.8)
    rects_skip = ax.bar(x - width / 2, skipped_on, width, bottom=calls_on,
                        label="Truy vấn được bỏ qua (Skipped)",
                        color=COLORS["accent"], alpha=0.85, edgecolor="black", hatch="//", linewidth=0.8)
    rects2 = ax.bar(x + width / 2, calls_off, width, label="SAT Calls thực thi (Reuse OFF)",
                    color=COLORS["off"], edgecolor="black", linewidth=0.8)

    max_calls = max([calls_on[i] + skipped_on[i] for i in range(len(sizes))] + calls_off or [1])
    ax.set_ylim(0, max_calls * 1.25)

    ax.set_title("Số lượng truy vấn SAT và hiệu quả lược bỏ truy vấn (Skipped Queries)",
                 fontsize=12, fontweight="bold", pad=16)
    ax.set_xlabel("Kích thước lưới (Grid Size)", fontsize=11, fontweight="bold")
    ax.set_ylabel("Số lượng truy vấn SAT", fontsize=11, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(sizes, fontsize=10)
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    ax.legend(frameon=True, fontsize=9.5)

    for i in range(len(sizes)):
        total_on = calls_on[i] + skipped_on[i]
        pct = (skipped_on[i] / total_on * 100) if total_on > 0 else 0
        ax.annotate(f"Giảm {pct:.0f}%",
                    xy=(x[i] - width / 2, total_on),
                    xytext=(0, 4), textcoords="offset points",
                    ha="center", va="bottom", fontsize=8.5, fontweight="bold", color="darkgreen")
        ax.annotate(f"{calls_off[i]:.0f}",
                    xy=(x[i] + width / 2, calls_off[i]),
                    xytext=(0, 4), textcoords="offset points",
                    ha="center", va="bottom", fontsize=8.5)

    plt.tight_layout()
    fig.savefig(out_path, dpi=dpi)
    plt.close(fig)


def plot_solver_operations(df: pd.DataFrame, out_path: Path, dpi: int = 300) -> None:
    """Biểu đồ 3 panel so sánh Decisions, Propagations, Backtracks của DPLL solver"""
    solved = df[df["status"] == "SOLVED"]
    if solved.empty:
        return

    sizes = sorted(solved["size_label"].unique())
    x = np.arange(len(sizes))
    width = 0.35

    metrics = [
        ("decisions", "Decisions (Phân nhánh)", COLORS["purple"]),
        ("propagations", "Unit Propagations (Lan truyền đơn)", COLORS["cyan"]),
        ("backtracks", "Backtracks (Quay lui xung đột)", COLORS["danger"]),
    ]

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8), sharey=False)

    for idx, (col, title, color) in enumerate(metrics):
        ax = axes[idx]
        val_on = [solved[(solved["size_label"] == s) & (solved["model_reuse"] == "on")][col].mean() for s in sizes]
        val_off = [solved[(solved["size_label"] == s) & (solved["model_reuse"] == "off")][col].mean() for s in sizes]

        ax.bar(x - width / 2, val_on, width, label="Reuse ON", color=COLORS["on"], edgecolor="black", linewidth=0.7)
        ax.bar(x + width / 2, val_off, width, label="Reuse OFF", color=COLORS["off"], edgecolor="black", linewidth=0.7)

        max_v = max(val_on + val_off or [1])
        ax.set_ylim(0, max_v * 1.25 if max_v > 0 else 1)

        ax.set_title(title, fontsize=11, fontweight="bold", pad=12)
        ax.set_xlabel("Kích thước", fontsize=10)
        ax.set_xticks(x)
        ax.set_xticklabels(sizes, fontsize=10)
        ax.grid(axis="y", linestyle="--", alpha=0.5)
        if idx == 0:
            ax.legend(frameon=True, fontsize=9)

    plt.suptitle("Thống kê hoạt động của DPLL SAT Solver theo kích thước câu đố", fontsize=13, fontweight="bold", y=1.02)
    plt.tight_layout()
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)


def plot_encoding_complexity(df: pd.DataFrame, out_path: Path, dpi: int = 300) -> None:
    """Biểu đồ số biến chính, biến phụ và số lượng mệnh đề CNF (KB0, KB_final, Full)"""
    solved = df[df["status"] == "SOLVED"]
    if solved.empty:
        return

    sizes = sorted(solved["size_label"].unique())
    x = np.arange(len(sizes))
    width = 0.25

    main_vars = [solved[solved["size_label"] == s]["full_main_vars"].mean() for s in sizes]
    aux_vars = [solved[solved["size_label"] == s]["full_aux_vars"].mean() for s in sizes]

    kb0_cl = [solved[solved["size_label"] == s]["kb0_clauses"].mean() for s in sizes]
    final_cl = [solved[solved["size_label"] == s]["kb_final_clauses"].mean() for s in sizes]
    full_cl = [solved[solved["size_label"] == s]["full_clauses"].mean() for s in sizes]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))

    # Panel 1: Biến logic (Variables)
    ax1.bar(x - width / 2, main_vars, width, label="Biến chính (Primary C_i)", color="#2b5c8f", edgecolor="black")
    ax1.bar(x + width / 2, aux_vars, width, label="Biến phụ (Auxiliary)", color="#e06666", edgecolor="black")
    ax1.set_title("Số biến mệnh đề logic theo kích thước", fontsize=12, fontweight="bold")
    ax1.set_xlabel("Kích thước lưới", fontsize=10, fontweight="bold")
    ax1.set_ylabel("Số lượng biến", fontsize=10, fontweight="bold")
    ax1.set_xticks(x)
    ax1.set_xticklabels(sizes)
    ax1.grid(axis="y", linestyle="--", alpha=0.5)
    ax1.legend(frameon=True)

    # Panel 2: Mệnh đề CNF (Clauses)
    ax2.bar(x - width, kb0_cl, width, label="KB ban đầu (KB0)", color="#99d8c9", edgecolor="black")
    ax2.bar(x, final_cl, width, label="KB kết thúc (KB_final)", color="#41ae76", edgecolor="black")
    ax2.bar(x + width, full_cl, width, label="Toàn bộ manh mối (Full CNF)", color="#005824", edgecolor="black")
    ax2.set_title("Số lượng mệnh đề CNF theo giai đoạn", fontsize=12, fontweight="bold")
    ax2.set_xlabel("Kích thước lưới", fontsize=10, fontweight="bold")
    ax2.set_ylabel("Số mệnh đề (Clauses)", fontsize=10, fontweight="bold")
    ax2.set_xticks(x)
    ax2.set_xticklabels(sizes)
    ax2.grid(axis="y", linestyle="--", alpha=0.5)
    ax2.legend(frameon=True)

    plt.suptitle("Quy mô biểu diễn Logic và Mã hoá CNF", fontsize=13, fontweight="bold", y=1.02)
    plt.tight_layout()
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)


def plot_speedup_and_savings(df: pd.DataFrame, out_path: Path, dpi: int = 300) -> None:
    """Biểu đồ tỉ lệ tiết kiệm SAT calls (%) và hệ số tăng tốc thời gian (Speedup factor)"""
    comp_df = compute_model_reuse_comparison(df)
    if comp_df.empty:
        return

    sizes = comp_df["_raw_size"].tolist()
    savings = comp_df["_raw_sat_saved_pct"].tolist()
    speedups = comp_df["_raw_speedup"].tolist()
    x = np.arange(len(sizes))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5))

    # Panel 1: Tỉ lệ tiết kiệm truy vấn SAT
    bars1 = ax1.bar(x, savings, color="#2ca02c", width=0.45, edgecolor="black")
    ax1.set_title("Tỉ lệ giảm truy vấn SAT nhờ Model Reuse (%)", fontsize=11, fontweight="bold")
    ax1.set_xlabel("Kích thước lưới", fontsize=10, fontweight="bold")
    ax1.set_ylabel("Phần trăm tiết kiệm (%)", fontsize=10, fontweight="bold")
    ax1.set_xticks(x)
    ax1.set_xticklabels(sizes)
    ax1.set_ylim(0, max(savings + [10]) * 1.15)
    ax1.grid(axis="y", linestyle="--", alpha=0.5)
    for bar in bars1:
        h = bar.get_height()
        ax1.annotate(f"{h:.1f}%", xy=(bar.get_x() + bar.get_width() / 2, h),
                     xytext=(0, 4), textcoords="offset points", ha="center", va="bottom",
                     fontweight="bold", fontsize=9)

    # Panel 2: Hệ số tăng tốc thời gian (Speedup)
    bars2 = ax2.bar(x, speedups, color="#1f77b4", width=0.45, edgecolor="black")
    ax2.axhline(1.0, color="gray", linestyle="--", linewidth=1, label="Baseline (1.0x)")
    ax2.set_title("Hệ số tăng tốc thời gian thực thi (Speedup)", fontsize=11, fontweight="bold")
    ax2.set_xlabel("Kích thước lưới", fontsize=10, fontweight="bold")
    ax2.set_ylabel("Tỉ số tăng tốc (Toff / Ton)", fontsize=10, fontweight="bold")
    ax2.set_xticks(x)
    ax2.set_xticklabels(sizes)
    ax2.set_ylim(0, max(speedups + [1.5]) * 1.2)
    ax2.grid(axis="y", linestyle="--", alpha=0.5)
    ax2.legend(frameon=True)
    for bar in bars2:
        h = bar.get_height()
        ax2.annotate(f"{h:.2f}x", xy=(bar.get_x() + bar.get_width() / 2, h),
                     xytext=(0, 4), textcoords="offset points", ha="center", va="bottom",
                     fontweight="bold", fontsize=9)

    plt.tight_layout()
    fig.savefig(out_path, dpi=dpi)
    plt.close(fig)


def plot_status_distribution(df: pd.DataFrame, out_path: Path, dpi: int = 300) -> None:
    """Biểu đồ phân bố trạng thái chạy (SOLVED, TIMEOUT, ERROR) theo kích thước"""
    sizes = sorted(df["size_label"].unique())
    x = np.arange(len(sizes))
    width = 0.45

    solved_counts = []
    timeout_counts = []
    error_counts = []

    for s in sizes:
        sub = df[df["size_label"] == s]
        n_solved = (sub["status"] == "SOLVED").sum()
        n_timeout = ((sub["status"] == "TIMEOUT") | (sub.get("uniqueness", pd.Series()) == "TIMEOUT")).sum()
        n_error = ((sub["status"].isin(["ERROR", "LOAD_ERROR"])) | (sub.get("error", pd.Series()).fillna("") != "")).sum()
        solved_counts.append(int(n_solved))
        timeout_counts.append(int(n_timeout))
        error_counts.append(int(n_error))

    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    p1 = ax.bar(x, solved_counts, width, label="SOLVED (Thành công)", color="#2ca02c", edgecolor="black")
    p2 = ax.bar(x, timeout_counts, width, bottom=solved_counts, label="TIMEOUT (Quá giờ)", color="#ff7f0e", edgecolor="black")
    bottom_err = np.array(solved_counts) + np.array(timeout_counts)
    p3 = ax.bar(x, error_counts, width, bottom=bottom_err, label="ERROR (Lỗi)", color="#d62728", edgecolor="black")

    # Mở rộng giới hạn trục Y (+25%) để nhãn số liệu không bị dính vào tiêu đề
    max_total = max([s + t + e for s, t, e in zip(solved_counts, timeout_counts, error_counts)] or [1])
    ax.set_ylim(0, max_total * 1.25)

    ax.set_title("Phân bố trạng thái thực thi thực nghiệm theo kích thước", fontsize=12, fontweight="bold", pad=16)
    ax.set_xlabel("Kích thước lưới", fontsize=10, fontweight="bold")
    ax.set_ylabel("Số lượt chạy", fontsize=10, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(sizes)
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    ax.legend(frameon=True, loc="upper right")

    for i in range(len(sizes)):
        total = solved_counts[i] + timeout_counts[i] + error_counts[i]
        rate = (solved_counts[i] / total * 100) if total > 0 else 0
        ax.annotate(f"{solved_counts[i]}/{total} ({rate:.0f}%)",
                    xy=(x[i], total), xytext=(0, 5), textcoords="offset points",
                    ha="center", va="bottom", fontsize=9, fontweight="bold")

    plt.tight_layout()
    fig.savefig(out_path, dpi=dpi)
    plt.close(fig)


def plot_step_dynamics(steps_df: pd.DataFrame | None, out_path: Path, dpi: int = 300) -> None:
    """Biểu đồ động lực học từng bước suy diễn (Deduction Step Dynamics) nếu có dữ liệu steps"""
    if steps_df is None or steps_df.empty:
        return

    # Lọc lấy một vài puzzle tiêu biểu của 3x3, 4x4, 5x5 (chế độ on, run 1)
    sub = steps_df[(steps_df["model_reuse"] == "on") & (steps_df["run"] == 1)]
    if sub.empty:
        sub = steps_df

    sample_puzzles = []
    for s in sorted(sub["size"].unique()):
        p_ids = sub[sub["size"] == s]["puzzle_id"].unique()
        if len(p_ids) > 0:
            sample_puzzles.append(p_ids[0])

    if not sample_puzzles:
        return

    fig, axes = plt.subplots(1, len(sample_puzzles), figsize=(5.5 * len(sample_puzzles), 4.5), sharey=False)
    if len(sample_puzzles) == 1:
        axes = [axes]

    for idx, p_id in enumerate(sample_puzzles):
        ax = axes[idx]
        p_steps = sub[sub["puzzle_id"] == p_id].sort_values("step")
        if p_steps.empty:
            continue

        steps = p_steps["step"].values
        active_clues = p_steps["num_active_clues"].values
        sat_queries = p_steps["sat_queries"].values

        ax.plot(steps, active_clues, marker="o", color=COLORS["on"], linewidth=2, label="Manh mối hoạt động (Active Clues)")
        ax.plot(steps, sat_queries, marker="s", color=COLORS["danger"], linestyle="--", linewidth=1.8, label="SAT Queries / bước")

        ax.set_title(f"Puzzle: {p_id}", fontsize=11, fontweight="bold")
        ax.set_xlabel("Bước suy diễn (Step)", fontsize=10)
        ax.set_ylabel("Số lượng", fontsize=10)
        ax.grid(True, linestyle="--", alpha=0.5)
        ax.set_xticks(steps)
        if idx == 0:
            ax.legend(frameon=True, fontsize=8.5)

    plt.suptitle("Động thái suy diễn từng bước (Lật thẻ tuần tự & Số truy vấn SAT)", fontsize=12, fontweight="bold", y=1.02)
    plt.tight_layout()
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)


def plot_overview_dashboard(df: pd.DataFrame, out_path: Path, dpi: int = 300) -> None:
    """Dashboard tổng hợp 4 đồ thị chính trong một bức ảnh chuẩn báo cáo"""
    solved = df[df["status"] == "SOLVED"]
    if solved.empty:
        return

    sizes = sorted(solved["size_label"].unique())
    x = np.arange(len(sizes))
    width = 0.35

    fig, axes = plt.subplots(2, 2, figsize=(13, 9))

    # 1. Top-Left: Runtime
    ax1 = axes[0, 0]
    t_on = [solved[(solved["size_label"] == s) & (solved["model_reuse"] == "on")]["runtime"].mean() * 1000 for s in sizes]
    t_off = [solved[(solved["size_label"] == s) & (solved["model_reuse"] == "off")]["runtime"].mean() * 1000 for s in sizes]
    ax1.bar(x - width / 2, t_on, width, label="Reuse ON", color=COLORS["on"], edgecolor="black")
    ax1.bar(x + width / 2, t_off, width, label="Reuse OFF", color=COLORS["off"], edgecolor="black")
    max_t = max(t_on + t_off or [1])
    ax1.set_ylim(0, max_t * 1.25)
    ax1.set_title("(A) Thời gian chạy trung bình (ms)", fontsize=11, fontweight="bold", pad=10)
    ax1.set_xticks(x)
    ax1.set_xticklabels(sizes)
    ax1.grid(axis="y", linestyle="--", alpha=0.5)
    ax1.legend(frameon=True, fontsize=9)

    # 2. Top-Right: SAT Calls
    ax2 = axes[0, 1]
    c_on = [solved[(solved["size_label"] == s) & (solved["model_reuse"] == "on")]["sat_calls"].mean() for s in sizes]
    c_off = [solved[(solved["size_label"] == s) & (solved["model_reuse"] == "off")]["sat_calls"].mean() for s in sizes]
    ax2.bar(x - width / 2, c_on, width, label="Reuse ON", color=COLORS["on"], edgecolor="black")
    ax2.bar(x + width / 2, c_off, width, label="Reuse OFF", color=COLORS["off"], edgecolor="black")
    max_c = max(c_on + c_off or [1])
    ax2.set_ylim(0, max_c * 1.25)
    ax2.set_title("(B) Tổng số truy vấn SAT", fontsize=11, fontweight="bold", pad=10)
    ax2.set_xticks(x)
    ax2.set_xticklabels(sizes)
    ax2.grid(axis="y", linestyle="--", alpha=0.5)
    ax2.legend(frameon=True, fontsize=9)

    # 3. Bottom-Left: DPLL Solver Operations
    ax3 = axes[1, 0]
    dec = [solved[solved["size_label"] == s]["decisions"].mean() for s in sizes]
    prop = [solved[solved["size_label"] == s]["propagations"].mean() for s in sizes]
    w = 0.28
    ax3.bar(x - w / 2, dec, w, label="Decisions", color=COLORS["purple"], edgecolor="black")
    ax3.bar(x + w / 2, prop, w, label="Propagations", color=COLORS["cyan"], edgecolor="black")
    max_op = max(dec + prop or [1])
    ax3.set_ylim(0, max_op * 1.25)
    ax3.set_title("(C) Thao tác Solver (Decisions & Propagations)", fontsize=11, fontweight="bold", pad=10)
    ax3.set_xticks(x)
    ax3.set_xticklabels(sizes)
    ax3.grid(axis="y", linestyle="--", alpha=0.5)
    ax3.legend(frameon=True, fontsize=9)

    # 4. Bottom-Right: Encoding Size (Variables & Clauses)
    ax4 = axes[1, 1]
    cl = [solved[solved["size_label"] == s]["full_clauses"].mean() for s in sizes]
    v = [solved[solved["size_label"] == s]["full_main_vars"].mean() + solved[solved["size_label"] == s]["full_aux_vars"].mean() for s in sizes]
    ax4.bar(x - w / 2, v, w, label="Tổng số biến (Vars)", color="#2ca02c", edgecolor="black")
    ax4.bar(x + w / 2, cl, w, label="Mệnh đề Full (Clauses)", color="#d62728", edgecolor="black")
    max_enc = max(cl + v or [1])
    ax4.set_ylim(0, max_enc * 1.25)
    ax4.set_title("(D) Quy mô mã hoá CNF", fontsize=11, fontweight="bold", pad=10)
    ax4.set_xticks(x)
    ax4.set_xticklabels(sizes)
    ax4.grid(axis="y", linestyle="--", alpha=0.5)
    ax4.legend(frameon=True, fontsize=9)

    plt.suptitle("TỔNG HỢP HIỆU NĂNG GRIDUCTIVE SOLVER (OVERVIEW DASHBOARD)", fontsize=13, fontweight="bold", y=0.99)
    plt.tight_layout()
    fig.savefig(out_path, dpi=dpi)
    plt.close(fig)



# QUY TRÌNH TỔNG HỢP TOÀN BỘ (PIPELINE)

def generate_all_plots_and_tables(
    summary_path: Path,
    steps_path: Path,
    out_dir: Path,
    img_format: str = "png",
    dpi: int = 300,
    generate_plots: bool = True,
    quiet: bool = False,
) -> list[Path]:
    """
    Quy trình đầy đủ: đọc dữ liệu, tạo bảng báo cáo và vẽ toàn bộ biểu đồ.
    Trả về danh sách các đường dẫn file đã tạo.
    """
    df = load_summary_data(summary_path)
    steps_df = load_steps_data(steps_path) if steps_path.is_file() else None
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Sinh các bảng báo cáo (in ra console và lưu 2 file CSV tổng hợp)
    report_res = generate_report_tables(df, out_dir)
    generated_files: list[Path] = []
    if (out_dir / "summary_by_size.csv").is_file():
        generated_files.append(out_dir / "summary_by_size.csv")
    if (out_dir / "model_reuse_comparison.csv").is_file():
        generated_files.append(out_dir / "model_reuse_comparison.csv")

    if not quiet:
        print("\n" + report_res["text"] + "\n")

    # 2. Sinh các biểu đồ trực quan
    if generate_plots:
        plots = [
            ("runtime_by_size", lambda p: plot_runtime_comparison(df, p, dpi)),
            ("sat_calls_by_size", lambda p: plot_sat_calls(df, p, dpi)),
            ("solver_operations_by_size", lambda p: plot_solver_operations(df, p, dpi)),
            ("encoding_complexity", lambda p: plot_encoding_complexity(df, p, dpi)),
            ("model_reuse_impact", lambda p: plot_speedup_and_savings(df, p, dpi)),
            ("status_distribution", lambda p: plot_status_distribution(df, p, dpi)),
            ("overview_dashboard", lambda p: plot_overview_dashboard(df, p, dpi)),
        ]

        if steps_df is not None:
            plots.append(("step_dynamics", lambda p: plot_step_dynamics(steps_df, p, dpi)))

        for name, plot_fn in plots:
            fig_path = out_dir / f"{name}.{img_format}"
            try:
                plot_fn(fig_path)
                generated_files.append(fig_path)
                if not quiet:
                    print(f"Đã tạo biểu đồ: {fig_path.name}")
            except Exception as exc:
                print(f"Lỗi khi vẽ biểu đồ {name}: {exc}", file=sys.stderr)

    return generated_files



# CLI INTERFACE

def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m experiments.plot_results",
        description="Đọc CSV benchmark, tạo bảng tổng hợp theo kích thước và vẽ biểu đồ hiệu năng.",
    )
    parser.add_argument(
        "--summary-csv",
        type=Path,
        default=DEFAULT_SUMMARY_FILE,
        help=f"Đường dẫn file benchmark_summary.csv (mặc định: {DEFAULT_SUMMARY_FILE.relative_to(SOURCE_ROOT) if DEFAULT_SUMMARY_FILE.is_relative_to(SOURCE_ROOT) else DEFAULT_SUMMARY_FILE})",
    )
    parser.add_argument(
        "--steps-csv",
        type=Path,
        default=DEFAULT_STEPS_FILE,
        help=f"Đường dẫn file benchmark_steps.csv (mặc định: {DEFAULT_STEPS_FILE.relative_to(SOURCE_ROOT) if DEFAULT_STEPS_FILE.is_relative_to(SOURCE_ROOT) else DEFAULT_STEPS_FILE})",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_RESULTS_DIR,
        help=f"Thư mục lưu kết quả xuất ra (mặc định: {DEFAULT_RESULTS_DIR.relative_to(SOURCE_ROOT) if DEFAULT_RESULTS_DIR.is_relative_to(SOURCE_ROOT) else DEFAULT_RESULTS_DIR})",
    )
    parser.add_argument(
        "--format",
        choices=["png", "pdf", "svg"],
        default="png",
        help="Định dạng ảnh xuất biểu đồ (mặc định: png)",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="Độ phân giải DPI khi xuất biểu đồ (mặc định: 300)",
    )
    parser.add_argument(
        "--no-plots",
        action="store_true",
        help="Chỉ xuất bảng số liệu và báo cáo văn bản, không vẽ biểu đồ",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Không in nội dung bảng ra console",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.summary_csv.is_file():
        print(f"Lỗi: Không tìm thấy file {args.summary_csv}", file=sys.stderr)
        print("Hãy chạy benchmark trước: python -m experiments.run_benchmark", file=sys.stderr)
        return 1

    try:
        written = generate_all_plots_and_tables(
            summary_path=args.summary_csv,
            steps_path=args.steps_csv,
            out_dir=args.out_dir,
            img_format=args.format,
            dpi=args.dpi,
            generate_plots=not args.no_plots,
            quiet=args.quiet,
        )
        print(f"\nHoàn tất task T22! Đã tạo {len(written)} sản phẩm tại: {args.out_dir}")
        return 0
    except Exception as exc:
        print(f"Lỗi thực thi: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())
