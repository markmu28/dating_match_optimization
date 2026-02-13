#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成正常/极端测试用例并批量执行CLI鲁棒性验证。
输出：
- edge_case_tests/generated_robustness/robustness_report.json
- edge_case_tests/generated_robustness/robustness_report.md
"""

from __future__ import annotations

import json
import random
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "cli.py"
BASE_ROSTER_FILE = ROOT / "嘉宾名单.xlsx"
BASE_ROSTER_SHEET = "嘉宾名单"
OUT_ROOT = ROOT / "edge_case_tests" / "generated_robustness"
CASES_DIR = OUT_ROOT / "cases"
RESULTS_DIR = OUT_ROOT / "results"
PYTHON = "python3"


def guest_id(guest_type: str, number: int) -> str:
    return f"{'M' if str(guest_type).strip() == '男' else 'F'}{int(number)}"


def split_aliases(alias_raw: object) -> List[str]:
    if alias_raw is None:
        return []
    alias_text = str(alias_raw).strip()
    if not alias_text or alias_text.lower() == "nan":
        return []
    normalized = alias_text.replace("，", ",").replace("、", ",").replace("|", ",").replace(";", ",")
    return [a.strip() for a in normalized.split(",") if a.strip()]


def ensure_roster_columns(df: pd.DataFrame) -> pd.DataFrame:
    roster = df.copy()
    for col, default in [
        ("嘉宾类型", ""),
        ("编号", ""),
        ("姓名", ""),
        ("是否到场", "是"),
        ("是否VIP", "否"),
        ("英文名", ""),
        ("别名", ""),
    ]:
        if col not in roster.columns:
            roster[col] = default
    # 统一顺序
    ordered = ["嘉宾类型", "编号", "姓名", "是否到场", "是否VIP", "英文名", "别名"]
    for c in roster.columns:
        if c not in ordered:
            ordered.append(c)
    return roster[ordered]


def load_base_roster() -> pd.DataFrame:
    roster = pd.read_excel(BASE_ROSTER_FILE, sheet_name=BASE_ROSTER_SHEET)
    return ensure_roster_columns(roster)


def set_attendance_and_vip(
    roster: pd.DataFrame,
    absent_ids: Optional[List[str]] = None,
    vip_ids: Optional[List[str]] = None,
) -> pd.DataFrame:
    absent_ids = set(absent_ids or [])
    vip_ids = set(vip_ids or [])
    out = roster.copy()
    out["是否到场"] = "是"
    out["是否VIP"] = "否"
    for idx, row in out.iterrows():
        gid = guest_id(row["嘉宾类型"], row["编号"])
        if gid in absent_ids:
            out.at[idx, "是否到场"] = "否"
        if gid in vip_ids:
            out.at[idx, "是否VIP"] = "是"
    return out


def choose_subject_token(row: pd.Series, mode: str, rng: random.Random) -> object:
    gid = guest_id(row["嘉宾类型"], row["编号"])
    number = int(row["编号"])
    name = str(row.get("姓名", "")).strip()
    english = str(row.get("英文名", "")).strip()
    aliases = split_aliases(row.get("别名", ""))
    if mode == "number":
        return number
    if mode == "id":
        return gid
    if mode == "name":
        return name
    if mode == "english":
        return english if english and english.lower() != "nan" else name
    if mode == "mixed_name":
        choices = [name]
        if english and english.lower() != "nan":
            choices.append(english)
        choices.extend(aliases)
        choices.append(gid)
        return rng.choice([c for c in choices if c])
    return number


def choose_target_token(row: pd.Series, mode: str, rng: random.Random) -> object:
    gid = guest_id(row["嘉宾类型"], row["编号"])
    number = int(row["编号"])
    name = str(row.get("姓名", "")).strip()
    english = str(row.get("英文名", "")).strip()
    aliases = split_aliases(row.get("别名", ""))
    if mode == "id":
        return gid
    if mode == "number":
        return number
    if mode == "name":
        return name
    if mode == "english":
        return english if english and english.lower() != "nan" else name
    if mode == "alias":
        return aliases[0] if aliases else (english if english and english.lower() != "nan" else name)
    if mode == "mixed":
        choices = [gid, number, name]
        if english and english.lower() != "nan":
            choices.append(english)
        choices.extend(aliases)
        return rng.choice([c for c in choices if c != ""])
    return gid


def build_preferences(
    roster: pd.DataFrame,
    rng: random.Random,
    subject_mode: str,
    target_mode: str,
    include_subject_name_col: bool = False,
    force_subject_name_priority: bool = False,
    invalid_target_every: int = 0,
    inject_ambiguous_alias_for_males: bool = False,
    vip_without_preferences: Optional[List[str]] = None,
) -> pd.DataFrame:
    vip_without_preferences = set(vip_without_preferences or [])
    roster_sorted = roster.sort_values(["嘉宾类型", "编号"]).reset_index(drop=True)

    males = roster_sorted[roster_sorted["嘉宾类型"] == "男"]
    females = roster_sorted[roster_sorted["嘉宾类型"] == "女"]

    rows: List[Dict[str, object]] = []
    for i, row in roster_sorted.iterrows():
        subject_gender = str(row["嘉宾类型"]).strip()
        subject_gid = guest_id(subject_gender, row["编号"])
        candidate_pool = females if subject_gender == "男" else males

        picked = candidate_pool.sample(2, random_state=rng.randint(1, 10_000_000)).reset_index(drop=True)
        target_1 = picked.iloc[0]
        target_2 = picked.iloc[1]

        obj1 = choose_target_token(target_1, target_mode, rng)
        obj2 = choose_target_token(target_2, target_mode, rng)

        if invalid_target_every > 0 and i % invalid_target_every == 0:
            obj1 = f"不存在的人{i+1}"

        if inject_ambiguous_alias_for_males and subject_gender == "男" and i % 3 == 0:
            obj1 = "Alex"

        if subject_gid in vip_without_preferences:
            obj1 = ""
            obj2 = ""

        subject_value = choose_subject_token(row, subject_mode, rng)
        if force_subject_name_priority and include_subject_name_col:
            # 编号列给一个可解析但可能非优先值，嘉宾姓名列给主值用于验证优先级
            subject_value = guest_id(subject_gender, row["编号"])

        out_row = {
            "嘉宾类型": subject_gender,
            "编号": subject_value,
            "对象1ID": obj1,
            "对象2ID": obj2,
        }
        if include_subject_name_col:
            out_row["嘉宾姓名"] = choose_subject_token(row, "mixed_name", rng)
        rows.append(out_row)

    rng.shuffle(rows)
    return pd.DataFrame(rows)


def write_roster_xlsx(path: Path, roster: pd.DataFrame) -> None:
    notes = pd.DataFrame(
        [
            {"说明": "鲁棒性测试自动生成名单"},
            {"说明": "可选列: 是否到场, 是否VIP, 英文名, 别名"},
        ]
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        roster.to_excel(writer, sheet_name="嘉宾名单", index=False)
        notes.to_excel(writer, sheet_name="填写说明", index=False)


def write_pref_xlsx(path: Path, pref: pd.DataFrame, note: str) -> None:
    note_df = pd.DataFrame([{"说明": note}])
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pref.to_excel(writer, sheet_name="偏好", index=False)
        note_df.to_excel(writer, sheet_name="说明", index=False)


@dataclass
class CaseResult:
    case_id: str
    category: str
    expected_success: bool
    solved: bool
    pattern_ok: bool
    passed: bool
    duration_sec: float
    command: List[str]
    required_patterns: List[str]
    missing_patterns: List[str]
    output_tail: str


def run_cli(command: List[str], timeout_sec: int = 120) -> Tuple[str, float]:
    start = time.time()
    proc = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=timeout_sec,
    )
    duration = time.time() - start
    out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return out, duration


def evaluate_output(output: str, expected_success: bool, required_patterns: List[str]) -> Tuple[bool, bool, List[str]]:
    solved = "✅ 求解成功" in output
    pattern_missing = [p for p in required_patterns if p not in output]
    pattern_ok = len(pattern_missing) == 0
    passed = (solved == expected_success) and pattern_ok
    return solved, passed, pattern_missing


def run_single_case(
    case_id: str,
    category: str,
    pref_path: Path,
    roster_path: Path,
    extra_args: List[str],
    expected_success: bool,
    required_patterns: List[str],
) -> CaseResult:
    case_output_dir = RESULTS_DIR / case_id
    case_output_dir.mkdir(parents=True, exist_ok=True)
    command = [
        PYTHON,
        str(CLI),
        "--input",
        str(pref_path),
        "--mode",
        "ranking",
        "--guest-map-file",
        str(roster_path),
        "--solver",
        "heuristic",
        "--seed",
        "42",
        "--max-iter",
        "1200",
        "--num-restarts",
        "2",
        "--output-dir",
        str(case_output_dir),
        "--export-xlsx",
    ] + extra_args

    output, duration = run_cli(command)
    solved, passed, missing = evaluate_output(output, expected_success, required_patterns)

    return CaseResult(
        case_id=case_id,
        category=category,
        expected_success=expected_success,
        solved=solved,
        pattern_ok=(len(missing) == 0),
        passed=passed,
        duration_sec=duration,
        command=command,
        required_patterns=required_patterns,
        missing_patterns=missing,
        output_tail="\n".join(output.strip().splitlines()[-20:]),
    )


def main() -> int:
    rng = random.Random(20260213)
    base_roster = load_base_roster()

    if OUT_ROOT.exists():
        shutil.rmtree(OUT_ROOT)
    CASES_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    results: List[CaseResult] = []

    # Case 1: 正常 - 编号输入
    roster1 = set_attendance_and_vip(base_roster, absent_ids=[], vip_ids=["M1", "F1"])
    pref1 = build_preferences(roster1, rng, subject_mode="number", target_mode="id")
    c1_roster = CASES_DIR / "normal_01_roster.xlsx"
    c1_pref = CASES_DIR / "normal_01_pref.xlsx"
    write_roster_xlsx(c1_roster, roster1)
    write_pref_xlsx(c1_pref, pref1, "正常场景：主体编号+目标ID")
    results.append(
        run_single_case(
            "normal_01_id",
            "normal",
            c1_pref,
            c1_roster,
            [],
            True,
            ["✅ 求解成功", "🌟 设置特权嘉宾: F1, M1"],
        )
    )

    # Case 2: 正常 - 主体/目标混合中英文名
    roster2 = set_attendance_and_vip(base_roster, absent_ids=[], vip_ids=["M1", "F1"])
    pref2 = build_preferences(roster2, rng, subject_mode="mixed_name", target_mode="mixed")
    c2_roster = CASES_DIR / "normal_02_roster.xlsx"
    c2_pref = CASES_DIR / "normal_02_pref.xlsx"
    write_roster_xlsx(c2_roster, roster2)
    write_pref_xlsx(c2_pref, pref2, "正常场景：主体与目标混合中英文名/别名/ID")
    results.append(
        run_single_case(
            "normal_02_name_mixed",
            "normal",
            c2_pref,
            c2_roster,
            [],
            True,
            ["✅ 求解成功", "🌟 设置特权嘉宾: F1, M1"],
        )
    )

    # Case 3: 正常 - 嘉宾姓名列优先
    roster3 = set_attendance_and_vip(base_roster, absent_ids=[], vip_ids=["M1", "F1"])
    pref3 = build_preferences(
        roster3,
        rng,
        subject_mode="id",
        target_mode="mixed",
        include_subject_name_col=True,
        force_subject_name_priority=True,
    )
    c3_roster = CASES_DIR / "normal_03_roster.xlsx"
    c3_pref = CASES_DIR / "normal_03_pref_subject_name_col.xlsx"
    write_roster_xlsx(c3_roster, roster3)
    write_pref_xlsx(c3_pref, pref3, "正常场景：存在嘉宾姓名列，主体优先按姓名识别")
    results.append(
        run_single_case(
            "normal_03_subject_name_col",
            "normal",
            c3_pref,
            c3_roster,
            [],
            True,
            ["✅ 求解成功"],
        )
    )

    # Case 4: 正常 - 配对模式奇数总人数允许一组三人
    roster4 = set_attendance_and_vip(base_roster, absent_ids=["F10"], vip_ids=["M1", "F1"])
    pref4 = build_preferences(roster4, rng, subject_mode="mixed_name", target_mode="mixed")
    c4_roster = CASES_DIR / "normal_04_roster_odd.xlsx"
    c4_pref = CASES_DIR / "normal_04_pref_odd_pairing.xlsx"
    write_roster_xlsx(c4_roster, roster4)
    write_pref_xlsx(c4_pref, pref4, "正常场景：配对模式奇数人数")
    results.append(
        run_single_case(
            "normal_04_pairing_odd",
            "normal",
            c4_pref,
            c4_roster,
            ["--pairing-mode"],
            True,
            ["✅ 求解成功", "其中1组三人"],
        )
    )

    # Case 5/6: 正常 - round1 + round2 连续流程
    roster5 = set_attendance_and_vip(base_roster, absent_ids=[], vip_ids=["M1", "F1"])
    pref5_r1 = build_preferences(roster5, rng, subject_mode="mixed_name", target_mode="mixed")
    pref5_r2 = build_preferences(roster5, rng, subject_mode="mixed_name", target_mode="mixed")
    c5_roster = CASES_DIR / "normal_05_roster_round2.xlsx"
    c5_pref_r1 = CASES_DIR / "normal_05_pref_round1.xlsx"
    c5_pref_r2 = CASES_DIR / "normal_05_pref_round2.xlsx"
    write_roster_xlsx(c5_roster, roster5)
    write_pref_xlsx(c5_pref_r1, pref5_r1, "round2流程-第一轮")
    write_pref_xlsx(c5_pref_r2, pref5_r2, "round2流程-第二轮")
    case5_out = RESULTS_DIR / "normal_05_round2_flow"
    case5_out.mkdir(parents=True, exist_ok=True)

    cmd_r1 = [
        PYTHON,
        str(CLI),
        "--input",
        str(c5_pref_r1),
        "--mode",
        "ranking",
        "--guest-map-file",
        str(c5_roster),
        "--solver",
        "heuristic",
        "--seed",
        "42",
        "--max-iter",
        "1200",
        "--num-restarts",
        "2",
        "--output-dir",
        str(case5_out),
        "--export-xlsx",
    ]
    out_r1, dur_r1 = run_cli(cmd_r1)
    solved_r1 = "✅ 求解成功" in out_r1
    missing_r1 = [p for p in ["✅ 求解成功"] if p not in out_r1]
    results.append(
        CaseResult(
            case_id="normal_05_round1_for_round2",
            category="normal",
            expected_success=True,
            solved=solved_r1,
            pattern_ok=(len(missing_r1) == 0),
            passed=solved_r1 and len(missing_r1) == 0,
            duration_sec=dur_r1,
            command=cmd_r1,
            required_patterns=["✅ 求解成功"],
            missing_patterns=missing_r1,
            output_tail="\n".join(out_r1.strip().splitlines()[-20:]),
        )
    )

    round1_json = case5_out / "安排结果_第一轮.json"
    cmd_r2 = [
        PYTHON,
        str(CLI),
        "--round-two",
        "--first-round-file",
        str(round1_json),
        "--input",
        str(c5_pref_r2),
        "--mode",
        "ranking",
        "--guest-map-file",
        str(c5_roster),
        "--solver",
        "heuristic",
        "--seed",
        "42",
        "--max-iter",
        "1200",
        "--num-restarts",
        "2",
        "--output-dir",
        str(case5_out),
        "--export-xlsx",
    ]
    out_r2, dur_r2 = run_cli(cmd_r2)
    solved_r2 = "✅ 求解成功" in out_r2
    missing_r2 = [p for p in ["第二轮分组模式", "✅ 求解成功"] if p not in out_r2]
    results.append(
        CaseResult(
            case_id="normal_06_round2",
            category="normal",
            expected_success=True,
            solved=solved_r2,
            pattern_ok=(len(missing_r2) == 0),
            passed=solved_r2 and len(missing_r2) == 0,
            duration_sec=dur_r2,
            command=cmd_r2,
            required_patterns=["第二轮分组模式", "✅ 求解成功"],
            missing_patterns=missing_r2,
            output_tail="\n".join(out_r2.strip().splitlines()[-20:]),
        )
    )

    # Case 7: 极端 - 部分目标不可识别
    roster7 = set_attendance_and_vip(base_roster, absent_ids=[], vip_ids=["M1", "F1"])
    pref7 = build_preferences(roster7, rng, subject_mode="mixed_name", target_mode="mixed", invalid_target_every=4)
    c7_roster = CASES_DIR / "extreme_01_roster_unknown_target.xlsx"
    c7_pref = CASES_DIR / "extreme_01_pref_unknown_target.xlsx"
    write_roster_xlsx(c7_roster, roster7)
    write_pref_xlsx(c7_pref, pref7, "极端场景：目标中混入不存在姓名")
    results.append(
        run_single_case(
            "extreme_01_unknown_target",
            "extreme",
            c7_pref,
            c7_roster,
            [],
            True,
            ["偏好目标解析提示", "✅ 求解成功"],
        )
    )

    # Case 8: 极端 - 重名别名歧义
    roster8 = set_attendance_and_vip(base_roster, absent_ids=[], vip_ids=["M1", "F1"])
    # 让两位女嘉宾共享同一别名，触发歧义
    for idx, row in roster8.iterrows():
        gid = guest_id(row["嘉宾类型"], row["编号"])
        if gid in {"F1", "F2"}:
            roster8.at[idx, "别名"] = "Alex"
    pref8 = build_preferences(
        roster8,
        rng,
        subject_mode="mixed_name",
        target_mode="mixed",
        inject_ambiguous_alias_for_males=True,
    )
    c8_roster = CASES_DIR / "extreme_02_roster_ambiguous_alias.xlsx"
    c8_pref = CASES_DIR / "extreme_02_pref_ambiguous_alias.xlsx"
    write_roster_xlsx(c8_roster, roster8)
    write_pref_xlsx(c8_pref, pref8, "极端场景：别名重名（Alex）")
    results.append(
        run_single_case(
            "extreme_02_ambiguous_alias",
            "extreme",
            c8_pref,
            c8_roster,
            [],
            True,
            ["重名无法唯一匹配", "✅ 求解成功"],
        )
    )

    # Case 9: 极端 - strict-two-by-two 在奇数人数下不可行
    roster9 = set_attendance_and_vip(base_roster, absent_ids=["F10"], vip_ids=["M1", "F1"])
    pref9 = build_preferences(roster9, rng, subject_mode="number", target_mode="id")
    c9_roster = CASES_DIR / "extreme_03_roster_strict_infeasible.xlsx"
    c9_pref = CASES_DIR / "extreme_03_pref_strict_infeasible.xlsx"
    write_roster_xlsx(c9_roster, roster9)
    write_pref_xlsx(c9_pref, pref9, "极端场景：strict-two-by-two不可行")
    results.append(
        run_single_case(
            "extreme_03_strict_2by2_infeasible",
            "extreme",
            c9_pref,
            c9_roster,
            ["--strict-two-by-two"],
            False,
            ["strict-two-by-two 开启时，男女人数必须相等"],
        )
    )

    # Case 10: 极端 - 配对模式男女差值>1不可行
    roster10 = set_attendance_and_vip(base_roster, absent_ids=["F9", "F10"], vip_ids=["M1", "F1"])
    pref10 = build_preferences(roster10, rng, subject_mode="number", target_mode="mixed")
    c10_roster = CASES_DIR / "extreme_04_roster_pairing_diff2.xlsx"
    c10_pref = CASES_DIR / "extreme_04_pref_pairing_diff2.xlsx"
    write_roster_xlsx(c10_roster, roster10)
    write_pref_xlsx(c10_pref, pref10, "极端场景：配对模式男女差值>1")
    results.append(
        run_single_case(
            "extreme_04_pairing_diff2",
            "extreme",
            c10_pref,
            c10_roster,
            ["--pairing-mode"],
            False,
            ["配对模式不可行"],
        )
    )

    # Case 11: 极端 - VIP硬约束不可行（VIP无喜欢对象）
    roster11 = set_attendance_and_vip(base_roster, absent_ids=[], vip_ids=["M1"])
    pref11 = build_preferences(
        roster11,
        rng,
        subject_mode="mixed_name",
        target_mode="mixed",
        vip_without_preferences=["M1"],
    )
    c11_roster = CASES_DIR / "extreme_05_roster_vip_infeasible.xlsx"
    c11_pref = CASES_DIR / "extreme_05_pref_vip_infeasible.xlsx"
    write_roster_xlsx(c11_roster, roster11)
    write_pref_xlsx(c11_pref, pref11, "极端场景：VIP嘉宾无任何喜欢对象")
    results.append(
        run_single_case(
            "extreme_05_vip_infeasible",
            "extreme",
            c11_pref,
            c11_roster,
            [],
            False,
            ["VIP硬约束不可行"],
        )
    )

    # 输出报告
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    normal_total = sum(1 for r in results if r.category == "normal")
    extreme_total = sum(1 for r in results if r.category == "extreme")

    report_data = {
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "normal_cases": normal_total,
            "extreme_cases": extreme_total,
        },
        "cases": [
            {
                "case_id": r.case_id,
                "category": r.category,
                "expected_success": r.expected_success,
                "solved": r.solved,
                "pattern_ok": r.pattern_ok,
                "passed": r.passed,
                "duration_sec": round(r.duration_sec, 3),
                "command": r.command,
                "required_patterns": r.required_patterns,
                "missing_patterns": r.missing_patterns,
                "output_tail": r.output_tail,
            }
            for r in results
        ],
    }

    report_json = OUT_ROOT / "robustness_report.json"
    report_md = OUT_ROOT / "robustness_report.md"
    report_json.write_text(json.dumps(report_data, ensure_ascii=False, indent=2), encoding="utf-8")

    md_lines = [
        "# Robustness Test Report",
        "",
        f"- Total cases: {total}",
        f"- Passed: {passed}",
        f"- Failed: {failed}",
        f"- Normal cases: {normal_total}",
        f"- Extreme cases: {extreme_total}",
        "",
        "## Case Results",
        "",
        "| Case | Category | Expected Success | Solved | Pattern OK | Result | Time(s) |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        md_lines.append(
            f"| `{r.case_id}` | {r.category} | {str(r.expected_success)} | {str(r.solved)} | {str(r.pattern_ok)} | {'PASS' if r.passed else 'FAIL'} | {r.duration_sec:.2f} |"
        )

    md_lines.append("")
    md_lines.append("## Failed Cases Details")
    md_lines.append("")
    fail_cases = [r for r in results if not r.passed]
    if not fail_cases:
        md_lines.append("- None")
    else:
        for r in fail_cases:
            md_lines.extend(
                [
                    f"### {r.case_id}",
                    f"- Missing patterns: {', '.join(r.missing_patterns) if r.missing_patterns else 'None'}",
                    "- Output tail:",
                    "```text",
                    r.output_tail,
                    "```",
                    "",
                ]
            )

    report_md.write_text("\n".join(md_lines), encoding="utf-8")

    print(f"[DONE] report_json: {report_json}")
    print(f"[DONE] report_md:   {report_md}")
    print(f"[SUMMARY] total={total}, passed={passed}, failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
