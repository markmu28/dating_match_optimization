# -*- coding: utf-8 -*-
"""
ILP/MIP 求解器
使用整数线性规划求解分组优化问题
"""

from typing import List, Tuple, Dict, Optional
import warnings
from .graph import PreferenceGraph, validate_grouping


class ILPSolver:
    """ILP求解器"""
    
    def __init__(self, graph: PreferenceGraph, require_2by2: bool = True, time_limit: int = 300, 
                 num_males: int = 12, num_females: int = 12, group_size: int = 4):
        """
        初始化ILP求解器
        
        Args:
            graph: 偏好图
            require_2by2: 是否要求每组等量男女
            time_limit: 求解时间限制（秒）
            num_males: 男性人数
            num_females: 女性人数
            group_size: 每组人数
        """
        self.graph = graph
        self.require_2by2 = require_2by2
        self.time_limit = time_limit
        self.num_males = num_males
        self.num_females = num_females
        self.group_size = group_size
        
        # 定义人员和组别
        self.males = [f"M{i}" for i in range(1, num_males + 1)]
        self.females = [f"F{i}" for i in range(1, num_females + 1)]
        self.all_persons = self.males + self.females
        
        # 计算分组数量
        total_people = num_males + num_females
        self.num_groups = (total_people + group_size - 1) // group_size  # 向上取整
        self.groups = list(range(self.num_groups))
        
        # 检查pulp可用性
        self.pulp_available = self._check_pulp()
        
    def _check_pulp(self) -> bool:
        """检查pulp库是否可用"""
        try:
            import pulp
            return True
        except ImportError:
            warnings.warn("pulp库不可用，将自动回退到启发式算法")
            return False
    
    def _calculate_edge_score(self, person1: str, person2: str, group: int) -> float:
        """
        计算两个人在同一组时的边得分
        
        Args:
            person1: 人员1
            person2: 人员2  
            group: 组别ID
            
        Returns:
            得分（单向1分，互相喜欢总共mutual_weight分）
        """
        score = 0.0
        
        # 检查person1 -> person2
        if (person1, person2) in self.graph.edges:
            score += 1.0
            
        # 检查person2 -> person1
        if (person2, person1) in self.graph.edges:
            score += 1.0
            
        # 如果是互相喜欢，调整权重
        if score == 2.0:  # 双向都有边
            # mutual_weight是互相喜欢的总权重，所以直接使用
            score = self.graph.mutual_weight
            
        return score
    
    def solve(self) -> Tuple[Optional[List[List[str]]], Dict]:
        """
        求解分组问题
        
        Returns:
            (solution, info): 解决方案和求解信息
        """
        if not self.pulp_available:
            return None, {"status": "failed", "message": "pulp不可用"}
        
        try:
            import pulp
            
            # 创建问题
            prob = pulp.LpProblem("DatingGrouping", pulp.LpMaximize)
            
            # 决策变量: x[person][group] = 1 if person in group, 0 otherwise
            x = {}
            for person in self.all_persons:
                for group in self.groups:
                    x[(person, group)] = pulp.LpVariable(f"x_{person}_{group}", cat='Binary')
            
            # 引入辅助变量来处理"两人同组"的逻辑
            # y[(person1, person2, group)] = 1 当且仅当 person1 和 person2 都在 group
            y = {}
            objective = 0
            
            for group in self.groups:
                for i, person1 in enumerate(self.all_persons):
                    for j, person2 in enumerate(self.all_persons):
                        if i < j:  # 避免重复计算
                            edge_score = self._calculate_edge_score(person1, person2, group)
                            if edge_score > 0:
                                # 创建辅助变量
                                y[(person1, person2, group)] = pulp.LpVariable(f"y_{person1}_{person2}_{group}", cat='Binary')
                                
                                # 约束：y = 1 当且仅当两人都在同组
                                # y <= x1 and y <= x2 and y >= x1 + x2 - 1
                                prob += y[(person1, person2, group)] <= x[(person1, group)]
                                prob += y[(person1, person2, group)] <= x[(person2, group)]
                                prob += y[(person1, person2, group)] >= x[(person1, group)] + x[(person2, group)] - 1
                                
                                # 目标函数
                                objective += edge_score * y[(person1, person2, group)]
            
            prob += objective
            
            # 约束1：每个人只能在一个组
            for person in self.all_persons:
                prob += pulp.lpSum([x[(person, group)] for group in self.groups]) == 1
            
            # 约束2：每组人数限制
            for group in self.groups:
                if group == self.num_groups - 1:  # 最后一组
                    # 最后一组的人数 = 总人数 - 前面组的人数
                    remaining_people = len(self.all_persons) - (self.num_groups - 1) * self.group_size
                    prob += pulp.lpSum([x[(person, group)] for person in self.all_persons]) == remaining_people
                else:
                    # 非最后一组，恰好group_size人
                    prob += pulp.lpSum([x[(person, group)] for person in self.all_persons]) == self.group_size
            
            # 约束3：性别比例（如果需要）
            if self.require_2by2:
                for group in self.groups:
                    if group == self.num_groups - 1:  # 最后一组
                        # 最后一组保持1:1比例
                        remaining_people = len(self.all_persons) - (self.num_groups - 1) * self.group_size
                        males_in_last_group = remaining_people // 2
                        females_in_last_group = remaining_people // 2
                        
                        prob += pulp.lpSum([x[(male, group)] for male in self.males]) == males_in_last_group
                        prob += pulp.lpSum([x[(female, group)] for female in self.females]) == females_in_last_group
                    else:
                        # 非最后一组，每组等量男女
                        expected_gender_count = self.group_size // 2
                        prob += pulp.lpSum([x[(male, group)] for male in self.males]) == expected_gender_count
                        prob += pulp.lpSum([x[(female, group)] for female in self.females]) == expected_gender_count
            
            # 求解
            solver = pulp.PULP_CBC_CMD(timeLimit=self.time_limit, msg=False)
            prob.solve(solver)
            
            # 处理结果
            status = pulp.LpStatus[prob.status]
            
            if status == 'Optimal':
                # 提取解
                solution = [[] for _ in range(self.num_groups)]
                for person in self.all_persons:
                    for group in self.groups:
                        if x[(person, group)].varValue == 1:
                            solution[group].append(person)
                
                # 验证解的有效性
                is_valid, errors = validate_grouping(solution, self.require_2by2, False, 
                                                   self.num_males, self.num_females, self.group_size)
                if not is_valid:
                    return None, {
                        "status": "invalid_solution",
                        "message": "求解结果无效",
                        "errors": errors
                    }
                
                return solution, {
                    "status": "optimal",
                    "objective_value": pulp.value(prob.objective),
                    "solve_time": solver.actualSolve,
                    "solver": "PULP_CBC"
                }
            
            elif status in ['Infeasible', 'Unbounded']:
                return None, {
                    "status": "infeasible",
                    "message": f"问题无解: {status}"
                }
            else:
                return None, {
                    "status": "timeout_or_error", 
                    "message": f"求解未完成: {status}"
                }
                
        except Exception as e:
            return None, {
                "status": "error",
                "message": f"求解异常: {str(e)}"
            }
    
    def solve_with_callback(self, callback=None) -> Tuple[Optional[List[List[str]]], Dict]:
        """
        带回调的求解方法
        
        Args:
            callback: 回调函数，用于报告进度
            
        Returns:
            (solution, info): 解决方案和求解信息
        """
        if callback:
            callback("开始ILP求解...")
            
        result = self.solve()
        
        if callback:
            if result[0] is not None:
                callback("ILP求解成功")
            else:
                callback(f"ILP求解失败: {result[1].get('message', '未知错误')}")
                
        return result


def demo_ilp_solver():
    """演示ILP求解器"""
    from .parser_cn import ChinesePreferenceParser
    
    # 构造测试数据
    test_data = [
        {'嘉宾类型': '男', '编号': 1, '偏好描述': '1号男嘉宾喜欢3号、6号和9号女嘉宾。'},
        {'嘉宾类型': '男', '编号': 2, '偏好描述': '2号男嘉宾偏好1号、5号和8号女嘉宾。'},
        {'嘉宾类型': '男', '编号': 3, '偏好描述': '3号男嘉宾对2号和4号女嘉宾有好感。'},
        {'嘉宾类型': '女', '编号': 1, '偏好描述': '1号女嘉宾喜欢4号和2号男嘉宾。'},
        {'嘉宾类型': '女', '编号': 3, '偏好描述': '3号女嘉宾对1号和10号男嘉宾有好感。'},
        {'嘉宾类型': '女', '编号': 4, '偏好描述': '4号女嘉宾更想认识8号和12号男嘉宾。'},
    ]
    
    # 解析偏好
    parser = ChinesePreferenceParser()
    parse_result = parser.parse_all_preferences(test_data)
    
    print(f"解析到 {len(parse_result.edges)} 条边")
    for edge in parse_result.edges:
        print(f"  {edge[0]} -> {edge[1]}")
    
    # 创建图
    graph = PreferenceGraph(parse_result.edges, mutual_weight=2.0)
    
    # 创建求解器
    solver = ILPSolver(graph, require_2by2=True, time_limit=60)
    
    def progress_callback(msg):
        print(f"[ILP] {msg}")
    
    # 求解
    solution, info = solver.solve_with_callback(progress_callback)
    
    print(f"\n求解结果: {info}")
    
    if solution:
        print(f"\n最优分组方案:")
        for i, group in enumerate(solution):
            print(f"第{i+1}组: {group}")
        
        # 计算得分
        stats = graph.calculate_overall_score(solution)
        print(f"\n总得分: {stats.total_score:.1f}")
        print(f"平均每组得分: {stats.avg_group_score:.1f}")
        
        return solution, stats
    else:
        print("求解失败")
        return None, None


if __name__ == "__main__":
    demo_ilp_solver()