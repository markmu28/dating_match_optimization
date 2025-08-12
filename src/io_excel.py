# -*- coding: utf-8 -*-
"""
Excel/CSV/JSON IO 处理模块
用于读取偏好数据和导出分组结果
"""

import pandas as pd
import json
import os
from typing import List, Dict, Optional, Tuple, Set
from pathlib import Path
from .graph import OverallStats


class DataIO:
    """数据输入输出处理器"""
    
    def __init__(self):
        """初始化数据IO处理器"""
        self.supported_extensions = {'.xlsx', '.xls', '.csv'}
    
    def read_ranking_from_excel(self, file_path: str, sheet_name: str = '偏好') -> Tuple[List[Dict], List[str]]:
        """
        从Excel文件读取ranking格式偏好数据（对象1ID, 对象2ID）
        
        Args:
            file_path: Excel文件路径
            sheet_name: sheet名称，默认为'偏好'
            
        Returns:
            (data, warnings): 数据列表和警告信息
        """
        warnings = []
        
        try:
            # 检查文件存在性
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"文件不存在: {file_path}")
            
            # 读取Excel文件
            if file_path.lower().endswith(('.xlsx', '.xls')):
                try:
                    df = pd.read_excel(file_path, sheet_name=sheet_name)
                except ValueError as e:
                    if 'sheet' in str(e).lower():
                        warnings.append(f"Sheet '{sheet_name}' 不存在，尝试读取第一个sheet")
                        df = pd.read_excel(file_path, sheet_name=0)
                    else:
                        raise e
                        
            elif file_path.lower().endswith('.csv'):
                # CSV文件处理
                try:
                    df = pd.read_csv(file_path, encoding='utf-8')
                except UnicodeDecodeError:
                    try:
                        df = pd.read_csv(file_path, encoding='gb2312')
                        warnings.append("使用GB2312编码读取CSV文件")
                    except UnicodeDecodeError:
                        df = pd.read_csv(file_path, encoding='gbk')
                        warnings.append("使用GBK编码读取CSV文件")
            else:
                raise ValueError(f"不支持的文件格式: {file_path}")
            
            # 检查和标准化列名 - ranking格式
            expected_columns = ['嘉宾类型', '编号', '对象1ID', '对象2ID']
            actual_columns = df.columns.tolist()
            
            # 尝试匹配列名
            column_mapping = {}
            for expected in expected_columns:
                found = False
                for actual in actual_columns:
                    if expected in str(actual) or str(actual) in expected:
                        column_mapping[actual] = expected
                        found = True
                        break
                
                if not found:
                    # 尝试按位置匹配
                    if len(actual_columns) >= len(expected_columns):
                        idx = expected_columns.index(expected)
                        if idx < len(actual_columns):
                            column_mapping[actual_columns[idx]] = expected
                            warnings.append(f"按位置匹配列: {actual_columns[idx]} -> {expected}")
            
            # 重命名列
            if column_mapping:
                df = df.rename(columns=column_mapping)
            
            # 检查必需列
            missing_columns = set(expected_columns) - set(df.columns)
            if missing_columns:
                raise ValueError(f"缺少必需列: {missing_columns}")
            
            # 删除空行
            original_len = len(df)
            df = df.dropna(how='all')
            if len(df) < original_len:
                warnings.append(f"删除了 {original_len - len(df)} 个空行")
            
            # 转换为字典列表
            data = df[expected_columns].to_dict('records')
            
            # 清理数据
            cleaned_data = []
            for i, row in enumerate(data):
                # 检查数据完整性
                if pd.isna(row['嘉宾类型']) or pd.isna(row['编号']):
                    warnings.append(f"第{i+2}行基本信息不完整，已跳过")
                    continue
                
                # 类型转换
                try:
                    row['嘉宾类型'] = str(row['嘉宾类型']).strip()
                    row['编号'] = int(float(row['编号']))  # 支持Excel中的浮点数格式
                    
                    # 对象ID可以为空，如果不为空则保持原始格式（数字或参与者ID如M11、F3）
                    for col in ['对象1ID', '对象2ID']:
                        if pd.isna(row[col]) or str(row[col]).strip() == '':
                            row[col] = ''
                        else:
                            col_str = str(row[col]).strip()
                            # 检查是否是参与者ID格式（如M11, F3）或纯数字
                            if col_str.startswith(('M', 'F')) and col_str[1:].isdigit():
                                # 参与者ID格式，直接保留
                                row[col] = col_str
                            else:
                                # 尝试作为数字处理
                                try:
                                    row[col] = int(float(col_str))
                                except (ValueError, TypeError):
                                    # 如果不能转换为数字，保留原始字符串给解析器处理
                                    row[col] = col_str
                    
                    cleaned_data.append(row)
                except (ValueError, TypeError) as e:
                    warnings.append(f"第{i+2}行数据格式错误: {str(e)}")
                    continue
            
            if not cleaned_data:
                raise ValueError("没有有效的数据行")
            
            return cleaned_data, warnings
            
        except Exception as e:
            raise Exception(f"读取ranking格式文件失败: {str(e)}")

    def read_preferences_from_excel(self, file_path: str, sheet_name: str = '偏好') -> Tuple[List[Dict], List[str]]:
        """
        从Excel文件读取偏好数据
        
        Args:
            file_path: Excel文件路径
            sheet_name: sheet名称，默认为'偏好'
            
        Returns:
            (data, warnings): 数据列表和警告信息
        """
        warnings = []
        
        try:
            # 检查文件存在性
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"文件不存在: {file_path}")
            
            # 读取Excel文件
            if file_path.lower().endswith(('.xlsx', '.xls')):
                try:
                    df = pd.read_excel(file_path, sheet_name=sheet_name)
                except ValueError as e:
                    if 'sheet' in str(e).lower():
                        warnings.append(f"Sheet '{sheet_name}' 不存在，尝试读取第一个sheet")
                        df = pd.read_excel(file_path, sheet_name=0)
                    else:
                        raise e
                        
            elif file_path.lower().endswith('.csv'):
                # CSV文件处理
                try:
                    df = pd.read_csv(file_path, encoding='utf-8')
                except UnicodeDecodeError:
                    try:
                        df = pd.read_csv(file_path, encoding='gb2312')
                        warnings.append("使用GB2312编码读取CSV文件")
                    except UnicodeDecodeError:
                        df = pd.read_csv(file_path, encoding='gbk')
                        warnings.append("使用GBK编码读取CSV文件")
            else:
                raise ValueError(f"不支持的文件格式: {file_path}")
            
            # 检查和标准化列名
            expected_columns = ['嘉宾类型', '编号', '偏好描述']
            actual_columns = df.columns.tolist()
            
            # 尝试匹配列名
            column_mapping = {}
            for expected in expected_columns:
                found = False
                for actual in actual_columns:
                    if expected in str(actual) or str(actual) in expected:
                        column_mapping[actual] = expected
                        found = True
                        break
                
                if not found:
                    # 尝试按位置匹配
                    if len(actual_columns) >= len(expected_columns):
                        idx = expected_columns.index(expected)
                        if idx < len(actual_columns):
                            column_mapping[actual_columns[idx]] = expected
                            warnings.append(f"按位置匹配列: {actual_columns[idx]} -> {expected}")
            
            # 重命名列
            if column_mapping:
                df = df.rename(columns=column_mapping)
            
            # 检查必需列
            missing_columns = set(expected_columns) - set(df.columns)
            if missing_columns:
                raise ValueError(f"缺少必需列: {missing_columns}")
            
            # 删除空行
            original_len = len(df)
            df = df.dropna(how='all')
            if len(df) < original_len:
                warnings.append(f"删除了 {original_len - len(df)} 个空行")
            
            # 转换为字典列表
            data = df[expected_columns].to_dict('records')
            
            # 清理数据
            cleaned_data = []
            for i, row in enumerate(data):
                # 检查数据完整性
                if pd.isna(row['嘉宾类型']) or pd.isna(row['编号']) or pd.isna(row['偏好描述']):
                    warnings.append(f"第{i+2}行数据不完整，已跳过")
                    continue
                
                # 类型转换
                try:
                    row['嘉宾类型'] = str(row['嘉宾类型']).strip()
                    row['编号'] = int(float(row['编号']))  # 支持Excel中的浮点数格式
                    row['偏好描述'] = str(row['偏好描述']).strip()
                    cleaned_data.append(row)
                except (ValueError, TypeError) as e:
                    warnings.append(f"第{i+2}行数据格式错误: {str(e)}")
                    continue
            
            if not cleaned_data:
                raise ValueError("没有有效的数据行")
            
            return cleaned_data, warnings
            
        except Exception as e:
            raise Exception(f"读取文件失败: {str(e)}")
    
    def export_results_to_json(self, 
                              stats: OverallStats, 
                              output_file: str,
                              include_detailed_stats: bool = True) -> None:
        """
        导出结果到JSON文件
        
        Args:
            stats: 整体统计信息
            output_file: 输出文件路径
            include_detailed_stats: 是否包含详细统计
        """
        try:
            # 构建输出数据
            result_data = {
                "meta": {
                    "total_groups": len(stats.group_scores),
                    "total_score": stats.total_score,
                    "avg_group_score": stats.avg_group_score,
                    "total_single_preferences": stats.total_single_prefs,
                    "total_mutual_preferences": stats.total_mutual_prefs,
                    "single_hit_rate": stats.hit_rate_single,
                    "mutual_hit_rate": stats.hit_rate_mutual
                },
                "groups": []
            }
            
            for group_score in stats.group_scores:
                group_data = {
                    "group_id": group_score.group_id,
                    "members": group_score.members,
                    "total_score": group_score.total_score,
                    "single_preferences_count": group_score.single_count,
                    "mutual_preferences_count": group_score.mutual_count
                }
                
                if include_detailed_stats:
                    group_data["single_preferences"] = [
                        {"from": src, "to": dst} for src, dst in group_score.single_preferences
                    ]
                    group_data["mutual_preferences"] = [
                        {"members": list(pair)} for pair in group_score.mutual_preferences
                    ]
                
                result_data["groups"].append(group_data)
            
            # 确保输出目录存在
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            
            # 写入JSON文件
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result_data, f, ensure_ascii=False, indent=2)
            
        except Exception as e:
            raise Exception(f"导出JSON失败: {str(e)}")
    
    def export_results_to_csv(self, stats: OverallStats, output_file: str) -> None:
        """
        导出结果到CSV文件
        
        Args:
            stats: 整体统计信息
            output_file: 输出文件路径
        """
        try:
            # 构建CSV数据
            csv_data = []
            
            for group_score in stats.group_scores:
                # 构建成员字符串
                members_str = ', '.join(group_score.members)
                
                # 构建偏好关系字符串
                single_prefs_str = '; '.join([f"{src}→{dst}" for src, dst in group_score.single_preferences])
                mutual_prefs_str = '; '.join([f"{pair[0]}↔{pair[1]}" for pair in group_score.mutual_preferences])
                
                csv_data.append({
                    '组号': group_score.group_id,
                    '成员': members_str,
                    '总得分': group_score.total_score,
                    '单向喜欢数': group_score.single_count,
                    '互相喜欢数': group_score.mutual_count,
                    '单向喜欢详情': single_prefs_str if single_prefs_str else '无',
                    '互相喜欢详情': mutual_prefs_str if mutual_prefs_str else '无'
                })
            
            # 添加汇总行
            csv_data.append({
                '组号': '汇总',
                '成员': f'总计 {len(stats.group_scores)} 组',
                '总得分': stats.total_score,
                '单向喜欢数': stats.total_single_prefs,
                '互相喜欢数': stats.total_mutual_prefs,
                '单向喜欢详情': f'命中率: {stats.hit_rate_single:.1%}',
                '互相喜欢详情': f'命中率: {stats.hit_rate_mutual:.1%}'
            })
            
            # 创建DataFrame并导出
            df = pd.DataFrame(csv_data)
            
            # 确保输出目录存在
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            
            df.to_csv(output_file, index=False, encoding='utf-8-sig')  # 使用BOM确保中文正确显示
            
        except Exception as e:
            raise Exception(f"导出CSV失败: {str(e)}")
    
    def export_results_to_excel(self, stats: OverallStats, output_file: str) -> None:
        """
        导出结果到Excel文件
        
        Args:
            stats: 整体统计信息
            output_file: 输出文件路径
        """
        try:
            # 创建Excel writer
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            
            with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
                # Sheet 1: 分组结果汇总
                summary_data = []
                for group_score in stats.group_scores:
                    summary_data.append({
                        '组号': group_score.group_id,
                        '成员': ', '.join(group_score.members),
                        '总得分': group_score.total_score,
                        '单向喜欢数': group_score.single_count,
                        '互相喜欢数': group_score.mutual_count
                    })
                
                df_summary = pd.DataFrame(summary_data)
                df_summary.to_excel(writer, sheet_name='分组汇总', index=False)
                
                # Sheet 2: 详细偏好关系
                details_data = []
                for group_score in stats.group_scores:
                    # 单向喜欢
                    for src, dst in group_score.single_preferences:
                        details_data.append({
                            '组号': group_score.group_id,
                            '关系类型': '单向喜欢',
                            '源': src,
                            '目标': dst,
                            '得分': 1.0
                        })
                    
                    # 互相喜欢
                    for pair in group_score.mutual_preferences:
                        details_data.append({
                            '组号': group_score.group_id,
                            '关系类型': '互相喜欢',
                            '源': pair[0],
                            '目标': pair[1],
                            '得分': stats.group_scores[0].total_score / max(1, len(stats.group_scores[0].single_preferences + stats.group_scores[0].mutual_preferences))  # 这里简化处理
                        })
                
                if details_data:
                    df_details = pd.DataFrame(details_data)
                    df_details.to_excel(writer, sheet_name='偏好详情', index=False)
                
                # Sheet 3: 整体统计
                stats_data = [
                    {'指标': '总得分', '数值': stats.total_score},
                    {'指标': '平均每组得分', '数值': stats.avg_group_score},
                    {'指标': '单向喜欢命中数', '数值': stats.total_single_prefs},
                    {'指标': '互相喜欢命中数', '数值': stats.total_mutual_prefs},
                    {'指标': '单向喜欢命中率', '数值': f"{stats.hit_rate_single:.1%}"},
                    {'指标': '互相喜欢命中率', '数值': f"{stats.hit_rate_mutual:.1%}"},
                ]
                
                df_stats = pd.DataFrame(stats_data)
                df_stats.to_excel(writer, sheet_name='整体统计', index=False)
            
        except Exception as e:
            raise Exception(f"导出Excel失败: {str(e)}")
    
    def create_sample_excel(self, output_file: str) -> None:
        """
        创建示例Excel文件
        
        Args:
            output_file: 输出文件路径
        """
        try:
            # 示例数据
            sample_data = [
                {'嘉宾类型': '男', '编号': 1, '偏好描述': '1号男嘉宾喜欢3号、6号和9号女嘉宾。'},
                {'嘉宾类型': '男', '编号': 2, '偏好描述': '2号男嘉宾偏好1号、5号和8号女嘉宾。'},
                {'嘉宾类型': '男', '编号': 3, '偏好描述': '3号男嘉宾对2号和4号女嘉宾有好感。'},
                {'嘉宾类型': '女', '编号': 1, '偏好描述': '1号女嘉宾喜欢4号和2号男嘉宾。'},
                {'嘉宾类型': '女', '编号': 2, '偏好描述': '2号女嘉宾偏好6号、10号、3号男嘉宾。'},
                {'嘉宾类型': '女', '编号': 3, '偏好描述': '3号女嘉宾对1号和10号男嘉宾有好感。'}
            ]
            
            df = pd.DataFrame(sample_data)
            
            # 确保输出目录存在
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            
            with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='偏好', index=False)
                
                # 添加说明sheet
                instructions = pd.DataFrame([
                    {'说明': '本文件为相亲活动偏好数据示例'},
                    {'说明': ''},
                    {'说明': '列说明:'},
                    {'说明': '嘉宾类型: 男 或 女'},
                    {'说明': '编号: 1-12 的数字'},
                    {'说明': '偏好描述: 中文自然语言描述偏好'},
                    {'说明': ''},
                    {'说明': '支持的表达方式:'},
                    {'说明': '喜欢、偏好、中意、最想认识、希望同组、对...有好感、想和...同组'},
                    {'说明': ''},
                    {'说明': '支持的连接词:'},
                    {'说明': '和、或、、（顿号）、，（逗号）、以及、还有、与'}
                ])
                
                instructions.to_excel(writer, sheet_name='使用说明', index=False)
            
        except Exception as e:
            raise Exception(f"创建示例文件失败: {str(e)}")
    
    def parse_first_round_results(self, file_path: str) -> Tuple[Set[Tuple[str, str]], List[str]]:
        """
        解析第一轮结果文件，提取单向喜欢关系
        
        Args:
            file_path: 第一轮结果JSON文件路径
            
        Returns:
            Tuple[Set[Tuple[str, str]], List[str]]: (单向喜欢关系集合, 警告信息)
        """
        warnings = []
        single_preferences = set()
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if 'groups' not in data:
                warnings.append(f"文件 {file_path} 中未找到 'groups' 字段")
                return single_preferences, warnings
            
            for group in data['groups']:
                if 'single_preferences' in group:
                    for pref in group['single_preferences']:
                        if 'from' in pref and 'to' in pref:
                            single_preferences.add((pref['from'], pref['to']))
                        else:
                            warnings.append(f"无效的单向喜欢格式: {pref}")
                            
            print(f"✅ 从第一轮结果中解析出 {len(single_preferences)} 条单向喜欢关系")
            if warnings:
                print(f"⚠️  解析警告: {len(warnings)} 条")
                
        except FileNotFoundError:
            warnings.append(f"第一轮结果文件未找到: {file_path}")
        except json.JSONDecodeError as e:
            warnings.append(f"JSON解析错误: {str(e)}")
        except Exception as e:
            warnings.append(f"解析第一轮结果时出错: {str(e)}")
            
        return single_preferences, warnings


def demo_io():
    """演示IO功能"""
    # 创建IO处理器
    io_handler = DataIO()
    
    # 创建示例文件
    sample_file = "sample_preferences.xlsx"
    print(f"创建示例文件: {sample_file}")
    io_handler.create_sample_excel(sample_file)
    
    # 读取示例文件
    print(f"\n读取示例文件:")
    try:
        data, warnings = io_handler.read_preferences_from_excel(sample_file, '偏好')
        print(f"读取到 {len(data)} 条记录")
        
        if warnings:
            print("警告信息:")
            for warning in warnings:
                print(f"  {warning}")
        
        print("\n前3条数据:")
        for i, record in enumerate(data[:3]):
            print(f"  {i+1}: {record}")
        
        return data
        
    except Exception as e:
        print(f"读取失败: {e}")
        return None


if __name__ == "__main__":
    demo_io()