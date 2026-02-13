#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
相亲活动分组优化命令行工具
主程序入口，整合解析、建模、求解和输出功能
"""

import argparse
import sys
import os
import time
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# 强制输出实时刷新
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

def print_flush(*args, **kwargs):
    """带强制刷新的print函数"""
    print(*args, **kwargs)
    sys.stdout.flush()

# 添加src目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.parser_cn import ChinesePreferenceParser
from src.parser_ranking import RankingPreferenceParser
from src.graph import PreferenceGraph, validate_grouping
from src.solver_ilp import ILPSolver
from src.solver_heur import HeuristicSolver
from src.io_excel import DataIO


def print_banner():
    """打印程序横幅"""
    banner = """
    ================================================
    相亲活动分组优化工具 v1.0
    Dating Match Optimization System
    ================================================
    """
    print(banner)


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='相亲活动分组优化工具 - 解析中文偏好并生成最优分组方案',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  %(prog)s --input 偏好数据.xlsx                    # 默认ranking模式ID解析
  %(prog)s --input 偏好数据.xlsx --export-xlsx     # 导出Excel结果
  %(prog)s --input 偏好数据.xlsx --mode text       # 使用text模式中文解析
  %(prog)s --input 偏好数据.xlsx --first-preference-weight 3.0
  %(prog)s --input 偏好数据.xlsx --dry-run-parse   # 仅解析不求解
  %(prog)s --input 偏好数据.xlsx --solver heuristic --seed 42
        """
    )
    
    # 必需参数
    parser.add_argument('--input', '-i', 
                       required=True,
                       help='输入Excel文件路径（必填）')
    
    # 输入选项
    parser.add_argument('--sheet', 
                       default='偏好',
                       help='Excel sheet名称（默认: 偏好）')
    
    parser.add_argument('--mode',
                       choices=['text', 'ranking'],
                       default='ranking',
                       help='输入数据模式：ranking=ID/姓名混合偏好（默认），text=中文描述解析')

    parser.add_argument('--guest-map-file',
                       help='嘉宾名单文件路径（可选，默认使用input文件），用于姓名映射和到场状态')

    parser.add_argument('--guest-map-sheet',
                       default='嘉宾名单',
                       help='嘉宾名单sheet名称（默认: 嘉宾名单）')

    parser.add_argument('--absent-guests',
                       type=str,
                       help='缺席嘉宾列表，逗号分隔，支持姓名或ID（如：张三,F8,M3）')
    
    # Ranking模式权重设置
    parser.add_argument('--first-preference-weight',
                       type=float,
                       default=2.0,
                       help='第一偏好权重（ranking模式，默认: 2.0）')
    
    parser.add_argument('--second-preference-weight',
                       type=float,
                       default=1.0,
                       help='第二偏好权重（ranking模式，默认: 1.0）')
    
    # 约束选项
    parser.add_argument('--two-by-two',
                       type=lambda x: x.lower() in ['true', '1', 'yes'],
                       default=True,
                       help='是否强制每组2男2女（默认: true）')

    parser.add_argument('--strict-two-by-two',
                       action='store_true',
                       help='严格保持2男2女，若人数/性别不满足则直接报错（默认自动放宽）')
    
    parser.add_argument('--pairing-mode',
                       action='store_true',
                       help='一男一女配对模式：生成12对1v1配对而不是6组2v2分组')
    
    # 第二轮分组选项
    parser.add_argument('--round-two',
                       action='store_true',
                       help='第二轮分组模式：基于第一轮结果进行重新分组')
    
    parser.add_argument('--first-round-file',
                       help='第一轮结果JSON文件路径（用于第二轮分组）')
    
    parser.add_argument('--penalty-weight',
                       type=float,
                       default=-1.0,
                       help='第一轮单向喜欢关系的惩罚权重（默认: -1.0）')
    
    # 评分选项
    parser.add_argument('--mutual-weight',
                       type=float,
                       default=2.0,
                       help='互相喜欢的总权重（默认: 2.0）')
    
    # 求解器选项
    parser.add_argument('--solver',
                       choices=['auto', 'ilp', 'heuristic'],
                       default='auto',
                       help='求解器选择（默认: auto）')
    
    # 启发式算法参数
    parser.add_argument('--seed',
                       type=int,
                       help='随机种子（用于可重现结果）')
    
    parser.add_argument('--max-iter',
                       type=int,
                       default=10000,
                       help='启发式算法最大迭代次数（默认: 10000）')
    
    parser.add_argument('--num-restarts',
                       type=int,
                       default=5,
                       help='启发式算法重启次数（默认: 5）')
    
    parser.add_argument('--heur-algorithm',
                       choices=['hill_climbing', 'simulated_annealing'],
                       default='simulated_annealing',
                       help='启发式算法类型（默认: simulated_annealing）')
    
    # 人数配置选项
    parser.add_argument('--group-size',
                       type=int,
                       default=4,
                       help='每组人数（默认: 4，最后一组可能少于此值）')
    
    # 特权嘉宾选项
    parser.add_argument('--privileged-guests',
                       type=str,
                       help='特权嘉宾列表，用逗号分隔（例如：M1,F3,M5）。特权嘉宾保证分到至少一个自己喜欢的嘉宾同组')
    
    # 输出选项
    parser.add_argument('--export-xlsx',
                       action='store_true',
                       help='导出Excel格式结果')
    
    parser.add_argument('--output-dir',
                       default='outputs',
                       help='输出目录（默认: outputs）')
    
    # 调试选项
    parser.add_argument('--dry-run-parse',
                       action='store_true',
                       help='仅解析偏好数据，不进行求解')
    
    parser.add_argument('--verbose',
                       action='store_true',
                       help='详细输出模式')
    
    # ILP选项
    parser.add_argument('--ilp-time-limit',
                       type=int,
                       default=300,
                       help='ILP求解时间限制（秒，默认: 300）')
    
    return parser.parse_args()


def create_progress_callback(verbose):
    """创建进度回调函数"""
    def callback(message):
        if verbose:
            print("[INFO] " + str(message))
            sys.stdout.flush()  # 强制刷新输出
    return callback


def detect_guest_counts(data):
    """
    从数据中自动检测男女嘉宾人数
    
    Args:
        data: 偏好数据列表
        
    Returns:
        (num_males, num_females): 男性和女性人数
    """
    male_ids = set()
    female_ids = set()
    
    for row in data:
        guest_type = row.get('嘉宾类型', '').strip()
        guest_id = row.get('编号', '')
        
        if guest_type and isinstance(guest_id, (int, str)) and str(guest_id).isdigit():
            guest_id = int(guest_id)
            if guest_type == '男':
                male_ids.add(guest_id)
            elif guest_type == '女':
                female_ids.add(guest_id)
    
    num_males = max(male_ids) if male_ids else 0
    num_females = max(female_ids) if female_ids else 0
    
    return num_males, num_females


def build_guest_ids_from_data(data: List[Dict]) -> Set[str]:
    """从原始数据行构建嘉宾ID集合（M1/F1格式）"""
    guest_ids = set()
    for row in data:
        guest_type = str(row.get('嘉宾类型', '')).strip()
        guest_no = row.get('编号')
        if guest_type in ('男', '女') and isinstance(guest_no, (int, str)) and str(guest_no).isdigit():
            guest_ids.add(f"{'M' if guest_type == '男' else 'F'}{int(guest_no)}")
    return guest_ids


def normalize_lookup_token(token: str) -> str:
    """将姓名/别名标准化为可匹配token（中英文统一）"""
    normalized = unicodedata.normalize('NFKC', str(token).strip())
    normalized = re.sub(r'\s+', ' ', normalized)
    return normalized.lower()


def build_guest_name_index(guest_profiles: List[Dict]) -> Tuple[Dict[str, str], Dict[str, List[str]]]:
    """构建 guest_id -> 主姓名 和 标准化别名 -> [guest_id] 索引"""
    guest_id_to_name = {}
    name_to_guest_ids = {}
    for item in guest_profiles:
        guest_id = item.get('guest_id')
        guest_name = str(item.get('guest_name', '')).strip()
        if not guest_id or not guest_name:
            continue
        guest_id_to_name[guest_id] = guest_name

        candidate_tokens = [guest_name]
        english_name = str(item.get('english_name', '')).strip()
        if english_name and english_name.lower() != 'nan':
            candidate_tokens.append(english_name)

        for alias in item.get('aliases', []) or []:
            alias_str = str(alias).strip()
            if alias_str:
                candidate_tokens.append(alias_str)

        for token in candidate_tokens:
            norm = normalize_lookup_token(token)
            if not norm:
                continue
            name_to_guest_ids.setdefault(norm, set()).add(guest_id)

    normalized_name_index = {
        key: sorted(list(value))
        for key, value in name_to_guest_ids.items()
    }
    return guest_id_to_name, normalized_name_index


def resolve_guest_tokens(raw_tokens: List[str], valid_guest_ids: Set[str], name_to_guest_ids: Dict[str, List[str]]) -> Tuple[Set[str], List[str]]:
    """
    解析姓名/ID混合输入，返回标准化guest_id集合
    支持 token: M1/F3 或精确姓名
    """
    resolved = set()
    warnings = []

    for token in raw_tokens:
        token = str(token).strip()
        if not token:
            continue

        token_upper = token.upper()
        if len(token_upper) >= 2 and token_upper[0] in ('M', 'F') and token_upper[1:].isdigit():
            guest_id = f"{token_upper[0]}{int(token_upper[1:])}"
            if guest_id in valid_guest_ids:
                resolved.add(guest_id)
            else:
                warnings.append(f"未找到嘉宾ID: {token}")
            continue

        normalized_token = normalize_lookup_token(token)
        candidate_ids = [gid for gid in name_to_guest_ids.get(normalized_token, []) if gid in valid_guest_ids]
        if len(candidate_ids) == 1:
            resolved.add(candidate_ids[0])
        elif len(candidate_ids) > 1:
            warnings.append(f"姓名重名无法唯一匹配: {token} -> {candidate_ids}")
        else:
            warnings.append(f"无法识别嘉宾: {token}")

    return resolved, warnings


def resolve_preference_target_token(target_raw, subject_gender: str, valid_guest_ids: Set[str],
                                    name_to_guest_ids: Dict[str, List[str]]) -> Tuple[str, Optional[str]]:
    """
    解析ranking偏好列里的目标值，支持ID/数字/中文名/英文名/别名
    Returns:
        (resolved_guest_id, warning_message)
    """
    if target_raw is None:
        return '', None

    token = str(target_raw).strip()
    if not token:
        return '', None

    token_nfkc = unicodedata.normalize('NFKC', token)
    id_match = re.match(r'^\s*([mMfF])\s*(\d+)\s*$', token_nfkc)
    if id_match:
        candidate = f"{id_match.group(1).upper()}{int(id_match.group(2))}"
        if candidate in valid_guest_ids:
            return candidate, None
        return '', f"未找到目标ID: {token}"

    if re.match(r'^\s*\d+(\.0+)?\s*$', token_nfkc):
        target_no = int(float(token_nfkc))
        target_prefix = 'F' if subject_gender == '男' else 'M'
        candidate = f"{target_prefix}{target_no}"
        if candidate in valid_guest_ids:
            return candidate, None
        return '', f"目标编号超出范围: {token}"

    normalized_token = normalize_lookup_token(token_nfkc)
    candidate_ids = [gid for gid in name_to_guest_ids.get(normalized_token, []) if gid in valid_guest_ids]
    if not candidate_ids:
        return '', f"无法识别偏好目标: {token}"

    expected_prefix = 'F' if subject_gender == '男' else 'M'
    opposite_gender_ids = [gid for gid in candidate_ids if gid.startswith(expected_prefix)]
    if len(opposite_gender_ids) == 1:
        return opposite_gender_ids[0], None
    if len(opposite_gender_ids) > 1:
        return '', f"偏好目标重名无法唯一匹配: {token} -> {opposite_gender_ids}"

    if len(candidate_ids) == 1:
        # 允许先落到唯一ID，后续由parser给出性别不匹配警告
        return candidate_ids[0], None
    return '', f"偏好目标重名无法唯一匹配: {token} -> {candidate_ids}"


def normalize_ranking_preference_targets(data: List[Dict], valid_guest_ids: Set[str],
                                         name_to_guest_ids: Dict[str, List[str]]) -> Tuple[List[Dict], List[str]]:
    """将ranking偏好列中的姓名/别名转换为标准ID，保留无法解析值并给出告警"""
    warnings = []
    normalized_data = []

    for idx, row in enumerate(data):
        new_row = dict(row)
        subject_gender = str(new_row.get('嘉宾类型', '')).strip()
        for col in ['对象1ID', '对象2ID']:
            raw_value = new_row.get(col, '')
            if raw_value is None or str(raw_value).strip() == '':
                continue

            resolved_id, warning = resolve_preference_target_token(
                raw_value, subject_gender, valid_guest_ids, name_to_guest_ids
            )
            if resolved_id:
                new_row[col] = resolved_id
            elif warning:
                warnings.append(f"第{idx+1}行 {col}: {warning}")
        normalized_data.append(new_row)

    return normalized_data, warnings


def normalize_ranking_subjects(data: List[Dict], name_to_guest_ids: Dict[str, List[str]]) -> Tuple[List[Dict], List[str]]:
    """
    将ranking主体（编号或嘉宾姓名）转换为标准编号。
    支持主体来源：
    - 编号列：数字 / M1,F3 / 中文名 / 英文名 / 别名
    - 可选嘉宾姓名列：中文名 / 英文名 / 别名（优先于编号列）
    """
    warnings = []
    normalized_data = []

    for idx, row in enumerate(data):
        new_row = dict(row)
        guest_type = str(new_row.get('嘉宾类型', '')).strip()
        expected_prefix = 'M' if guest_type == '男' else 'F'

        subject_name_token = str(new_row.get('嘉宾姓名', '')).strip() if new_row.get('嘉宾姓名') is not None else ''
        subject_no_token = str(new_row.get('编号', '')).strip() if new_row.get('编号') is not None else ''
        token = subject_name_token if subject_name_token else subject_no_token

        if not token:
            warnings.append(f"第{idx+1}行 主体为空")
            normalized_data.append(new_row)
            continue

        token_nfkc = unicodedata.normalize('NFKC', token)

        # 1) 纯数字
        if re.match(r'^\s*\d+(\.0+)?\s*$', token_nfkc):
            new_row['编号'] = int(float(token_nfkc))
            normalized_data.append(new_row)
            continue

        # 2) M/F+数字
        id_match = re.match(r'^\s*([mMfF])\s*(\d+)\s*$', token_nfkc)
        if id_match:
            prefix = id_match.group(1).upper()
            if prefix != expected_prefix:
                warnings.append(f"第{idx+1}行 主体性别与嘉宾类型不匹配: {token}")
                normalized_data.append(new_row)
                continue
            new_row['编号'] = int(id_match.group(2))
            normalized_data.append(new_row)
            continue

        # 3) 中文名/英文名/别名
        normalized_token = normalize_lookup_token(token_nfkc)
        candidate_ids = name_to_guest_ids.get(normalized_token, [])
        if not candidate_ids:
            warnings.append(f"第{idx+1}行 无法识别主体: {token}")
            normalized_data.append(new_row)
            continue

        type_matched = [gid for gid in candidate_ids if gid.startswith(expected_prefix)]
        if len(type_matched) == 1:
            new_row['编号'] = int(type_matched[0][1:])
        elif len(type_matched) > 1:
            warnings.append(f"第{idx+1}行 主体重名无法唯一匹配: {token} -> {type_matched}")
        elif len(candidate_ids) == 1:
            warnings.append(f"第{idx+1}行 主体性别与嘉宾类型不匹配: {token} -> {candidate_ids[0]}")
        else:
            warnings.append(f"第{idx+1}行 主体重名无法唯一匹配: {token} -> {candidate_ids}")

        normalized_data.append(new_row)

    return normalized_data, warnings


def normalize_ranking_data_for_attendance(data: List[Dict], absent_guest_ids: Set[str]) -> Tuple[List[Dict], Dict[str, str], Dict[str, str], List[str]]:
    """
    对ranking数据做缺席过滤 + 性别内重编号（保证编号连续）

    Returns:
        normalized_data: 过滤并重编号后的数据
        old_to_new_guest_id: 例如 {"M8":"M7"}
        new_to_old_guest_id: 例如 {"M7":"M8"}
        warnings: 处理告警
    """
    warnings = []
    subject_guest_ids = []

    for row in data:
        guest_type = str(row.get('嘉宾类型', '')).strip()
        guest_no = row.get('编号')
        if guest_type not in ('男', '女') or not str(guest_no).isdigit():
            continue
        old_guest_id = f"{'M' if guest_type == '男' else 'F'}{int(guest_no)}"
        if old_guest_id in absent_guest_ids:
            continue
        subject_guest_ids.append(old_guest_id)

    present_male_old = sorted([int(g[1:]) for g in subject_guest_ids if g.startswith('M')])
    present_female_old = sorted([int(g[1:]) for g in subject_guest_ids if g.startswith('F')])

    old_to_new_guest_id = {}
    for idx, old_no in enumerate(present_male_old, start=1):
        old_to_new_guest_id[f"M{old_no}"] = f"M{idx}"
    for idx, old_no in enumerate(present_female_old, start=1):
        old_to_new_guest_id[f"F{old_no}"] = f"F{idx}"

    new_to_old_guest_id = {v: k for k, v in old_to_new_guest_id.items()}

    def map_target(target_raw, subject_gender: str) -> str:
        if target_raw is None:
            return ''
        target_str = str(target_raw).strip()
        if not target_str:
            return ''

        target_guest_id = None
        if target_str[0].upper() in ('M', 'F') and target_str[1:].isdigit():
            target_guest_id = f"{target_str[0].upper()}{int(target_str[1:])}"
        else:
            try:
                target_no = int(float(target_str))
                target_prefix = 'F' if subject_gender == '男' else 'M'
                target_guest_id = f"{target_prefix}{target_no}"
            except Exception:
                warnings.append(f"无法解析目标ID: {target_raw}")
                return ''

        if target_guest_id in absent_guest_ids:
            return ''
        if target_guest_id not in old_to_new_guest_id:
            return ''
        return old_to_new_guest_id[target_guest_id]

    normalized_data = []
    for row in data:
        guest_type = str(row.get('嘉宾类型', '')).strip()
        guest_no = row.get('编号')
        if guest_type not in ('男', '女') or not str(guest_no).isdigit():
            continue

        old_guest_id = f"{'M' if guest_type == '男' else 'F'}{int(guest_no)}"
        if old_guest_id in absent_guest_ids:
            continue
        if old_guest_id not in old_to_new_guest_id:
            continue

        new_row = dict(row)
        new_subject = old_to_new_guest_id[old_guest_id]
        new_row['编号'] = int(new_subject[1:])

        for col in ['对象1ID', '对象2ID']:
            mapped_target = map_target(new_row.get(col, ''), guest_type)
            if mapped_target:
                new_row[col] = int(mapped_target[1:])
            else:
                new_row[col] = ''

        normalized_data.append(new_row)

    return normalized_data, old_to_new_guest_id, new_to_old_guest_id, warnings


def convert_guest_ids_to_internal(guest_ids: Set[str], old_to_new_guest_id: Dict[str, str]) -> Set[str]:
    """将外部ID集合转换为内部重编号ID集合"""
    result = set()
    for guest_id in guest_ids:
        if guest_id in old_to_new_guest_id:
            result.add(old_to_new_guest_id[guest_id])
    return result


def remap_penalty_edges(penalties: Set[Tuple[str, str]], old_to_new_guest_id: Dict[str, str]) -> Set[Tuple[str, str]]:
    """将第一轮惩罚边按新编号映射，不在当前出席集合中的边会被丢弃"""
    remapped = set()
    for src, dst in penalties:
        if src in old_to_new_guest_id and dst in old_to_new_guest_id:
            remapped.add((old_to_new_guest_id[src], old_to_new_guest_id[dst]))
    return remapped


def main():
    """主函数"""
    # 打印横幅
    print_banner()
    
    # 解析命令行参数
    args = parse_arguments()
    
    # 创建进度回调
    progress_callback = create_progress_callback(args.verbose)
    
    try:
        # 参数验证
        if args.round_two:
            if not args.first_round_file:
                print("❌ 第二轮模式需要指定第一轮结果文件 (--first-round-file)")
                return
            if args.pairing_mode:
                print("❌ 第二轮模式暂不支持配对模式")
                return
        
        io_handler = DataIO()
        
        # 第二轮模式：解析第一轮结果
        first_round_penalties = set()
        if args.round_two:
            print("\n🔄 第二轮分组模式")
            print(f"📖 正在解析第一轮结果: {args.first_round_file}")
            first_round_penalties, penalty_warnings = io_handler.parse_first_round_results(args.first_round_file)
            
            if penalty_warnings:
                print("⚠️  第一轮结果解析警告:")
                for warning in penalty_warnings:
                    print(f"   {warning}")
            
            if not first_round_penalties:
                print("⚠️  第一轮结果中未找到单向喜欢关系，将按正常模式进行")
        
        # 1. 读取偏好数据
        print(f"\n📖 正在读取偏好数据...")
        progress_callback("从文件读取: " + str(args.input))
        
        if args.mode == 'ranking':
            data, io_warnings = io_handler.read_ranking_from_excel(args.input, args.sheet)
        else:
            data, io_warnings = io_handler.read_preferences_from_excel(args.input, args.sheet)
        
        print_flush("✅ 成功读取 " + str(len(data)) + " 条偏好记录")
        
        if io_warnings:
            print("⚠️  读取警告:")
            for warning in io_warnings:
                print(f"   {warning}")

        # 1.1 读取嘉宾名单（姓名映射 + 到场状态）
        guest_map_file = args.guest_map_file or args.input
        guest_profiles = []
        guest_map_warnings = []
        try:
            guest_profiles, guest_map_warnings = io_handler.read_guest_mapping(guest_map_file, args.guest_map_sheet)
        except Exception as e:
            guest_map_warnings.append(str(e))

        if guest_map_warnings and args.verbose:
            print("⚠️  嘉宾名单读取提示:")
            for warning in guest_map_warnings[:10]:
                print(f"   {warning}")

        guest_id_to_name, name_to_guest_ids = build_guest_name_index(guest_profiles)

        # 1.1.5 ranking主体支持姓名/英文名/别名（统一转换为数字编号）
        if args.mode == 'ranking' and name_to_guest_ids:
            data, subject_resolve_warnings = normalize_ranking_subjects(data, name_to_guest_ids)
            if subject_resolve_warnings:
                print("⚠️  主体嘉宾解析提示:")
                for warning in subject_resolve_warnings[:10]:
                    print(f"   {warning}")
                if len(subject_resolve_warnings) > 10:
                    print(f"   ... 还有 {len(subject_resolve_warnings) - 10} 条")

        all_guest_ids_raw = build_guest_ids_from_data(data)
        if guest_id_to_name:
            print_flush(f"🪪 已加载姓名映射: {len(guest_id_to_name)} 人（来源: {guest_map_file}#{args.guest_map_sheet}）")

        # 1.15 ranking偏好列支持姓名/英文名/别名（统一转换为标准ID）
        if args.mode == 'ranking' and name_to_guest_ids:
            data, preference_target_warnings = normalize_ranking_preference_targets(
                data, all_guest_ids_raw, name_to_guest_ids
            )
            if preference_target_warnings:
                print("⚠️  偏好目标解析提示:")
                for warning in preference_target_warnings[:10]:
                    print(f"   {warning}")
                if len(preference_target_warnings) > 10:
                    print(f"   ... 还有 {len(preference_target_warnings) - 10} 条")

        # 1.2 解析缺席名单（名单中的“是否到场=否” + CLI传入）
        absent_from_roster = {
            p['guest_id'] for p in guest_profiles
            if not p.get('is_present', True) and p.get('guest_id') in all_guest_ids_raw
        }

        absent_from_cli = set()
        if args.absent_guests:
            raw_absent_tokens = [t.strip() for t in args.absent_guests.split(',') if t.strip()]
            absent_from_cli, absent_parse_warnings = resolve_guest_tokens(
                raw_absent_tokens, all_guest_ids_raw, name_to_guest_ids
            )
            for warning in absent_parse_warnings:
                print(f"⚠️  缺席名单解析: {warning}")

        absent_guest_ids = absent_from_roster | absent_from_cli
        present_guest_ids_raw = set(all_guest_ids_raw) - set(absent_guest_ids)
        if absent_guest_ids:
            absent_display = []
            for guest_id in sorted(absent_guest_ids):
                guest_name = guest_id_to_name.get(guest_id)
                absent_display.append(f"{guest_id}({guest_name})" if guest_name else guest_id)
            print_flush(f"🚫 缺席嘉宾: {', '.join(absent_display)}")

        # 默认不变更编号；ranking缺席时会重编号为连续ID
        old_to_new_guest_id = {gid: gid for gid in all_guest_ids_raw}
        new_to_old_guest_id = {gid: gid for gid in all_guest_ids_raw}

        if args.mode == 'ranking':
            if absent_guest_ids:
                data, old_to_new_guest_id, new_to_old_guest_id, normalize_warnings = normalize_ranking_data_for_attendance(data, absent_guest_ids)
                if normalize_warnings and args.verbose:
                    print("⚠️  缺席重编号提示:")
                    for warning in normalize_warnings[:10]:
                        print(f"   {warning}")
                print_flush(f"🚫 已处理缺席嘉宾: {len(absent_guest_ids)} 人")
                print_flush("🔁 已对到场嘉宾重新编号（按性别各自连续）")
        else:
            if absent_guest_ids:
                print("❌ text模式暂不支持缺席重编号，请使用ranking模式处理缺席场景")
                return

        if not data:
            print("❌ 过滤缺席后无有效数据，无法求解")
            return

        # 第二轮惩罚边按新编号映射（缺席后可能发生重编号）
        if args.round_two and first_round_penalties:
            first_round_penalties = remap_penalty_edges(first_round_penalties, old_to_new_guest_id)
        
        # 自动检测人数
        num_males, num_females = detect_guest_counts(data)
        print_flush(f"📊 检测到嘉宾人数: {num_males}男 + {num_females}女 = {num_males + num_females}人")
        
        # 计算分组信息
        total_people = num_males + num_females
        if args.pairing_mode:
            expected_pairs = min(num_males, num_females)
            diff = abs(num_males - num_females)
            if total_people % 2 == 1 and diff == 1:
                print_flush(f"🔗 配对模式: 将生成{expected_pairs}组（其中1组三人，其余1v1）")
            else:
                print_flush(f"🔗 配对模式: 将生成{expected_pairs}对1v1配对")
        else:
            num_groups = (total_people + args.group_size - 1) // args.group_size  # 向上取整
            print_flush(f"👥 分组模式: 将生成{num_groups}组，每组最多{args.group_size}人")
        
        # 根据出席情况自动放宽2男2女约束
        effective_two_by_two = args.two_by_two
        if args.two_by_two and not args.pairing_mode:
            if args.group_size % 2 != 0:
                if args.strict_two_by_two:
                    print(f"❌ strict-two-by-two 开启时，每组人数必须为偶数，当前 group-size={args.group_size}")
                    return
                print(f"⚠️  group-size={args.group_size} 为奇数，自动放宽2男2女硬约束")
                effective_two_by_two = False
            elif num_males != num_females:
                if args.strict_two_by_two:
                    print(f"❌ strict-two-by-two 开启时，男女人数必须相等；当前为 {num_males}:{num_females}")
                    return
                print(f"⚠️  当前男女人数不相等（{num_males}:{num_females}），自动放宽2男2女硬约束")
                effective_two_by_two = False

        # 解析特权嘉宾（支持姓名或ID）
        privileged_guests = set()
        if args.privileged_guests:
            raw_privileged_tokens = [g.strip() for g in args.privileged_guests.split(',') if g.strip()]
            privileged_raw_ids, privileged_parse_warnings = resolve_guest_tokens(
                raw_privileged_tokens, present_guest_ids_raw, name_to_guest_ids
            )
            for warning in privileged_parse_warnings:
                print(f"⚠️  特权嘉宾解析: {warning}")

            privileged_guests = convert_guest_ids_to_internal(privileged_raw_ids, old_to_new_guest_id)
            
            if privileged_guests:
                print_flush(f"🌟 设置特权嘉宾: {', '.join(sorted(privileged_guests))}（共{len(privileged_guests)}人）")
            else:
                print("⚠️  未识别到有效的特权嘉宾")
        
        # 2. 解析偏好
        if args.mode == 'ranking':
            print_flush(f"\n🔍 正在解析ranking偏好...")
            parser = RankingPreferenceParser(
                first_preference_weight=args.first_preference_weight,
                second_preference_weight=args.second_preference_weight,
                max_male_id=num_males,
                max_female_id=num_females
            )
            parse_result = parser.parse_all_preferences(data)
            
            print_flush(f"✅ 解析出 {len(parse_result.weighted_edges)} 条加权偏好边")
            
            if parse_result.warnings:
                print("⚠️  解析警告:")
                for warning in parse_result.warnings[:10]:  # 只显示前10个警告
                    print(f"   {warning}")
                if len(parse_result.warnings) > 10:
                    print(f"   ... 还有 {len(parse_result.warnings) - 10} 个警告")
            
            # 打印解析摘要
            if args.verbose:
                parser.print_parse_summary(parse_result)
                
        else:
            print_flush("\n🔍 正在解析中文偏好...")
            parser = ChinesePreferenceParser(max_male_id=num_males, max_female_id=num_females)
            parse_result = parser.parse_all_preferences(data)
            
            print_flush(f"✅ 解析出 {len(parse_result.edges)} 条有向偏好边")
            
            if parse_result.warnings:
                print("⚠️  解析警告:")
                for warning in parse_result.warnings[:10]:  # 只显示前10个警告
                    print(f"   {warning}")
                if len(parse_result.warnings) > 10:
                    print(f"   ... 还有 {len(parse_result.warnings) - 10} 个警告")
            
            # 打印解析摘要
            if args.verbose:
                parser.print_parse_summary(parse_result)
        
        # 如果是干运行模式，仅解析后退出
        if args.dry_run_parse:
            print("\n🏃 干运行模式 - 仅解析偏好，不进行求解")
            
            # 输出解析结果到JSON
            os.makedirs(args.output_dir, exist_ok=True)
            parse_output_file = os.path.join(args.output_dir, '偏好解析结果.json')
            
            import json
            parse_summary = {
                "total_edges": len(parse_result.edges),
                "warnings_count": len(parse_result.warnings),
                "edges": [{"from": src, "to": dst} for src, dst in parse_result.edges],
                "warnings": parse_result.warnings
            }
            
            with open(parse_output_file, 'w', encoding='utf-8') as f:
                json.dump(parse_summary, f, ensure_ascii=False, indent=2)
            
            print(f"💾 解析结果已保存到: {parse_output_file}")
            return
        
        # 3. 创建偏好图
        round_info = "第二轮模式" if args.round_two else "标准模式"
        print_flush(f"\n📈 正在构建偏好图...（{round_info}）")
        if args.mode == 'ranking':
            # Ranking模式：使用加权边
            graph = PreferenceGraph(
                parse_result.edges, 
                mutual_weight=args.mutual_weight,
                weighted_edges=parse_result.weighted_edges,
                first_round_penalties=first_round_penalties,
                penalty_weight=args.penalty_weight
            )
        else:
            # Text模式：使用传统的无权边
            graph = PreferenceGraph(
                parse_result.edges, 
                mutual_weight=args.mutual_weight,
                first_round_penalties=first_round_penalties,
                penalty_weight=args.penalty_weight
            )
        
        graph_stats = graph.get_graph_stats()
        print(f"✅ 偏好图构建完成:")
        print(f"   - 总边数: {graph_stats['total_edges']}")
        print(f"   - 总节点数: {graph_stats['total_nodes']}")
        print(f"   - 互相喜欢对数: {graph_stats['mutual_pairs']}")
        print(f"   - 平均出度: {graph_stats['avg_out_degree']:.1f}")
        
        # 4. 选择求解器并求解
        solution = None
        solve_info = {}
        
        start_time = time.time()
        
        if args.solver == 'auto':
            # 自动选择求解器 - 优先使用启发式（更稳定）
            print_flush("\n🤖 自动选择求解器...")
            
            # 优先使用启发式求解器（更稳定）
            print_flush("🔧 使用启发式求解器...")
            heur_solver = HeuristicSolver(
                graph, effective_two_by_two, args.seed, args.max_iter, 
                pairing_mode=args.pairing_mode,
                num_males=num_males, num_females=num_females, group_size=args.group_size,
                privileged_guests=privileged_guests
            )
            solution, solve_info = heur_solver.solve(
                algorithm=args.heur_algorithm,
                initial_strategy='greedy',
                num_restarts=args.num_restarts,
                callback=progress_callback
            )
            solve_info['solver_used'] = 'Heuristic'
            
            # 如果启发式失败，尝试ILP
            if solution is None:
                print("🔧 启发式求解失败，尝试ILP求解器...")
                if not args.pairing_mode:  # ILP求解器暂不支持配对模式
                    try:
                        ilp_solver = ILPSolver(graph, effective_two_by_two, args.ilp_time_limit,
                                             num_males=num_males, num_females=num_females, group_size=args.group_size,
                                             privileged_guests=privileged_guests)
                        if ilp_solver.pulp_available:
                            solution, solve_info = ilp_solver.solve_with_callback(progress_callback)
                            solve_info['solver_used'] = 'ILP (fallback)'
                        else:
                            print("ILP求解器不可用")
                    except Exception as e:
                        print("ILP求解器出错: " + str(e))
                        # 保持启发式的结果
                else:
                    print("配对模式暂不支持ILP求解器")
        
        elif args.solver == 'ilp':
            print("\n🎯 使用ILP求解器...")
            if args.pairing_mode:
                print("❌ ILP求解器不支持配对模式，自动切换到启发式求解器")
                heur_solver = HeuristicSolver(
                    graph, effective_two_by_two, args.seed, args.max_iter,
                    pairing_mode=args.pairing_mode,
                    num_males=num_males, num_females=num_females, group_size=args.group_size,
                    privileged_guests=privileged_guests
                )
                solution, solve_info = heur_solver.solve(
                    algorithm=args.heur_algorithm,
                    initial_strategy='greedy', 
                    num_restarts=args.num_restarts,
                    callback=progress_callback
                )
                solve_info['solver_used'] = 'Heuristic (Pairing mode)'
            else:
                try:
                    ilp_solver = ILPSolver(graph, effective_two_by_two, args.ilp_time_limit,
                                         num_males=num_males, num_females=num_females, group_size=args.group_size,
                                         privileged_guests=privileged_guests)
                    solution, solve_info = ilp_solver.solve_with_callback(progress_callback)
                    solve_info['solver_used'] = 'ILP'
                except Exception as e:
                    print("❌ ILP求解器出错: " + str(e))
                    print("🔧 自动回退到启发式求解器...")
                    heur_solver = HeuristicSolver(
                        graph, effective_two_by_two, args.seed, args.max_iter,
                        pairing_mode=args.pairing_mode,
                        num_males=num_males, num_females=num_females, group_size=args.group_size,
                        privileged_guests=privileged_guests
                    )
                    solution, solve_info = heur_solver.solve(
                        algorithm=args.heur_algorithm,
                        initial_strategy='greedy', 
                        num_restarts=args.num_restarts,
                        callback=progress_callback
                    )
                    solve_info['solver_used'] = 'Heuristic (ILP failed)'
        
        else:  # heuristic
            print("\n🎯 使用启发式求解器...")
            heur_solver = HeuristicSolver(
                graph, effective_two_by_two, args.seed, args.max_iter,
                pairing_mode=args.pairing_mode,
                num_males=num_males, num_females=num_females, group_size=args.group_size,
                privileged_guests=privileged_guests
            )
            solution, solve_info = heur_solver.solve(
                algorithm=args.heur_algorithm,
                initial_strategy='greedy',
                num_restarts=args.num_restarts,
                callback=progress_callback
            )
            solve_info['solver_used'] = 'Heuristic'
        
        solve_time = time.time() - start_time
        
        # 5. 处理求解结果
        if solution is None:
            print(f"\n❌ 求解失败: {solve_info.get('message', '未知错误')}")
            print(f"求解信息: {solve_info}")
            return
        
        print_flush(f"\n✅ 求解成功! 用时 {solve_time:.2f} 秒")
        print_flush(f"求解器: {solve_info.get('solver_used', 'Unknown')}")
        
        if args.verbose:
            print(f"求解详情: {solve_info}")
        
        # 6. 验证分组方案
        is_valid, validation_errors = validate_grouping(solution, effective_two_by_two, args.pairing_mode,
                                                       num_males, num_females, args.group_size)
        if not is_valid:
            print(f"\n⚠️  分组方案验证失败:")
            for error in validation_errors:
                print(f"   {error}")
        else:
            print(f"\n✅ 分组方案验证通过")
        
        # 7. 验证特权嘉宾约束
        if privileged_guests and solution:
            print(f"\n🌟 正在验证特权嘉宾约束...")
            privileged_satisfied = {}
            privileged_violations = []
            
            for privileged_guest in privileged_guests:
                # 找到该特权嘉宾所在的组
                guest_group = None
                for group_idx, group in enumerate(solution):
                    if privileged_guest in group:
                        guest_group = group
                        break
                
                if guest_group is None:
                    privileged_violations.append(f"{privileged_guest}: 未找到所在组")
                    privileged_satisfied[privileged_guest] = False
                    continue
                
                # 检查是否与喜欢的人同组
                liked_persons_in_group = []
                for other_person in guest_group:
                    if other_person != privileged_guest and (privileged_guest, other_person) in graph.edges:
                        liked_persons_in_group.append(other_person)
                
                if liked_persons_in_group:
                    privileged_satisfied[privileged_guest] = True
                    print(f"   ✅ {privileged_guest} 与喜欢的人 {', '.join(liked_persons_in_group)} 同组")
                else:
                    privileged_satisfied[privileged_guest] = False
                    privileged_violations.append(f"{privileged_guest}: 未与喜欢的人同组")
                    print(f"   ❌ {privileged_guest} 未与任何喜欢的人同组")
            
            satisfied_count = sum(privileged_satisfied.values())
            total_privileged = len(privileged_guests)
            print(f"\n🌟 特权嘉宾约束满足情况: {satisfied_count}/{total_privileged} ({satisfied_count/total_privileged*100:.1f}%)")
            
            if privileged_violations:
                print("⚠️  未满足约束的特权嘉宾:")
                for violation in privileged_violations:
                    print(f"   • {violation}")
        
        # 8. 计算统计信息
        print(f"\n📊 正在计算统计信息...")
        stats = graph.calculate_overall_score(solution)
        
        # 9. 显示结果
        print(f"\n🎉 === 分组结果 ===")
        graph.print_overall_stats(stats)
        
        # 9. 导出结果
        print(f"\n💾 正在导出结果...")
        os.makedirs(args.output_dir, exist_ok=True)

        # 构建展示用姓名映射（内部ID -> 姓名 / 原始ID）
        guest_display_map = {}
        for internal_guest_id, old_guest_id in new_to_old_guest_id.items():
            guest_name = guest_id_to_name.get(old_guest_id)
            if not guest_name:
                continue
            if old_guest_id != internal_guest_id:
                guest_display_map[internal_guest_id] = f"{guest_name}/原{old_guest_id}"
            else:
                guest_display_map[internal_guest_id] = guest_name
        
        # 文件名后缀
        if args.pairing_mode:
            file_suffix = "_双人配对"
        elif args.round_two:
            file_suffix = "_第二轮"
        else:
            file_suffix = "_第一轮"
        
        # 准备特权嘉宾信息
        privileged_info = None
        if privileged_guests:
            privileged_info = {
                "privileged_guests": list(privileged_guests),
                "satisfied_count": satisfied_count if 'satisfied_count' in locals() else 0,
                "satisfaction_rate": (satisfied_count/len(privileged_guests)*100) if 'satisfied_count' in locals() and len(privileged_guests) > 0 else 0
            }
        
        # 导出JSON
        json_file = os.path.join(args.output_dir, f'安排结果{file_suffix}.json')
        io_handler.export_results_to_json(stats, json_file, privileged_info=privileged_info, guest_display_map=guest_display_map)
        print(f"✅ JSON结果已保存: {json_file}")
        
        # 导出CSV
        csv_file = os.path.join(args.output_dir, f'安排结果{file_suffix}.csv')
        io_handler.export_results_to_csv(stats, csv_file, privileged_info=privileged_info, guest_display_map=guest_display_map)
        print(f"✅ CSV结果已保存: {csv_file}")
        
        # 导出Excel（可选）
        if args.export_xlsx:
            excel_file = os.path.join(args.output_dir, f'安排结果{file_suffix}.xlsx')
            io_handler.export_results_to_excel(stats, excel_file, privileged_info=privileged_info, guest_display_map=guest_display_map)
            print(f"✅ Excel结果已保存: {excel_file}")
        
        print(f"\n🎊 任务完成! 总用时 {time.time() - start_time:.2f} 秒")
        
    except KeyboardInterrupt:
        print(f"\n\n⏹️  用户中断程序")
        sys.exit(1)
    
    except Exception as e:
        print(f"\n❌ 程序异常: {str(e)}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
