#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Streamlit GUI for Dating Match Optimization (ranking-only).
"""

from __future__ import annotations

import json
import io
import hashlib
import mimetypes
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st


ROOT_DIR = Path(__file__).resolve().parent
CLI_PATH = ROOT_DIR / "cli.py"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "outputs"

PREF_COLUMNS = ["嘉宾类型", "编号", "嘉宾姓名", "对象1ID", "对象2ID"]
ROSTER_COLUMNS = ["嘉宾类型", "编号", "姓名", "是否到场", "是否VIP", "英文名", "别名"]


def init_state() -> None:
    if "manual_pref_signature" not in st.session_state:
        st.session_state.manual_pref_signature = ""
    if "manual_pref_male_df" not in st.session_state:
        st.session_state.manual_pref_male_df = pd.DataFrame(columns=PREF_COLUMNS)
    if "manual_pref_female_df" not in st.session_state:
        st.session_state.manual_pref_female_df = pd.DataFrame(columns=PREF_COLUMNS)
    if "manual_pref_label_to_id" not in st.session_state:
        st.session_state.manual_pref_label_to_id = {}
    if "manual_pref_male_options" not in st.session_state:
        st.session_state.manual_pref_male_options = []
    if "manual_pref_female_options" not in st.session_state:
        st.session_state.manual_pref_female_options = []


def normalize_column_name(col: str) -> str:
    return str(col).strip().replace(" ", "")


def pick_column(columns: List[str], candidates: List[str]) -> Optional[str]:
    normalized = {normalize_column_name(c): c for c in columns}
    for candidate in candidates:
        key = normalize_column_name(candidate)
        if key in normalized:
            return normalized[key]
    return None


def normalize_guest_type(value: object) -> Optional[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip().lower()
    if text in {"男", "male", "m", "man"}:
        return "男"
    if text in {"女", "female", "f", "woman"}:
        return "女"
    return None


def parse_guest_number(value: object) -> Optional[int]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float):
        ivalue = int(value)
        return ivalue if ivalue > 0 else None
    text = str(value).strip()
    if not text:
        return None
    m = re.search(r"(\d+)$", text)
    if not m:
        return None
    number = int(m.group(1))
    return number if number > 0 else None


def extract_roster_rows(uploaded_file, sheet_name: str) -> pd.DataFrame:
    raw = io.BytesIO(uploaded_file.getvalue())
    df = pd.read_excel(raw, sheet_name=sheet_name)
    if df.empty:
        raise ValueError("嘉宾名单sheet为空。")

    columns = [str(c) for c in df.columns]
    type_col = pick_column(columns, ["嘉宾类型", "类型", "性别"])
    number_col = pick_column(columns, ["编号", "ID", "id", "嘉宾编号"])
    name_col = pick_column(columns, ["姓名", "嘉宾姓名", "name", "Name"])
    present_col = pick_column(columns, ["是否到场", "到场", "是否出席", "出席", "在场"])
    english_col = pick_column(columns, ["英文名", "EnglishName", "English Name", "英文姓名", "英文"])

    missing = []
    if not type_col:
        missing.append("嘉宾类型")
    if not number_col:
        missing.append("编号")
    if not name_col:
        missing.append("姓名")
    if missing:
        raise ValueError(f"嘉宾名单缺少必要列: {', '.join(missing)}")

    rows = []
    for _, row in df.iterrows():
        guest_type = normalize_guest_type(row.get(type_col))
        guest_number = parse_guest_number(row.get(number_col))
        guest_name = str(row.get(name_col, "")).strip()
        if guest_type is None or guest_number is None or not guest_name:
            continue

        if present_col:
            present = normalize_yes_no(row.get(present_col), default_yes=True)
            if present != "是":
                continue

        english_name = ""
        if english_col:
            english_name = str(row.get(english_col, "")).strip()

        guest_id = f"{'M' if guest_type == '男' else 'F'}{guest_number}"
        rows.append(
            {
                "嘉宾类型": guest_type,
                "编号": guest_number,
                "嘉宾姓名": guest_name,
                "英文名": english_name,
                "guest_id": guest_id,
            }
        )

    roster = pd.DataFrame(rows)
    if roster.empty:
        raise ValueError("名单中没有可用的到场嘉宾（请检查嘉宾类型/编号/姓名/是否到场）。")

    roster = roster.drop_duplicates(subset=["guest_id"], keep="first")
    roster = roster.sort_values(by=["嘉宾类型", "编号"]).reset_index(drop=True)
    return roster


def build_display_label(row: pd.Series) -> str:
    guest_id = row["guest_id"]
    name = str(row.get("嘉宾姓名", "")).strip()
    english = str(row.get("英文名", "")).strip()
    if english:
        return f"{guest_id} | {name} / {english}"
    return f"{guest_id} | {name}"


def build_manual_pref_from_roster(roster: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, str], List[str], List[str]]:
    roster = roster.copy()
    roster["display"] = roster.apply(build_display_label, axis=1)
    label_to_id = {row["display"]: row["guest_id"] for _, row in roster.iterrows()}

    male_targets = roster[roster["嘉宾类型"] == "男"]["display"].tolist()
    female_targets = roster[roster["嘉宾类型"] == "女"]["display"].tolist()

    male_subjects = roster[roster["嘉宾类型"] == "男"][["嘉宾类型", "编号", "嘉宾姓名"]].copy()
    female_subjects = roster[roster["嘉宾类型"] == "女"][["嘉宾类型", "编号", "嘉宾姓名"]].copy()

    male_subjects["对象1ID"] = ""
    male_subjects["对象2ID"] = ""
    female_subjects["对象1ID"] = ""
    female_subjects["对象2ID"] = ""
    male_subjects = male_subjects[PREF_COLUMNS]
    female_subjects = female_subjects[PREF_COLUMNS]
    return male_subjects, female_subjects, label_to_id, male_targets, female_targets


def normalize_target_value(value: object, label_to_id: Dict[str, str]) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if text in label_to_id:
        return label_to_id[text]
    m = re.match(r"^([MF]\d+)", text, flags=re.IGNORECASE)
    if m:
        return m.group(1).upper()
    return text


def normalize_yes_no(value: object, default_yes: bool) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "是" if default_yes else "否"
    if isinstance(value, bool):
        return "是" if value else "否"
    text = str(value).strip().lower()
    if text in {"是", "y", "yes", "true", "1", "到场", "出席", "在场", "vip", "特权"}:
        return "是"
    if text in {"否", "n", "no", "false", "0", "缺席", "不到场", "普通", "非vip"}:
        return "否"
    return "是" if default_yes else "否"


def clean_pref_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in PREF_COLUMNS:
        if col not in out.columns:
            out[col] = ""
    out = out[PREF_COLUMNS]
    out = out.dropna(how="all")
    for col in PREF_COLUMNS:
        out[col] = out[col].apply(lambda x: "" if (x is None or (isinstance(x, float) and pd.isna(x))) else x)
    return out


def normalize_manual_pref_targets(df: pd.DataFrame, label_to_id: Dict[str, str]) -> pd.DataFrame:
    out = df.copy()
    for col in ["对象1ID", "对象2ID"]:
        out[col] = out[col].apply(lambda x: normalize_target_value(x, label_to_id))
    return out


def resolve_option_value(value: object, options: List[str]) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if text in options:
        return text

    m = re.match(r"^([MF]\d+)", text, flags=re.IGNORECASE)
    if m:
        guest_id = m.group(1).upper()
        for opt in options:
            if opt.startswith(f"{guest_id} |"):
                return opt
    return ""


def render_manual_pref_selector_table(
    subject_df: pd.DataFrame,
    options: List[str],
    section_key: str,
    section_title: str,
    option_help: str,
) -> pd.DataFrame:
    st.markdown(f"**{section_title}**")
    if subject_df.empty:
        return subject_df.copy()

    header_cols = st.columns([2.2, 1.4, 1.4])
    header_cols[0].markdown("主体")
    header_cols[1].markdown("对象1ID")
    header_cols[2].markdown("对象2ID")

    rows = []
    for idx, row in subject_df.reset_index(drop=True).iterrows():
        subject_label = f"{row['嘉宾类型']}{int(row['编号'])} · {row['嘉宾姓名']}"
        current_obj1 = resolve_option_value(row.get("对象1ID", ""), options)
        current_obj2 = resolve_option_value(row.get("对象2ID", ""), options)

        cols = st.columns([2.2, 1.4, 1.4])
        cols[0].markdown(subject_label)
        selected_obj1 = cols[1].selectbox(
            f"{section_title}_对象1_{idx}",
            options=options,
            index=options.index(current_obj1) if current_obj1 in options else 0,
            key=f"{section_key}_obj1_{idx}",
            label_visibility="collapsed",
            help=option_help,
        )
        selected_obj2 = cols[2].selectbox(
            f"{section_title}_对象2_{idx}",
            options=options,
            index=options.index(current_obj2) if current_obj2 in options else 0,
            key=f"{section_key}_obj2_{idx}",
            label_visibility="collapsed",
            help=option_help,
        )

        rows.append(
            {
                "嘉宾类型": row["嘉宾类型"],
                "编号": int(row["编号"]),
                "嘉宾姓名": row["嘉宾姓名"],
                "对象1ID": selected_obj1,
                "对象2ID": selected_obj2,
            }
        )

    return pd.DataFrame(rows, columns=PREF_COLUMNS)


def save_uploaded_file(uploaded, target_path: Path) -> None:
    target_path.write_bytes(uploaded.getbuffer())


def save_manual_pref_excel(pref_df: pd.DataFrame, pref_path: Path, pref_sheet: str) -> None:
    with pd.ExcelWriter(pref_path, engine="openpyxl") as writer:
        pref_df.to_excel(writer, sheet_name=pref_sheet, index=False)
        pd.DataFrame([{"说明": "由Streamlit手动输入生成"}]).to_excel(writer, sheet_name="说明", index=False)


def parse_saved_paths_from_logs(log_lines: List[str], started_at: float) -> List[Path]:
    saved: List[Path] = []
    pattern = re.compile(r"已保存:\s*(.+)")
    for line in log_lines:
        m = pattern.search(line)
        if not m:
            continue
        raw_path = m.group(1).strip()
        p = Path(raw_path)
        if not p.is_absolute():
            p = ROOT_DIR / p
        if p.exists() and p not in saved:
            saved.append(p)

    if saved:
        return saved

    # Fallback: find output files modified after process started.
    fallback: List[Path] = []
    if DEFAULT_OUTPUT_DIR.exists():
        for p in DEFAULT_OUTPUT_DIR.glob("安排结果_*.*"):
            if p.suffix.lower() in {".json", ".csv", ".xlsx"} and p.stat().st_mtime >= started_at - 0.5:
                fallback.append(p)
    return sorted(fallback, key=lambda x: x.stat().st_mtime, reverse=True)


def run_cli_streaming(command: List[str], log_container) -> Tuple[int, List[str], float, float]:
    started_at = time.time()
    process = subprocess.Popen(
        command,
        cwd=str(ROOT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    logs: List[str] = []
    log_container.code("等待日志输出...", language="bash", height=320, wrap_lines=False)
    while True:
        line = process.stdout.readline() if process.stdout else ""
        if not line and process.poll() is not None:
            break
        if line:
            logs.append(line.rstrip("\n"))
            display = "\n".join(logs[-600:])
            log_container.code(display, language="bash", height=320, wrap_lines=False)

    ret = process.wait()
    duration = time.time() - started_at
    return ret, logs, duration, started_at


def show_result_summary(json_path: Path) -> None:
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as e:
        st.warning(f"读取结果JSON失败: {e}")
        return

    meta = data.get("meta", {})
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("总分", f"{meta.get('total_score', 0)}")
    col2.metric("分组数", f"{meta.get('total_groups', 0)}")
    col3.metric("单向命中率", f"{meta.get('single_hit_rate', 0):.1%}" if isinstance(meta.get("single_hit_rate"), (int, float)) else str(meta.get("single_hit_rate", "")))
    col4.metric("互相命中率", f"{meta.get('mutual_hit_rate', 0):.1%}" if isinstance(meta.get("mutual_hit_rate"), (int, float)) else str(meta.get("mutual_hit_rate", "")))

    groups = data.get("groups", [])
    if groups:
        table_rows = []
        for g in groups:
            members_display = g.get("members_display", g.get("members", []))
            table_rows.append(
                {
                    "组号": g.get("group_id"),
                    "成员": ", ".join(members_display) if isinstance(members_display, list) else str(members_display),
                    "总得分": g.get("total_score"),
                    "单向喜欢数": g.get("single_preferences_count"),
                    "互相喜欢数": g.get("mutual_preferences_count"),
                }
            )
        st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)

    vip = data.get("privileged_guests")
    if vip:
        st.info(
            f"VIP满足: {vip.get('satisfied_count', 0)}/{len(vip.get('privileged_guests', []))} "
            f"({vip.get('satisfaction_rate', 0):.1f}%)"
        )


def render_downloads(saved_files: List[Path]) -> None:
    if not saved_files:
        st.warning("未检测到输出文件。")
        return

    st.write("输出文件（已同时保存到 `outputs/`）：")
    for idx, path in enumerate(saved_files):
        try:
            data = path.read_bytes()
        except Exception:
            continue
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        st.download_button(
            label=f"下载 {path.name}",
            data=data,
            file_name=path.name,
            mime=mime,
            key=f"download_{idx}_{path.name}",
        )


def main() -> None:
    st.set_page_config(page_title="相亲分组工具 Streamlit", layout="wide")
    init_state()

    st.title("相亲活动分组优化工具 (Streamlit)")
    st.caption("仅支持 ranking 模式。运行结果会展示在页面，同时直接保存到 outputs/。")

    with st.sidebar:
        st.header("运行配置")
        round_choice = st.selectbox("轮次", ["第一轮", "第二轮", "第三轮"], index=0)
        pairing_mode = False
        if round_choice == "第三轮":
            pairing_mode = st.checkbox("第三轮使用配对模式 (pairing-mode)", value=True)
        extra_vip = st.text_input("额外追加VIP（可选，逗号分隔，姓名或ID）", value="")
        st.markdown("---")
        st.write(f"输出目录固定为: `{DEFAULT_OUTPUT_DIR}`")

    st.subheader("名单输入（仅支持上传）")
    roster_file = st.file_uploader("上传嘉宾名单Excel（必需）", type=["xlsx", "xls"])

    input_mode = st.radio("偏好输入方式", ["上传Excel", "GUI手动输入"], horizontal=True)
    pref_sheet = st.text_input("偏好Sheet名", value="偏好")
    roster_sheet = st.text_input("名单Sheet名", value="嘉宾名单")

    pref_file = None
    first_round_json_file = None
    cleaned_pref: Optional[pd.DataFrame] = None
    male_editor_df: Optional[pd.DataFrame] = None
    female_editor_df: Optional[pd.DataFrame] = None

    roster_df: Optional[pd.DataFrame] = None
    roster_error = ""
    roster_signature = ""
    if roster_file is not None:
        roster_signature = hashlib.md5(roster_file.getvalue() + f"|{roster_sheet}".encode("utf-8")).hexdigest()
        try:
            roster_df = extract_roster_rows(roster_file, roster_sheet)
        except Exception as e:
            roster_error = str(e)
            st.error(f"名单读取失败: {e}")

    if input_mode == "上传Excel":
        pref_file = st.file_uploader("上传嘉宾偏好Excel", type=["xlsx", "xls"])
    else:
        st.subheader("手动输入：偏好表（基于名单自动生成）")
        if roster_file is None:
            st.info("请先上传嘉宾名单，系统会自动填充嘉宾类型/编号/姓名，并提供下拉偏好选择。")
        elif roster_error:
            st.warning("请先修正名单文件后再进行手动偏好输入。")
        elif roster_df is not None:
            if st.session_state.manual_pref_signature != roster_signature:
                male_df, female_df, label_to_id, male_targets, female_targets = build_manual_pref_from_roster(roster_df)
                st.session_state.manual_pref_male_df = male_df
                st.session_state.manual_pref_female_df = female_df
                st.session_state.manual_pref_label_to_id = label_to_id
                st.session_state.manual_pref_male_options = [""] + female_targets
                st.session_state.manual_pref_female_options = [""] + male_targets
                st.session_state.manual_pref_signature = roster_signature

            male_count = len(st.session_state.manual_pref_male_df)
            female_count = len(st.session_state.manual_pref_female_df)
            st.caption(f"已生成到场嘉宾偏好表：男 {male_count} 人，女 {female_count} 人。")

            if male_count > 0:
                male_editor = render_manual_pref_selector_table(
                    st.session_state.manual_pref_male_df,
                    st.session_state.manual_pref_male_options,
                    section_key=f"pref_male_{roster_signature}",
                    section_title="男嘉宾偏好（对象为女嘉宾）",
                    option_help="从下拉选择女嘉宾",
                )
                male_editor_df = male_editor
                st.session_state.manual_pref_male_df = male_editor

            if female_count > 0:
                female_editor = render_manual_pref_selector_table(
                    st.session_state.manual_pref_female_df,
                    st.session_state.manual_pref_female_options,
                    section_key=f"pref_female_{roster_signature}",
                    section_title="女嘉宾偏好（对象为男嘉宾）",
                    option_help="从下拉选择男嘉宾",
                )
                female_editor_df = female_editor
                st.session_state.manual_pref_female_df = female_editor

            if male_count == 0 or female_count == 0:
                st.warning("到场名单中至少需要男女各1人，才能生成有效的ranking偏好。")

    if round_choice == "第二轮":
        first_round_json_file = st.file_uploader("上传第一轮结果JSON（第二轮必需）", type=["json"])

    run_btn = st.button("开始运行", type="primary", use_container_width=True)
    st.subheader("运行日志")
    log_placeholder = st.empty()
    log_placeholder.code("点击“开始运行”后显示日志", language="bash", height=320, wrap_lines=False)

    if not run_btn:
        return

    # Validation
    if roster_file is None:
        st.error("请先上传嘉宾名单Excel。")
        return
    if roster_error:
        st.error(f"名单读取失败: {roster_error}")
        return

    if round_choice == "第二轮" and first_round_json_file is None:
        st.error("第二轮必须上传第一轮结果JSON。")
        return

    if input_mode == "上传Excel":
        if pref_file is None:
            st.error("上传模式下必须提供嘉宾偏好Excel。")
            return
    else:
        if male_editor_df is None and female_editor_df is None:
            st.error("手动输入模式下未检测到可编辑的偏好表，请先检查名单。")
            return
        manual_pref_df = pd.concat(
            [df for df in [male_editor_df, female_editor_df] if df is not None],
            ignore_index=True,
        )
        cleaned_pref = clean_pref_df(manual_pref_df)
        cleaned_pref = normalize_manual_pref_targets(cleaned_pref, st.session_state.manual_pref_label_to_id)
        if cleaned_pref.empty:
            st.error("手动输入的偏好表为空。")
            return
        dup_choice = cleaned_pref[
            (cleaned_pref["对象1ID"].astype(str).str.strip() != "")
            & (cleaned_pref["对象1ID"].astype(str).str.strip() == cleaned_pref["对象2ID"].astype(str).str.strip())
        ]
        if not dup_choice.empty:
            first_bad = dup_choice.iloc[0]
            st.error(
                f"手动偏好中存在对象1和对象2相同：{first_bad['嘉宾类型']}{int(first_bad['编号'])} "
                f"{first_bad.get('嘉宾姓名', '')}"
            )
            return

    temp_dir = Path(tempfile.mkdtemp(prefix="dating_match_streamlit_"))
    pref_path = temp_dir / "input_pref.xlsx"
    roster_path = temp_dir / "input_roster.xlsx"
    first_round_json_path: Optional[Path] = None

    if input_mode == "上传Excel":
        save_uploaded_file(pref_file, pref_path)
    else:
        save_manual_pref_excel(cleaned_pref, pref_path, pref_sheet)

    save_uploaded_file(roster_file, roster_path)

    if first_round_json_file is not None:
        first_round_json_path = temp_dir / "first_round_result.json"
        save_uploaded_file(first_round_json_file, first_round_json_path)

    command = [
        sys.executable,
        str(CLI_PATH),
        "--input",
        str(pref_path),
        "--mode",
        "ranking",
        "--sheet",
        pref_sheet,
        "--guest-map-file",
        str(roster_path),
        "--guest-map-sheet",
        roster_sheet,
        "--output-dir",
        str(DEFAULT_OUTPUT_DIR),
        "--export-xlsx",
        "--verbose",
    ]

    if round_choice == "第二轮":
        command.extend(["--round-two", "--first-round-file", str(first_round_json_path)])
    if round_choice == "第三轮" and pairing_mode:
        command.append("--pairing-mode")
    if extra_vip.strip():
        command.extend(["--privileged-guests", extra_vip.strip()])

    st.write("命令预览：")
    st.code(" ".join(command), language="bash")

    with st.spinner("程序运行中..."):
        ret, logs, duration, started_at = run_cli_streaming(command, log_placeholder)
        saved_files = parse_saved_paths_from_logs(logs, started_at=started_at)

    if ret == 0 and any("✅ 求解成功" in ln for ln in logs):
        st.success(f"运行成功，用时 {duration:.2f}s")
    elif ret == 0:
        st.warning("程序退出码为0，但未检测到“求解成功”字样，请检查日志。")
    else:
        st.error(f"运行失败，退出码 {ret}，请检查日志。")

    # 优先展示JSON结果
    json_candidates = [p for p in saved_files if p.suffix.lower() == ".json"]
    if json_candidates:
        latest_json = sorted(json_candidates, key=lambda p: p.stat().st_mtime, reverse=True)[0]
        st.subheader("结果概览")
        show_result_summary(latest_json)

    st.subheader("结果下载")
    render_downloads(saved_files)


if __name__ == "__main__":
    main()
