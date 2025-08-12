# -*- coding: utf-8 -*-
"""
图建模和评分系统
用于构建偏好图、计算分组得分和统计信息
"""

from typing import List, Tuple, Dict, Set, Optional
from dataclasses import dataclass
from collections import defaultdict, Counter
import json


@dataclass
class GroupScore:
    """分组得分详情"""
    group_id: int
    members: List[str]
    single_preferences: List[Tuple[str, str]]  # 单向喜欢
    mutual_preferences: List[Tuple[str, str]]  # 互相喜欢
    total_score: float
    single_count: int
    mutual_count: int


@dataclass 
class OverallStats:
    """整体统计信息"""
    total_score: float
    avg_group_score: float
    total_single_prefs: int
    total_mutual_prefs: int
    group_scores: List[GroupScore]
    hit_rate_single: float  # 单向喜欢命中率
    hit_rate_mutual: float  # 互相喜欢命中率


class PreferenceGraph:
    """偏好图"""
    
    def __init__(self, edges: List[Tuple[str, str]], mutual_weight: float = 2.0, weighted_edges: List[Tuple[str, str, float]] = None, first_round_penalties: Set[Tuple[str, str]] = None, penalty_weight: float = -1.0):
        """
        初始化偏好图
        
        Args:
            edges: 有向边列表 [(src, dst), ...] - 用于兼容性
            mutual_weight: 互相喜欢的权重
            weighted_edges: 加权边列表 [(src, dst, weight), ...] - 支持ranking模式
            first_round_penalties: 第一轮单向喜欢关系，需要施加惩罚 {(src, dst), ...}
            penalty_weight: 第一轮单向喜欢关系的惩罚权重
        """
        self.edges = edges
        self.mutual_weight = mutual_weight
        self.weighted_edges = weighted_edges or []
        self.first_round_penalties = first_round_penalties or set()
        self.penalty_weight = penalty_weight
        
        # 构建图结构
        self.graph = defaultdict(set)  # src -> {dst1, dst2, ...}
        self.reverse_graph = defaultdict(set)  # dst -> {src1, src2, ...}
        self.edge_weights = {}  # (src, dst) -> weight
        
        # 如果有加权边，优先使用加权边
        if self.weighted_edges:
            for src, dst, weight in self.weighted_edges:
                self.graph[src].add(dst)
                self.reverse_graph[dst].add(src)
                self.edge_weights[(src, dst)] = weight
            # 同时保持edges兼容性
            self.edges = [(src, dst) for src, dst, _ in self.weighted_edges]
        else:
            # 传统模式，所有边权重为1
            for src, dst in edges:
                self.graph[src].add(dst)
                self.reverse_graph[dst].add(src)
                self.edge_weights[(src, dst)] = 1.0
        
        # 统计信息
        self.all_nodes = self._get_all_nodes()
        self.mutual_pairs = self._find_mutual_pairs()
    
    def _get_all_nodes(self) -> Set[str]:
        """获取所有节点"""
        nodes = set()
        for src, dst in self.edges:
            nodes.add(src)
            nodes.add(dst)
        return nodes
    
    def _find_mutual_pairs(self) -> Set[Tuple[str, str]]:
        """找到所有互相喜欢的对"""
        mutual_pairs = set()
        for src, dst in self.edges:
            if dst in self.graph and src in self.graph[dst]:
                # 确保每对只记录一次，按字典序排序
                pair = tuple(sorted([src, dst]))
                mutual_pairs.add(pair)
        return mutual_pairs
    
    def get_single_preferences_in_group(self, group: List[str]) -> List[Tuple[str, str]]:
        """获取组内的单向喜欢关系"""
        single_prefs = []
        group_set = set(group)
        
        for src, dst in self.edges:
            if src in group_set and dst in group_set:
                # 检查是否为互相喜欢
                is_mutual = (dst in self.graph and src in self.graph[dst])
                if not is_mutual:
                    single_prefs.append((src, dst))
        
        return single_prefs
    
    def get_mutual_preferences_in_group(self, group: List[str]) -> List[Tuple[str, str]]:
        """获取组内的互相喜欢关系"""
        mutual_prefs = []
        group_set = set(group)
        seen_pairs = set()
        
        for src, dst in self.edges:
            if src in group_set and dst in group_set:
                # 检查是否为互相喜欢
                if dst in self.graph and src in self.graph[dst]:
                    # 确保每对只记录一次
                    pair = tuple(sorted([src, dst]))
                    if pair not in seen_pairs:
                        mutual_prefs.append(pair)
                        seen_pairs.add(pair)
        
        return mutual_prefs
    
    def calculate_group_score(self, group: List[str], group_id: int = 0) -> GroupScore:
        """
        计算单个分组的得分
        
        Args:
            group: 分组成员列表
            group_id: 分组ID
            
        Returns:
            GroupScore: 分组得分详情
        """
        single_prefs = self.get_single_preferences_in_group(group)
        mutual_prefs = self.get_mutual_preferences_in_group(group)
        
        # 计算得分 - 支持加权边和第一轮惩罚
        if self.weighted_edges:
            # 加权模式：使用边的实际权重
            single_score = sum(self.edge_weights.get((src, dst), 1.0) for src, dst in single_prefs)
            # 互相喜欢：两个方向的权重之和
            mutual_score = 0.0
            for src, dst in mutual_prefs:
                weight1 = self.edge_weights.get((src, dst), 1.0)
                weight2 = self.edge_weights.get((dst, src), 1.0)
                mutual_score += weight1 + weight2
        else:
            # 传统模式
            single_score = len(single_prefs) * 1.0  # 单向喜欢 1 分
            mutual_score = len(mutual_prefs) * self.mutual_weight  # 互相喜欢按权重计分
        
        # 应用第一轮惩罚
        penalty_score = 0.0
        if self.first_round_penalties:
            for src, dst in single_prefs:
                if (src, dst) in self.first_round_penalties:
                    penalty_score += self.penalty_weight
        
        total_score = single_score + mutual_score + penalty_score
        
        return GroupScore(
            group_id=group_id,
            members=sorted(group),
            single_preferences=single_prefs,
            mutual_preferences=mutual_prefs,
            total_score=total_score,
            single_count=len(single_prefs),
            mutual_count=len(mutual_prefs)
        )
    
    def calculate_overall_score(self, groups: List[List[str]]) -> OverallStats:
        """
        计算整体得分和统计
        
        Args:
            groups: 所有分组的列表
            
        Returns:
            OverallStats: 整体统计信息
        """
        group_scores = []
        total_score = 0.0
        total_single = 0
        total_mutual = 0
        
        # 计算每组得分
        for i, group in enumerate(groups):
            score = self.calculate_group_score(group, i + 1)
            group_scores.append(score)
            total_score += score.total_score
            total_single += score.single_count
            total_mutual += score.mutual_count
        
        # 计算平均分
        avg_score = total_score / len(groups) if groups else 0.0
        
        # 计算命中率
        total_possible_single = len(self.edges) - 2 * len(self.mutual_pairs)  # 总边数 - 互相喜欢边数
        total_possible_mutual = len(self.mutual_pairs)
        
        hit_rate_single = total_single / total_possible_single if total_possible_single > 0 else 0.0
        hit_rate_mutual = total_mutual / total_possible_mutual if total_possible_mutual > 0 else 0.0
        
        return OverallStats(
            total_score=total_score,
            avg_group_score=avg_score,
            total_single_prefs=total_single,
            total_mutual_prefs=total_mutual,
            group_scores=group_scores,
            hit_rate_single=hit_rate_single,
            hit_rate_mutual=hit_rate_mutual
        )
    
    def print_group_details(self, group_score: GroupScore):
        """打印单个分组详情"""
        print(f"\n=== 第 {group_score.group_id} 组 ===")
        print(f"成员: {', '.join(group_score.members)}")
        print(f"总得分: {group_score.total_score:.1f}")
        
        if group_score.single_preferences:
            print(f"单向喜欢 ({group_score.single_count} 条，每条 1.0 分):")
            for src, dst in group_score.single_preferences:
                print(f"  {src} → {dst}")
        
        if group_score.mutual_preferences:
            print(f"互相喜欢 ({group_score.mutual_count} 对，每对 {self.mutual_weight:.1f} 分):")
            for src, dst in group_score.mutual_preferences:
                print(f"  {src} ↔ {dst}")
        
        if not group_score.single_preferences and not group_score.mutual_preferences:
            print("  无组内喜欢关系")
    
    def print_overall_stats(self, stats: OverallStats):
        """打印整体统计"""
        print(f"\n=== 整体统计 ===")
        print(f"总得分: {stats.total_score:.1f}")
        print(f"平均每组得分: {stats.avg_group_score:.1f}")
        print(f"单向喜欢命中: {stats.total_single_prefs} 条 (命中率: {stats.hit_rate_single:.1%})")
        print(f"互相喜欢命中: {stats.total_mutual_prefs} 对 (命中率: {stats.hit_rate_mutual:.1%})")
        print(f"分组数: {len(stats.group_scores)}")
        
        # 打印每组详情
        for group_score in stats.group_scores:
            self.print_group_details(group_score)
    
    def export_stats_to_dict(self, stats: OverallStats) -> Dict:
        """将统计信息导出为字典格式"""
        result = {
            "overall": {
                "total_score": stats.total_score,
                "avg_group_score": stats.avg_group_score,
                "total_single_prefs": stats.total_single_prefs,
                "total_mutual_prefs": stats.total_mutual_prefs,
                "hit_rate_single": stats.hit_rate_single,
                "hit_rate_mutual": stats.hit_rate_mutual,
                "num_groups": len(stats.group_scores)
            },
            "groups": []
        }
        
        for group_score in stats.group_scores:
            group_dict = {
                "group_id": group_score.group_id,
                "members": group_score.members,
                "total_score": group_score.total_score,
                "single_count": group_score.single_count,
                "mutual_count": group_score.mutual_count,
                "single_preferences": [{"from": src, "to": dst} for src, dst in group_score.single_preferences],
                "mutual_preferences": [{"pair": [src, dst]} for src, dst in group_score.mutual_preferences]
            }
            result["groups"].append(group_dict)
        
        return result
    
    def get_graph_stats(self) -> Dict:
        """获取图的基本统计信息"""
        node_degrees = Counter()
        for src, dst in self.edges:
            node_degrees[src] += 1
        
        return {
            "total_edges": len(self.edges),
            "total_nodes": len(self.all_nodes),
            "mutual_pairs": len(self.mutual_pairs),
            "avg_out_degree": sum(node_degrees.values()) / len(self.all_nodes) if self.all_nodes else 0,
            "nodes_with_preferences": len(node_degrees),
            "nodes_without_preferences": len(self.all_nodes) - len(node_degrees)
        }


def validate_grouping(groups: List[List[str]], require_2by2: bool = True, pairing_mode: bool = False, 
                     expected_males: int = 12, expected_females: int = 12, group_size: int = 4) -> Tuple[bool, List[str]]:
    """
    验证分组方案的有效性
    
    Args:
        groups: 分组方案
        require_2by2: 是否要求每组等量男女
        pairing_mode: 是否为配对模式
        expected_males: 期望男性人数
        expected_females: 期望女性人数
        group_size: 标准组大小（最后一组可以小于此值）
        
    Returns:
        (is_valid, error_messages): 是否有效和错误信息列表
    """
    errors = []
    
    total_people = expected_males + expected_females
    expected_pairs = min(expected_males, expected_females)
    
    if pairing_mode:
        # 配对模式验证
        if len(groups) != expected_pairs:
            errors.append(f"配对数量应为{expected_pairs}，实际为{len(groups)}")
        
        # 检查每对人数
        for i, pair in enumerate(groups):
            if len(pair) != 2:
                errors.append(f"第{i+1}对人数应为2，实际为{len(pair)}")
            else:
                # 检查每对是否为一男一女
                males = [m for m in pair if m.startswith('M')]
                females = [m for m in pair if m.startswith('F')]
                
                if len(males) != 1:
                    errors.append(f"第{i+1}对男性人数应为1，实际为{len(males)}")
                if len(females) != 1:
                    errors.append(f"第{i+1}对女性人数应为1，实际为{len(females)}")
    else:
        # 传统分组模式验证
        expected_groups = (total_people + group_size - 1) // group_size  # 向上取整
        if len(groups) != expected_groups:
            errors.append(f"分组数量应为{expected_groups}，实际为{len(groups)}")
        
        # 检查每组人数
        for i, group in enumerate(groups):
            # 最后一组可以人数较少
            if i == len(groups) - 1:  # 最后一组
                if len(group) == 0:
                    errors.append(f"第{i+1}组不能为空")
            else:  # 非最后一组
                if len(group) != group_size:
                    errors.append(f"第{i+1}组人数应为{group_size}，实际为{len(group)}")
    
    # 检查人员重复
    all_members = []
    for group in groups:
        all_members.extend(group)
    
    if len(all_members) != len(set(all_members)):
        duplicates = [x for x in all_members if all_members.count(x) > 1]
        errors.append(f"发现重复人员: {set(duplicates)}")
    
    # 检查人员完整性
    expected_members = {f"M{i}" for i in range(1, expected_males + 1)} | {f"F{i}" for i in range(1, expected_females + 1)}
    actual_members = set(all_members)
    
    missing = expected_members - actual_members
    if missing:
        errors.append(f"缺少人员: {sorted(missing)}")
    
    extra = actual_members - expected_members
    if extra:
        errors.append(f"多余人员: {sorted(extra)}")
    
    # 检查性别比例（仅限传统分组模式）
    if require_2by2 and not pairing_mode:
        for i, group in enumerate(groups):
            males = [m for m in group if m.startswith('M')]
            females = [m for m in group if m.startswith('F')]
            
            # 要求每组男女1:1
            if len(males) != len(females):
                errors.append(f"第{i+1}组男女比例应为1:1，实际为{len(males)}:{len(females)}")
            
            # 最后一组可以人数较少，但仍需保持1:1
            if i == len(groups) - 1:  # 最后一组
                if len(group) % 2 != 0:
                    errors.append(f"第{i+1}组(最后一组)人数应为偶数以保持1:1性别比例，实际为{len(group)}")
            else:  # 非最后一组
                expected_gender_count = group_size // 2
                if len(males) != expected_gender_count:
                    errors.append(f"第{i+1}组男性人数应为{expected_gender_count}，实际为{len(males)}")
                if len(females) != expected_gender_count:
                    errors.append(f"第{i+1}组女性人数应为{expected_gender_count}，实际为{len(females)}")
    
    return len(errors) == 0, errors


def demo_graph():
    """演示图功能"""
    # 构造测试边
    test_edges = [
        ("M1", "F3"), ("M1", "F6"), ("M1", "F9"),
        ("M2", "F1"), ("M2", "F5"), ("M2", "F8"),
        ("F1", "M4"), ("F1", "M2"),  # F1->M2, M2->F1 不构成互相喜欢（M2喜欢的是其他人）
        ("F3", "M1"), ("F3", "M10"),  # F3->M1, M1->F3 构成互相喜欢 
        ("M4", "F1"),  # M4->F1, F1->M4 构成互相喜欢
    ]
    
    # 创建图
    graph = PreferenceGraph(test_edges, mutual_weight=2.0)
    
    # 测试分组
    test_groups = [
        ["M1", "M2", "F1", "F3"],  # 包含互相喜欢和单向喜欢
        ["M3", "M4", "F2", "F4"],
        ["M5", "M6", "F5", "F6"],
        ["M7", "M8", "F7", "F8"],
        ["M9", "M10", "F9", "F10"],
        ["M11", "M12", "F11", "F12"]
    ]
    
    # 计算得分
    stats = graph.calculate_overall_score(test_groups)
    
    # 打印结果
    graph.print_overall_stats(stats)
    
    # 验证分组
    is_valid, errors = validate_grouping(test_groups, require_2by2=True)
    print(f"\n分组有效性: {'有效' if is_valid else '无效'}")
    if errors:
        for error in errors:
            print(f"  错误: {error}")
    
    return graph, stats


if __name__ == "__main__":
    demo_graph()