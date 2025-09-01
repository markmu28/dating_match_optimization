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
from pathlib import Path

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
                       help='输入数据模式：ranking=排名ID模式（默认），text=中文描述解析')
    
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
        
        # 自动检测人数
        num_males, num_females = detect_guest_counts(data)
        print_flush(f"📊 检测到嘉宾人数: {num_males}男 + {num_females}女 = {num_males + num_females}人")
        
        # 计算分组信息
        total_people = num_males + num_females
        if args.pairing_mode:
            expected_pairs = min(num_males, num_females)
            print_flush(f"🔗 配对模式: 将生成{expected_pairs}对1v1配对")
        else:
            num_groups = (total_people + args.group_size - 1) // args.group_size  # 向上取整
            print_flush(f"👥 分组模式: 将生成{num_groups}组，每组最多{args.group_size}人")
        
        # 解析特权嘉宾
        privileged_guests = set()
        if args.privileged_guests:
            privileged_list = [g.strip().upper() for g in args.privileged_guests.split(',') if g.strip()]
            for guest in privileged_list:
                # 验证嘉宾ID格式
                if guest.startswith('M') and guest[1:].isdigit():
                    guest_id = int(guest[1:])
                    if 1 <= guest_id <= num_males:
                        privileged_guests.add(guest)
                    else:
                        print(f"⚠️  无效的特权嘉宾ID: {guest}（男性ID范围: M1-M{num_males}）")
                elif guest.startswith('F') and guest[1:].isdigit():
                    guest_id = int(guest[1:])
                    if 1 <= guest_id <= num_females:
                        privileged_guests.add(guest)
                    else:
                        print(f"⚠️  无效的特权嘉宾ID: {guest}（女性ID范围: F1-F{num_females}）")
                else:
                    print(f"⚠️  无效的特权嘉宾ID格式: {guest}（应为M1-M{num_males}或F1-F{num_females}）")
            
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
                graph, args.two_by_two, args.seed, args.max_iter, 
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
                        ilp_solver = ILPSolver(graph, args.two_by_two, args.ilp_time_limit,
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
                    graph, args.two_by_two, args.seed, args.max_iter,
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
                    ilp_solver = ILPSolver(graph, args.two_by_two, args.ilp_time_limit,
                                         num_males=num_males, num_females=num_females, group_size=args.group_size,
                                         privileged_guests=privileged_guests)
                    solution, solve_info = ilp_solver.solve_with_callback(progress_callback)
                    solve_info['solver_used'] = 'ILP'
                except Exception as e:
                    print("❌ ILP求解器出错: " + str(e))
                    print("🔧 自动回退到启发式求解器...")
                    heur_solver = HeuristicSolver(
                        graph, args.two_by_two, args.seed, args.max_iter,
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
                graph, args.two_by_two, args.seed, args.max_iter,
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
        is_valid, validation_errors = validate_grouping(solution, args.two_by_two, args.pairing_mode,
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
        io_handler.export_results_to_json(stats, json_file, privileged_info=privileged_info)
        print(f"✅ JSON结果已保存: {json_file}")
        
        # 导出CSV
        csv_file = os.path.join(args.output_dir, f'安排结果{file_suffix}.csv')
        io_handler.export_results_to_csv(stats, csv_file, privileged_info=privileged_info)
        print(f"✅ CSV结果已保存: {csv_file}")
        
        # 导出Excel（可选）
        if args.export_xlsx:
            excel_file = os.path.join(args.output_dir, f'安排结果{file_suffix}.xlsx')
            io_handler.export_results_to_excel(stats, excel_file, privileged_info=privileged_info)
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