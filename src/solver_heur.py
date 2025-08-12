# -*- coding: utf-8 -*-
"""
启发式求解器
实现贪心+局部搜索算法求解分组优化问题
"""

import random
import math
import time
from typing import List, Tuple, Dict, Optional, Callable
from copy import deepcopy
from .graph import PreferenceGraph, validate_grouping, OverallStats


class HeuristicSolver:
    """启发式求解器"""
    
    def __init__(self, 
                 graph: PreferenceGraph, 
                 require_2by2: bool = True, 
                 seed: Optional[int] = None,
                 max_iterations: int = 10000,
                 temperature_start: float = 10.0,
                 temperature_end: float = 0.01,
                 cooling_rate: float = 0.99,
                 pairing_mode: bool = False,
                 num_males: int = 12,
                 num_females: int = 12,
                 group_size: int = 4):
        """
        初始化启发式求解器
        
        Args:
            graph: 偏好图
            require_2by2: 是否要求每组等量男女
            seed: 随机种子
            max_iterations: 最大迭代次数
            temperature_start: 模拟退火初始温度
            temperature_end: 模拟退火结束温度
            cooling_rate: 模拟退火降温率
            pairing_mode: 是否为一男一女配对模式
            num_males: 男性人数
            num_females: 女性人数
            group_size: 每组人数
        """
        self.graph = graph
        self.require_2by2 = require_2by2
        self.max_iterations = max_iterations
        self.temperature_start = temperature_start
        self.temperature_end = temperature_end
        self.cooling_rate = cooling_rate
        self.pairing_mode = pairing_mode
        self.num_males = num_males
        self.num_females = num_females
        self.group_size = group_size
        
        # 设置随机种子
        if seed is not None:
            random.seed(seed)
        
        # 定义人员
        self.males = [f"M{i}" for i in range(1, num_males + 1)]
        self.females = [f"F{i}" for i in range(1, num_females + 1)]
        self.all_persons = self.males + self.females
        
        # 计算分组数量
        if pairing_mode:
            self.num_groups = min(num_males, num_females)
        else:
            total_people = num_males + num_females
            self.num_groups = (total_people + group_size - 1) // group_size  # 向上取整
        
    def generate_random_solution(self) -> List[List[str]]:
        """生成随机分组方案"""
        if self.pairing_mode:
            return self.generate_random_pairing()
            
        solution = [[] for _ in range(self.num_groups)]
        
        if self.require_2by2:
            # 按性别分别随机分配
            males_copy = self.males.copy()
            females_copy = self.females.copy()
            random.shuffle(males_copy)
            random.shuffle(females_copy)
            
            for i in range(self.num_groups):
                if i == self.num_groups - 1:  # 最后一组
                    # 将剩余的人员都分配到最后一组
                    solution[i].extend(males_copy[i * (self.group_size // 2):])
                    solution[i].extend(females_copy[i * (self.group_size // 2):])
                else:
                    # 每组等量男女
                    gender_count = self.group_size // 2
                    solution[i].extend(males_copy[i * gender_count:(i + 1) * gender_count])
                    solution[i].extend(females_copy[i * gender_count:(i + 1) * gender_count])
        else:
            # 完全随机分配
            all_persons_shuffled = self.all_persons.copy()
            random.shuffle(all_persons_shuffled)
            
            for i in range(self.num_groups):
                if i == self.num_groups - 1:  # 最后一组
                    solution[i] = all_persons_shuffled[i * self.group_size:]
                else:
                    solution[i] = all_persons_shuffled[i * self.group_size:(i + 1) * self.group_size]
        
        return solution

    def generate_random_pairing(self) -> List[List[str]]:
        """生成随机一男一女配对方案"""
        males_copy = self.males.copy()
        females_copy = self.females.copy()
        random.shuffle(males_copy)
        random.shuffle(females_copy)
        
        # 生成min(num_males, num_females)对1v1配对
        pairs = []
        for i in range(self.num_groups):  # num_groups = min(num_males, num_females)
            pairs.append([males_copy[i], females_copy[i]])
        
        return pairs
    
    def generate_greedy_solution(self) -> List[List[str]]:
        """生成贪心初始解"""
        if self.pairing_mode:
            return self.generate_greedy_pairing()
            
        solution = [[] for _ in range(self.num_groups)]
        
        if self.require_2by2:
            # 按性别分别处理
            male_preferences = self._get_person_preferences(self.males)
            female_preferences = self._get_person_preferences(self.females)
            
            # 按偏好数量排序（偏好多的优先分配）
            sorted_males = sorted(self.males, key=lambda p: len(male_preferences[p]), reverse=True)
            sorted_females = sorted(self.females, key=lambda p: len(female_preferences[p]), reverse=True)
            
            # 贪心分配
            for i in range(self.num_groups):
                if i == self.num_groups - 1:  # 最后一组
                    # 将剩余的人员都分配到最后一组
                    solution[i].extend(sorted_males[i * (self.group_size // 2):])
                    solution[i].extend(sorted_females[i * (self.group_size // 2):])
                else:
                    # 每组等量男女
                    gender_count = self.group_size // 2
                    solution[i].extend(sorted_males[i * gender_count:(i + 1) * gender_count])
                    solution[i].extend(sorted_females[i * gender_count:(i + 1) * gender_count])
        else:
            # 不限制性别比例的贪心
            person_scores = {}
            for person in self.all_persons:
                # 计算每个人的"受欢迎程度" + "偏好广度"
                in_degree = len([edge for edge in self.graph.edges if edge[1] == person])
                out_degree = len([edge for edge in self.graph.edges if edge[0] == person])
                person_scores[person] = in_degree + out_degree * 0.5
            
            sorted_persons = sorted(self.all_persons, key=lambda p: person_scores[p], reverse=True)
            
            for i in range(self.num_groups):
                if i == self.num_groups - 1:  # 最后一组
                    solution[i] = sorted_persons[i * self.group_size:]
                else:
                    solution[i] = sorted_persons[i * self.group_size:(i + 1) * self.group_size]
        
        return solution

    def generate_greedy_pairing(self) -> List[List[str]]:
        """生成贪心一男一女配对方案"""
        # 构建男性和女性的偏好权重
        male_female_scores = {}  # (male, female) -> score
        
        for male in self.males:
            for female in self.females:
                score = 0.0
                # 计算男性对女性的偏好权重
                if (male, female) in self.graph.edge_weights:
                    score += self.graph.edge_weights[(male, female)]
                # 计算女性对男性的偏好权重
                if (female, male) in self.graph.edge_weights:
                    score += self.graph.edge_weights[(female, male)]
                    
                if score > 0:
                    male_female_scores[(male, female)] = score
        
        # 按得分排序所有可能的配对
        sorted_pairs = sorted(male_female_scores.items(), 
                            key=lambda x: x[1], reverse=True)
        
        # 贪心选择配对
        used_males = set()
        used_females = set()
        selected_pairs = []
        
        for (male, female), score in sorted_pairs:
            if male not in used_males and female not in used_females:
                selected_pairs.append([male, female])
                used_males.add(male)
                used_females.add(female)
                
                if len(selected_pairs) == self.num_groups:
                    break
        
        # 如果还有未配对的人员，随机配对
        remaining_males = [m for m in self.males if m not in used_males]
        remaining_females = [f for f in self.females if f not in used_females]
        
        for i in range(len(remaining_males)):
            if i < len(remaining_females):
                selected_pairs.append([remaining_males[i], remaining_females[i]])
        
        return selected_pairs
    
    def _get_person_preferences(self, persons: List[str]) -> Dict[str, List[str]]:
        """获取每个人的偏好列表"""
        preferences = {person: [] for person in persons}
        
        for src, dst in self.graph.edges:
            if src in persons:
                preferences[src].append(dst)
        
        return preferences
    
    def calculate_solution_score(self, solution: List[List[str]]) -> float:
        """计算解的总得分"""
        stats = self.graph.calculate_overall_score(solution)
        return stats.total_score
    
    def get_neighbors(self, solution: List[List[str]]) -> List[List[List[str]]]:
        """生成邻域解（通过人员交换）"""
        if self.pairing_mode:
            return self.get_pairing_neighbors(solution)
            
        neighbors = []
        
        # 单点移动：将一个人从一组移到另一组
        for from_group in range(self.num_groups):
            for to_group in range(self.num_groups):
                if from_group != to_group:
                    for person_idx in range(len(solution[from_group])):
                        # 创建新解
                        new_solution = deepcopy(solution)
                        person = new_solution[from_group].pop(person_idx)
                        
                        # 检查目标组是否已满
                        max_group_size = self.group_size if to_group != self.num_groups - 1 else len(self.all_persons)
                        if len(new_solution[to_group]) < max_group_size:
                            new_solution[to_group].append(person)
                            
                            # 检查约束
                            if self._is_valid_partial_solution(new_solution):
                                neighbors.append(new_solution)
        
        # 两点互换：交换不同组的两个人
        for group1 in range(self.num_groups):
            for group2 in range(group1 + 1, self.num_groups):
                for person1_idx in range(len(solution[group1])):
                    for person2_idx in range(len(solution[group2])):
                        new_solution = deepcopy(solution)
                        
                        # 交换两个人
                        person1 = new_solution[group1][person1_idx]
                        person2 = new_solution[group2][person2_idx]
                        
                        new_solution[group1][person1_idx] = person2
                        new_solution[group2][person2_idx] = person1
                        
                        # 检查约束
                        if self._is_valid_partial_solution(new_solution):
                            neighbors.append(new_solution)
        
        return neighbors

    def get_pairing_neighbors(self, solution: List[List[str]]) -> List[List[List[str]]]:
        """生成配对模式的邻域解（交换配对中的男性或女性）"""
        neighbors = []
        
        # 交换两对配对中的男性
        for i in range(self.num_groups):
            for j in range(i + 1, self.num_groups):
                if len(solution) > max(i, j) and len(solution[i]) >= 1 and len(solution[j]) >= 1:
                    # 找到每对中的男性
                    male_i = next((p for p in solution[i] if p.startswith('M')), None)
                    male_j = next((p for p in solution[j] if p.startswith('M')), None)
                    
                    if male_i and male_j:
                        new_solution = deepcopy(solution)
                        # 交换男性
                        for k, person in enumerate(new_solution[i]):
                            if person == male_i:
                                new_solution[i][k] = male_j
                                break
                        for k, person in enumerate(new_solution[j]):
                            if person == male_j:
                                new_solution[j][k] = male_i
                                break
                        neighbors.append(new_solution)
        
        # 交换两对配对中的女性
        for i in range(self.num_groups):
            for j in range(i + 1, self.num_groups):
                if len(solution) > max(i, j) and len(solution[i]) >= 1 and len(solution[j]) >= 1:
                    # 找到每对中的女性
                    female_i = next((p for p in solution[i] if p.startswith('F')), None)
                    female_j = next((p for p in solution[j] if p.startswith('F')), None)
                    
                    if female_i and female_j:
                        new_solution = deepcopy(solution)
                        # 交换女性
                        for k, person in enumerate(new_solution[i]):
                            if person == female_i:
                                new_solution[i][k] = female_j
                                break
                        for k, person in enumerate(new_solution[j]):
                            if person == female_j:
                                new_solution[j][k] = female_i
                                break
                        neighbors.append(new_solution)
        
        return neighbors
    
    def _is_valid_partial_solution(self, solution: List[List[str]]) -> bool:
        """检查部分解是否满足约束"""
        if not self.require_2by2:
            return True
        
        for i, group in enumerate(solution):
            max_size = self.group_size if i != self.num_groups - 1 else len(self.all_persons)
            if len(group) > max_size:  # 超出组大小限制
                return False
            
            males_in_group = sum(1 for p in group if p.startswith('M'))
            females_in_group = sum(1 for p in group if p.startswith('F'))
            
            # 如果组已满，检查性别比例
            expected_size = self.group_size if i != self.num_groups - 1 else (len(self.all_persons) - (self.num_groups - 1) * self.group_size)
            if len(group) == expected_size:
                if males_in_group != females_in_group:
                    return False
            # 如果组未满，检查是否可能达到1:1比例
            elif len(group) > 0:
                max_possible_males = males_in_group + (expected_size - len(group))
                max_possible_females = females_in_group + (expected_size - len(group))
                expected_gender_count = expected_size // 2
                
                if max_possible_males < expected_gender_count or max_possible_females < expected_gender_count:
                    return False
        
        return True
    
    def hill_climbing(self, initial_solution: List[List[str]], callback: Optional[Callable] = None) -> Tuple[List[List[str]], float, int]:
        """爬山算法"""
        current_solution = deepcopy(initial_solution)
        current_score = self.calculate_solution_score(current_solution)
        iterations = 0
        
        while iterations < self.max_iterations:
            neighbors = self.get_neighbors(current_solution)
            
            if not neighbors:
                break
            
            # 找到最好的邻居
            best_neighbor = None
            best_score = current_score
            
            for neighbor in neighbors:
                score = self.calculate_solution_score(neighbor)
                if score > best_score:
                    best_neighbor = neighbor
                    best_score = score
            
            if best_neighbor is None:
                # 没有更好的邻居，到达局部最优
                break
            
            current_solution = best_neighbor
            current_score = best_score
            iterations += 1
            
            if callback and iterations % 100 == 0:
                callback(f"爬山法迭代 {iterations}，当前得分: {current_score:.1f}")
        
        return current_solution, current_score, iterations
    
    def simulated_annealing(self, initial_solution: List[List[str]], callback: Optional[Callable] = None) -> Tuple[List[List[str]], float, int]:
        """模拟退火算法"""
        current_solution = deepcopy(initial_solution)
        current_score = self.calculate_solution_score(current_solution)
        
        best_solution = deepcopy(current_solution)
        best_score = current_score
        
        temperature = self.temperature_start
        iterations = 0
        
        while temperature > self.temperature_end and iterations < self.max_iterations:
            neighbors = self.get_neighbors(current_solution)
            
            if neighbors:
                # 随机选择一个邻居
                neighbor = random.choice(neighbors)
                neighbor_score = self.calculate_solution_score(neighbor)
                
                # 计算接受概率
                if neighbor_score > current_score:
                    # 更好的解，直接接受
                    accept = True
                else:
                    # 较差的解，以一定概率接受
                    delta = current_score - neighbor_score
                    probability = math.exp(-delta / temperature)
                    accept = random.random() < probability
                
                if accept:
                    current_solution = neighbor
                    current_score = neighbor_score
                    
                    # 更新最优解
                    if current_score > best_score:
                        best_solution = deepcopy(current_solution)
                        best_score = current_score
            
            # 降温
            temperature *= self.cooling_rate
            iterations += 1
            
            if callback and iterations % 100 == 0:
                callback(f"模拟退火迭代 {iterations}，温度: {temperature:.3f}, 当前得分: {current_score:.1f}, 最优得分: {best_score:.1f}")
        
        return best_solution, best_score, iterations
    
    def solve(self, 
              algorithm: str = "simulated_annealing", 
              initial_strategy: str = "greedy", 
              num_restarts: int = 5,
              callback: Optional[Callable] = None) -> Tuple[Optional[List[List[str]]], Dict]:
        """
        求解分组问题
        
        Args:
            algorithm: 算法选择 ("hill_climbing" 或 "simulated_annealing")
            initial_strategy: 初始解策略 ("random" 或 "greedy")
            num_restarts: 重启次数
            callback: 进度回调函数
            
        Returns:
            (solution, info): 解决方案和求解信息
        """
        start_time = time.time()
        best_solution = None
        best_score = -1
        total_iterations = 0
        
        try:
            for restart in range(num_restarts):
                if callback:
                    callback(f"第 {restart + 1}/{num_restarts} 次重启")
                
                # 生成初始解
                if initial_strategy == "random":
                    initial_solution = self.generate_random_solution()
                else:  # greedy
                    initial_solution = self.generate_greedy_solution()
                
                # 验证初始解
                is_valid, errors = validate_grouping(initial_solution, self.require_2by2, self.pairing_mode,
                                                   self.num_males, self.num_females, self.group_size)
                if not is_valid:
                    if callback:
                        callback(f"第 {restart + 1} 次重启: 初始解无效，跳过")
                    continue
                
                # 选择算法
                if algorithm == "hill_climbing":
                    solution, score, iterations = self.hill_climbing(initial_solution, callback)
                else:  # simulated_annealing
                    solution, score, iterations = self.simulated_annealing(initial_solution, callback)
                
                total_iterations += iterations
                
                if score > best_score:
                    best_solution = solution
                    best_score = score
                    
                    if callback:
                        callback(f"第 {restart + 1} 次重启找到更好解: {best_score:.1f}")
            
            solve_time = time.time() - start_time
            
            if best_solution is not None:
                # 最终验证
                is_valid, errors = validate_grouping(best_solution, self.require_2by2, self.pairing_mode,
                                                   self.num_males, self.num_females, self.group_size)
                if not is_valid:
                    return None, {
                        "status": "invalid_solution",
                        "message": "最终解无效",
                        "errors": errors
                    }
                
                return best_solution, {
                    "status": "completed",
                    "algorithm": algorithm,
                    "initial_strategy": initial_strategy,
                    "best_score": best_score,
                    "total_iterations": total_iterations,
                    "num_restarts": num_restarts,
                    "solve_time": solve_time
                }
            else:
                return None, {
                    "status": "no_solution",
                    "message": "未找到有效解"
                }
                
        except Exception as e:
            return None, {
                "status": "error",
                "message": f"求解异常: {str(e)}"
            }


def demo_heuristic_solver():
    """演示启发式求解器"""
    from .parser_cn import ChinesePreferenceParser
    
    # 构造测试数据
    test_data = [
        {'嘉宾类型': '男', '编号': 1, '偏好描述': '1号男嘉宾喜欢3号、6号和9号女嘉宾。'},
        {'嘉宾类型': '男', '编号': 2, '偏好描述': '2号男嘉宾偏好1号、5号和8号女嘉宾。'},
        {'嘉宾类型': '男', '编号': 3, '偏好描述': '3号男嘉宾对2号和4号女嘉宾有好感。'},
        {'嘉宾类型': '女', '编号': 1, '偏好描述': '1号女嘉宾喜欢4号和2号男嘉宾。'},
        {'嘉宾类型': '女', '编号': 3, '偏好描述': '3号女嘉宾对1号和10号男嘉宾有好感。'},
        {'嘉宾类型': '女', '编号': 6, '偏好描述': '6号女嘉宾中意12号和7号男嘉宾。'},
    ]
    
    # 解析偏好
    parser = ChinesePreferenceParser()
    parse_result = parser.parse_all_preferences(test_data)
    
    print(f"解析到 {len(parse_result.edges)} 条边")
    
    # 创建图
    graph = PreferenceGraph(parse_result.edges, mutual_weight=2.0)
    
    # 创建求解器
    solver = HeuristicSolver(
        graph, 
        require_2by2=True, 
        seed=42, 
        max_iterations=1000
    )
    
    def progress_callback(msg):
        print(f"[启发式] {msg}")
    
    # 测试不同算法
    for algorithm in ["hill_climbing", "simulated_annealing"]:
        print(f"\n=== 测试 {algorithm} ===")
        
        solution, info = solver.solve(
            algorithm=algorithm,
            initial_strategy="greedy",
            num_restarts=3,
            callback=progress_callback
        )
        
        print(f"求解结果: {info}")
        
        if solution:
            print(f"\n最优分组方案:")
            for i, group in enumerate(solution):
                print(f"第{i+1}组: {group}")
            
            # 计算得分
            stats = graph.calculate_overall_score(solution)
            print(f"总得分: {stats.total_score:.1f}")
            print(f"平均每组得分: {stats.avg_group_score:.1f}")
        else:
            print("求解失败")
    
    return solver


if __name__ == "__main__":
    demo_heuristic_solver()