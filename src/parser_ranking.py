# -*- coding: utf-8 -*-
"""
Ranking格式偏好解析器
用于解析新的ranking格式输入数据（对象1ID, 对象2ID）
"""

from typing import List, Tuple, Dict, Set, Optional
from dataclasses import dataclass
import warnings


@dataclass
class RankingParseResult:
    """Ranking解析结果"""
    weighted_edges: List[Tuple[str, str, float]]  # (src, dst, weight) 加权边列表
    edges: List[Tuple[str, str]]  # 传统的无权边列表（兼容性）
    warnings: List[str]  # 解析警告
    raw_data: List[Dict]  # 原始数据记录


class RankingPreferenceParser:
    """Ranking偏好解析器"""
    
    def __init__(self, first_preference_weight: float = 2.0, second_preference_weight: float = 1.0, 
                 max_male_id: int = 12, max_female_id: int = 12):
        """
        初始化Ranking解析器
        
        Args:
            first_preference_weight: 第一偏好的权重
            second_preference_weight: 第二偏好的权重
            max_male_id: 最大男性ID编号
            max_female_id: 最大女性ID编号
        """
        self.first_preference_weight = first_preference_weight
        self.second_preference_weight = second_preference_weight
        self.max_male_id = max_male_id
        self.max_female_id = max_female_id
    
    def parse_all_preferences(self, data: List[Dict]) -> RankingParseResult:
        """
        解析所有ranking偏好数据
        
        Args:
            data: 包含ranking偏好数据的字典列表，每个字典包含：
                  - '嘉宾类型': '男' 或 '女'
                  - '编号': 数字ID
                  - '对象1ID': 第一偏好的异性ID
                  - '对象2ID': 第二偏好的异性ID
        
        Returns:
            RankingParseResult: 解析结果
        """
        all_weighted_edges = []
        all_edges = []
        all_warnings = []
        
        for i, row in enumerate(data):
            try:
                # 获取基本信息
                guest_type = row.get('嘉宾类型', '').strip()
                guest_id = row.get('编号', '')
                obj1_id = row.get('对象1ID', '')  # 第一偏好
                obj2_id = row.get('对象2ID', '')  # 第二偏好
                
                # 验证嘉宾类型
                if not guest_type or guest_type not in ['男', '女']:
                    all_warnings.append(f"第{i+1}行: 嘉宾类型无效: {guest_type}")
                    continue
                
                # 验证嘉宾编号
                if not isinstance(guest_id, (int, str)) or not str(guest_id).isdigit():
                    all_warnings.append(f"第{i+1}行: 编号无效: {guest_id}")
                    continue
                
                guest_id = int(guest_id)
                max_id = self.max_male_id if guest_type == '男' else self.max_female_id
                if not (1 <= guest_id <= max_id):
                    all_warnings.append(f"第{i+1}行: 编号超出范围: {guest_id} (最大{guest_type}ID: {max_id})")
                    continue
                
                # 构建主体ID
                subject_prefix = 'M' if guest_type == '男' else 'F'
                subject_id = f"{subject_prefix}{guest_id}"
                
                # 推断目标性别前缀
                target_prefix = 'F' if guest_type == '男' else 'M'
                
                # 处理第一偏好
                target1_id = None
                if obj1_id and str(obj1_id).strip():
                    obj1_str = str(obj1_id).strip()
                    
                    # 检查是否已经是完整的参与者ID格式（如M11, F3等）
                    if obj1_str.startswith(('M', 'F')) and obj1_str[1:].isdigit():
                        target_num = int(obj1_str[1:])
                        target_gender = 'M' if obj1_str.startswith('M') else 'F'
                        max_target_id = self.max_male_id if target_gender == 'M' else self.max_female_id
                        
                        if 1 <= target_num <= max_target_id:
                            # 检查性别是否正确（男嘉宾只能选女嘉宾）
                            if guest_type == '男' and obj1_str.startswith('F'):
                                target1_id = obj1_str
                            elif guest_type == '女' and obj1_str.startswith('M'):
                                target1_id = obj1_str
                            else:
                                all_warnings.append(f"第{i+1}行: 对象1ID性别不匹配: {guest_type}嘉宾不能选择{obj1_str}")
                        else:
                            all_warnings.append(f"第{i+1}行: 对象1ID编号超出范围: {obj1_str} (最大{target_gender}ID: {max_target_id})")
                    else:
                        # 尝试作为纯数字ID处理
                        try:
                            obj1_num = int(obj1_str)
                            max_target_id = self.max_female_id if target_prefix == 'F' else self.max_male_id
                            if 1 <= obj1_num <= max_target_id:
                                target1_id = f"{target_prefix}{obj1_num}"
                            else:
                                all_warnings.append(f"第{i+1}行: 对象1ID超出范围: {obj1_num} (最大{target_prefix}ID: {max_target_id})")
                        except (ValueError, TypeError):
                            all_warnings.append(f"第{i+1}行: 对象1ID格式错误: {obj1_str}")
                    
                    # 如果解析成功，添加边
                    if target1_id:
                        if subject_id != target1_id:  # 避免自我指向
                            all_weighted_edges.append((subject_id, target1_id, self.first_preference_weight))
                            all_edges.append((subject_id, target1_id))
                        else:
                            all_warnings.append(f"第{i+1}行: 忽略自我指向: {subject_id} -> {target1_id}")
                
                # 处理第二偏好
                if obj2_id and str(obj2_id).strip():
                    obj2_str = str(obj2_id).strip()
                    target2_id = None
                    
                    # 检查是否已经是完整的参与者ID格式（如M11, F3等）
                    if obj2_str.startswith(('M', 'F')) and obj2_str[1:].isdigit():
                        target_num = int(obj2_str[1:])
                        target_gender = 'M' if obj2_str.startswith('M') else 'F'
                        max_target_id = self.max_male_id if target_gender == 'M' else self.max_female_id
                        
                        if 1 <= target_num <= max_target_id:
                            # 检查性别是否正确（男嘉宾只能选女嘉宾）
                            if guest_type == '男' and obj2_str.startswith('F'):
                                target2_id = obj2_str
                            elif guest_type == '女' and obj2_str.startswith('M'):
                                target2_id = obj2_str
                            else:
                                all_warnings.append(f"第{i+1}行: 对象2ID性别不匹配: {guest_type}嘉宾不能选择{obj2_str}")
                        else:
                            all_warnings.append(f"第{i+1}行: 对象2ID编号超出范围: {obj2_str} (最大{target_gender}ID: {max_target_id})")
                    else:
                        # 尝试作为纯数字ID处理
                        try:
                            obj2_num = int(obj2_str)
                            max_target_id = self.max_female_id if target_prefix == 'F' else self.max_male_id
                            if 1 <= obj2_num <= max_target_id:
                                target2_id = f"{target_prefix}{obj2_num}"
                            else:
                                all_warnings.append(f"第{i+1}行: 对象2ID超出范围: {obj2_num} (最大{target_prefix}ID: {max_target_id})")
                        except (ValueError, TypeError):
                            all_warnings.append(f"第{i+1}行: 对象2ID格式错误: {obj2_str}")
                    
                    # 如果解析成功，添加边
                    if target2_id:
                        if subject_id != target2_id:  # 避免自我指向
                            # 避免重复边（如果对象1和对象2相同）
                            if target1_id != target2_id:
                                all_weighted_edges.append((subject_id, target2_id, self.second_preference_weight))
                                all_edges.append((subject_id, target2_id))
                            else:
                                all_warnings.append(f"第{i+1}行: 对象1和对象2相同，忽略重复: {target2_id}")
                        else:
                            all_warnings.append(f"第{i+1}行: 忽略自我指向: {subject_id} -> {target2_id}")
                
            except Exception as e:
                all_warnings.append(f"第{i+1}行: 处理异常: {str(e)}")
                continue
        
        return RankingParseResult(
            weighted_edges=all_weighted_edges,
            edges=all_edges,
            warnings=all_warnings,
            raw_data=data
        )
    
    def print_parse_summary(self, result: RankingParseResult):
        """打印解析摘要"""
        print(f"=== Ranking解析摘要 ===")
        print(f"加权边数: {len(result.weighted_edges)}")
        print(f"普通边数: {len(result.edges)}")
        print(f"警告数量: {len(result.warnings)}")
        
        if result.warnings:
            print(f"\n警告信息:")
            for warning in result.warnings:
                print(f"  {warning}")
        
        print(f"\n解析出的加权偏好边:")
        # 按权重分组显示
        first_prefs = [e for e in result.weighted_edges if e[2] == self.first_preference_weight]
        second_prefs = [e for e in result.weighted_edges if e[2] == self.second_preference_weight]
        
        print(f"第一偏好 ({len(first_prefs)} 条，权重 {self.first_preference_weight}):")
        for src, dst, weight in first_prefs:
            print(f"  {src} -> {dst} (权重: {weight})")
        
        print(f"\n第二偏好 ({len(second_prefs)} 条，权重 {self.second_preference_weight}):")
        for src, dst, weight in second_prefs:
            print(f"  {src} -> {dst} (权重: {weight})")


def demo_ranking_parser():
    """演示Ranking解析器功能"""
    # 测试数据
    test_data = [
        {'嘉宾类型': '男', '编号': 1, '对象1ID': 3, '对象2ID': 6},
        {'嘉宾类型': '男', '编号': 2, '对象1ID': 1, '对象2ID': 5},
        {'嘉宾类型': '女', '编号': 1, '对象1ID': 4, '对象2ID': 2},
        {'嘉宾类型': '女', '编号': 3, '对象1ID': 1, '对象2ID': 10},
    ]
    
    parser = RankingPreferenceParser(first_preference_weight=2.0, second_preference_weight=1.0)
    result = parser.parse_all_preferences(test_data)
    parser.print_parse_summary(result)
    
    return result


if __name__ == "__main__":
    demo_ranking_parser()