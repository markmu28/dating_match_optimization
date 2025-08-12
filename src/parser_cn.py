# -*- coding: utf-8 -*-
"""
中文偏好解析器
用于解析中文自然语言偏好描述，提取有向喜好关系
"""

import re
import warnings
from typing import List, Tuple, Dict, Set, Optional
from dataclasses import dataclass


@dataclass
class ParseResult:
    """解析结果"""
    edges: List[Tuple[str, str]]  # 有向边列表 [(src, dst), ...]
    warnings: List[str]  # 解析警告
    raw_data: List[Dict]  # 原始数据记录


class ChinesePreferenceParser:
    """中文偏好解析器"""
    
    def __init__(self, max_male_id: int = 12, max_female_id: int = 12):
        """
        初始化解析器
        
        Args:
            max_male_id: 最大男性ID编号
            max_female_id: 最大女性ID编号
        """
        self.max_male_id = max_male_id
        self.max_female_id = max_female_id
        
        # 偏好动词词典
        self.preference_verbs = [
            '喜欢', '偏好', '中意', '最想认识', '希望同组', '对.*有好感',
            '想和.*同组', '想和.*认识', '希望遇到', '倾向于', '特别喜欢',
            '更喜欢', '最想遇到', '感兴趣', '更想认识', '希望能和.*同组',
            '想和.*同组认识'
        ]
        
        # 连接词模式
        self.connectors = ['和', '或', '、', '，', ',', '以及', '还有', '与']
        
        # 编译正则表达式
        self._compile_patterns()
    
    def _compile_patterns(self):
        """编译正则表达式模式"""
        # 主体匹配：如"1号男嘉宾"
        self.subject_pattern = re.compile(r'(\d+)号([男女])嘉宾')
        
        # 目标编号匹配：如"3号、6号和9号女嘉宾"
        self.target_pattern = re.compile(r'(\d+)号')
        
        # 性别识别
        self.gender_pattern = re.compile(r'([男女])嘉宾')
        
        # 偏好动词模式
        preference_pattern = '|'.join(self.preference_verbs)
        self.preference_pattern = re.compile(f'({preference_pattern})')
        
        # 连接词模式
        connector_pattern = '|'.join(re.escape(c) for c in self.connectors)
        self.connector_pattern = re.compile(f'({connector_pattern})')
    
    def parse_preference_text(self, text: str, subject_id: int, subject_gender: str) -> Tuple[List[str], List[str]]:
        """
        解析偏好文本
        
        Args:
            text: 偏好描述文本
            subject_id: 主体编号
            subject_gender: 主体性别 ('男' 或 '女')
            
        Returns:
            (target_ids, warnings): 目标ID列表和警告信息
        """
        warnings_list = []
        target_ids = []
        
        try:
            # 1. 检查是否包含偏好动词
            if not self.preference_pattern.search(text):
                warnings_list.append(f"未找到偏好动词: {text}")
                return target_ids, warnings_list
            
            # 2. 提取所有数字编号
            number_matches = self.target_pattern.findall(text)
            if not number_matches:
                warnings_list.append(f"未找到目标编号: {text}")
                return target_ids, warnings_list
            
            # 3. 推断目标性别
            target_gender = self._infer_target_gender(text, subject_gender)
            if not target_gender:
                warnings_list.append(f"无法推断目标性别: {text}")
                return target_ids, warnings_list
            
            # 4. 构建目标ID列表
            gender_prefix = 'M' if target_gender == '男' else 'F'
            for num in number_matches:
                target_id = f"{gender_prefix}{num}"
                target_ids.append(target_id)
            
            # 5. 验证编号范围
            valid_targets = []
            for target_id in target_ids:
                num = int(target_id[1:])
                gender_prefix = target_id[0]
                max_id = self.max_male_id if gender_prefix == 'M' else self.max_female_id
                
                if 1 <= num <= max_id:
                    valid_targets.append(target_id)
                else:
                    warnings_list.append(f"编号超出范围: {target_id} (最大{gender_prefix}{'男' if gender_prefix == 'M' else '女'}ID: {max_id})")
            
            target_ids = valid_targets
            
        except Exception as e:
            warnings_list.append(f"解析异常: {text}, 错误: {str(e)}")
            return [], warnings_list
        
        return target_ids, warnings_list
    
    def _infer_target_gender(self, text: str, subject_gender: str) -> Optional[str]:
        """推断目标性别"""
        # 直接从文本中查找性别指示
        gender_matches = self.gender_pattern.findall(text)
        if gender_matches:
            # 计算每种性别出现的次数
            gender_counts = {}
            for gender in gender_matches:
                gender_counts[gender] = gender_counts.get(gender, 0) + 1
            
            # 如果只有一种性别，直接返回
            if len(gender_counts) == 1:
                return list(gender_counts.keys())[0]
            
            # 如果有多种性别，优先选择非主体性别（目标更可能是异性）
            for gender in gender_counts:
                if gender != subject_gender:
                    return gender
            
            # 如果都是同性，返回出现次数最多的
            return max(gender_counts.items(), key=lambda x: x[1])[0]
        
        # 如果没有明确指示，根据常理推断（异性恋假设）
        if subject_gender == '男':
            return '女'
        elif subject_gender == '女':
            return '男'
        
        return None
    
    def parse_all_preferences(self, data: List[Dict]) -> ParseResult:
        """
        解析所有偏好数据
        
        Args:
            data: 包含偏好数据的字典列表，每个字典包含：
                  - '嘉宾类型': '男' 或 '女'
                  - '编号': 数字ID
                  - '偏好描述': 中文偏好文本
        
        Returns:
            ParseResult: 解析结果
        """
        all_edges = []
        all_warnings = []
        
        for i, row in enumerate(data):
            try:
                # 获取基本信息
                guest_type = row.get('嘉宾类型', '').strip()
                guest_id = row.get('编号', '')
                preference_text = row.get('偏好描述', '').strip()
                
                # 验证数据完整性
                if not guest_type or guest_type not in ['男', '女']:
                    all_warnings.append(f"第{i+1}行: 嘉宾类型无效: {guest_type}")
                    continue
                
                if not isinstance(guest_id, (int, str)) or not str(guest_id).isdigit():
                    all_warnings.append(f"第{i+1}行: 编号无效: {guest_id}")
                    continue
                
                if not preference_text:
                    all_warnings.append(f"第{i+1}行: 偏好描述为空")
                    continue
                
                guest_id = int(guest_id)
                max_id = self.max_male_id if guest_type == '男' else self.max_female_id
                if not (1 <= guest_id <= max_id):
                    all_warnings.append(f"第{i+1}行: 编号超出范围: {guest_id} (最大{guest_type}ID: {max_id})")
                    continue
                
                # 构建主体ID
                subject_prefix = 'M' if guest_type == '男' else 'F'
                subject_id = f"{subject_prefix}{guest_id}"
                
                # 解析偏好
                target_ids, parse_warnings = self.parse_preference_text(
                    preference_text, guest_id, guest_type
                )
                
                # 添加警告信息
                for warning in parse_warnings:
                    all_warnings.append(f"第{i+1}行: {warning}")
                
                # 构建有向边
                for target_id in target_ids:
                    # 避免自我指向
                    if subject_id != target_id:
                        all_edges.append((subject_id, target_id))
                    else:
                        all_warnings.append(f"第{i+1}行: 忽略自我指向: {subject_id}")
                        
            except Exception as e:
                all_warnings.append(f"第{i+1}行: 处理异常: {str(e)}")
                continue
        
        return ParseResult(
            edges=all_edges,
            warnings=all_warnings,
            raw_data=data
        )
    
    def validate_edges(self, edges: List[Tuple[str, str]]) -> Tuple[List[Tuple[str, str]], List[str]]:
        """
        验证边的有效性
        
        Args:
            edges: 有向边列表
            
        Returns:
            (valid_edges, warnings): 有效边和警告信息
        """
        valid_edges = []
        warnings_list = []
        
        # 定义有效ID集合
        valid_male_ids = {f"M{i}" for i in range(1, self.max_male_id + 1)}
        valid_female_ids = {f"F{i}" for i in range(1, self.max_female_id + 1)}
        valid_ids = valid_male_ids | valid_female_ids
        
        for src, dst in edges:
            # 检查ID有效性
            if src not in valid_ids:
                warnings_list.append(f"源ID无效: {src}")
                continue
            if dst not in valid_ids:
                warnings_list.append(f"目标ID无效: {dst}")
                continue
            
            # 检查是否为异性（如果需要的话）
            src_gender = 'M' if src.startswith('M') else 'F'
            dst_gender = 'M' if dst.startswith('M') else 'F'
            
            # 这里不强制异性恋假设，允许同性偏好
            valid_edges.append((src, dst))
        
        return valid_edges, warnings_list
    
    def print_parse_summary(self, result: ParseResult):
        """打印解析摘要"""
        print(f"=== 解析摘要 ===")
        print(f"解析边数: {len(result.edges)}")
        print(f"警告数量: {len(result.warnings)}")
        
        if result.warnings:
            print(f"\n警告信息:")
            for warning in result.warnings:
                print(f"  {warning}")
        
        print(f"\n解析出的有向边 ({len(result.edges)} 条):")
        edge_count = {}
        for src, dst in result.edges:
            key = f"{src} -> {dst}"
            edge_count[key] = edge_count.get(key, 0) + 1
        
        for edge, count in sorted(edge_count.items()):
            if count > 1:
                print(f"  {edge} (重复 {count} 次)")
            else:
                print(f"  {edge}")


def demo_parser():
    """演示解析器功能"""
    # 测试数据
    test_data = [
        {'嘉宾类型': '男', '编号': 1, '偏好描述': '1号男嘉宾喜欢3号、6号和9号女嘉宾。'},
        {'嘉宾类型': '男', '编号': 2, '偏好描述': '2号男嘉宾偏好1号、5号和8号女嘉宾。'},
        {'嘉宾类型': '女', '编号': 1, '偏好描述': '1号女嘉宾喜欢4号和2号男嘉宾。'},
        {'嘉宾类型': '女', '编号': 3, '偏好描述': '3号女嘉宾对1号和10号男嘉宾有好感。'},
    ]
    
    parser = ChinesePreferenceParser()
    result = parser.parse_all_preferences(test_data)
    parser.print_parse_summary(result)
    
    return result


if __name__ == "__main__":
    demo_parser()