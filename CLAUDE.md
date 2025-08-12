# 项目：相亲活动分组优化工具

## 目标
将 Excel 中的中文自然语言偏好解析为"有向喜欢图"，并在嘉宾中生成最优分组方案，最大化组内喜欢关系的命中（互相喜欢权重更高）。

**支持灵活人数配置**：
- 默认 24 位嘉宾（12 男、12 女）生成 6 组、每组 4 人
- 支持任意人数的嘉宾，自动检测数据中的男女人数
- 支持自定义每组人数（`--group-size`），最后一组可少于标准组大小
- 人数不整除时采用"最后一组人数减少"的处理策略

## 非目标
- 本版本不处理“排斥/避开”约束，不做长期稳定婚配，只做一期活动的分组优化。
- 不做 UI；仅命令行与文件输出。

## 约束与规则
- **性别比例**：强制每组男女 1:1 比例（可通过 `--two-by-two` 配置）
- **分组模式**：
  - 传统分组：生成多组，每组若干人（默认4人）
  - 配对模式：`--pairing-mode` 生成 1v1 配对
- **人数处理**：
  - 自动从输入数据检测男女嘉宾人数
  - 分组数量 = (总人数 + 组大小 - 1) ÷ 组大小（向上取整）
  - 最后一组人数可能少于标准组大小，但仍保持 1:1 性别比例
- **评分系统**：
  - 单向喜欢 = 1 分；互相喜欢 = 2 分（可配置 `--mutual-weight`）
  - Ranking模式：第一偏好权重（默认2.0），第二偏好权重（默认1.0）
- **解析兼容性**：兼容中文多样表述；对无法解析的句子给出 warning 并忽略
- **可重现性**：支持 `--seed` 参数确保结果可重现

## 技术路线
1. **自动人数检测**（`cli.py::detect_guest_counts()`）
   - 从输入数据自动扫描嘉宾类型和编号，检测男女人数
   - 支持非标准人数配置（不限于24人）
2. **解析层**（`src/parser_cn.py`, `src/parser_ranking.py`）
   - **中文模式**：使用正则和模式词典提取主体与目标编号集合
   - **Ranking模式**：解析"对象1ID"、"对象2ID"列，支持加权偏好
   - 归一化为动态 ID：男=M1..MN，女=F1..FN（N为检测到的人数）
   - 输出：有向边列表 `[(src, dst), ...]` 与解析日志
3. **图与评分**（`src/graph.py`）
   - 统计单向与互向喜欢；提供组得分计算与全局目标函数
   - 支持动态人数验证：`validate_grouping()` 适配任意人数场景
4. **求解器**  
   - **ILP求解器**（`src/solver_ilp.py`）：动态约束生成，支持任意人数和组大小
   - **启发式求解器**（`src/solver_heur.py`）：动态邻域搜索，支持传统分组和配对模式
   - 自动分组数量计算：`num_groups = ⌈total_people / group_size⌉`
5. **IO 层**（`src/io_excel.py`）
   - 读取 Excel/CSV，写出 CSV/JSON/Excel 结果
6. **CLI 增强**（`cli.py`）
   - 新增：`--group-size`（每组人数）、`--pairing-mode`（配对模式）
   - 保留：`--input`、`--two-by-two`、`--mutual-weight`、`--solver`、`--seed` 等

## 目录结构
.
├─ src/
│  ├─ parser_cn.py      # 中文偏好解析（正则/模式库）
│  ├─ graph.py          # 构建喜好图与评分
│  ├─ solver_ilp.py     # ILP/MIP 实现
│  ├─ solver_heur.py    # 启发式实现（初始化+邻域搜索）
│  └─ io_excel.py       # 读写 Excel/CSV/JSON
├─ cli.py               # 命令行入口
├─ tests/               # pytest：解析与求解最小用例
├─ requirements.txt
└─ README.md

## 运行示例

### 基础运行
```bash
pip install -r requirements.txt

# 默认24人场景
python cli.py --input 相亲偏好示例.xlsx --export-xlsx

# 仅解析测试
python cli.py --input 相亲偏好示例.xlsx --dry-run-parse
```

### 灵活人数场景
```bash
# 16人场景（8男8女），自动检测人数
python cli.py --input test_16人.csv --mode text --solver heuristic

# 10人场景，自定义组大小
python cli.py --input test_10人.csv --group-size 3 --mode text

# 配对模式（1v1配对）
python cli.py --input test_10人.csv --pairing-mode --mode text
```

### 参数说明
```bash
# 人数配置
--group-size N          # 每组人数（默认4），最后一组可少于此值
--pairing-mode          # 1v1配对模式，生成 min(男性数, 女性数) 对配对

# 模式选择
--mode ranking          # Ranking ID模式（默认）
--mode text            # 中文自然语言解析模式

# 求解器选择
--solver auto          # 自动选择（默认）
--solver heuristic     # 启发式算法
--solver ilp           # 整数线性规划（不支持配对模式）
```

## 验收标准

### 基础功能
- ✅ **24人标准场景**：成功输出 6 组（每组 4 人），打印并导出命中明细与统计
- ✅ **中文解析鲁棒性**：覆盖"喜欢/偏好/中意/希望同组/有好感/并列编号/或/和/中文标点"
- ✅ **算法可靠性**：若 ILP 依赖不可用，启发式能给出合理、可复现的非零得分方案

### 灵活人数支持
- ✅ **任意人数适配**：支持非24人场景（如16人、10人等）
- ✅ **自动人数检测**：从输入数据自动识别男女嘉宾数量
- ✅ **动态分组计算**：根据人数和组大小自动计算分组数量
- ✅ **最后一组处理**：人数不整除时，最后一组人数减少但保持1:1性别比例
- ✅ **配对模式**：支持1v1配对，适用于任意人数

### 测试用例
```bash
# 16人场景测试
python cli.py --input 嘉宾偏好_第一轮.xlsx --export-xlsx --verbose
# 预期：4组，每组4人，互相喜欢命中率>80%

# 10人场景测试  
python cli.py --嘉宾偏好_第二轮.xlsx --mode text --solver heuristic
# 预期：3组（4+4+2人），最后一组2人，验证通过

# 10人配对测试
python cli.py --input test_10人.csv --pairing-mode --mode text
# 预期：5对1v1配对，每对都是一男一女
```

## 技术特性

### 向后兼容性
- 默认参数保持24人场景行为不变
- 现有配置文件和数据格式完全兼容
- CLI参数扩展，不影响原有功能

### 性能优化
- 动态约束生成，适配任意规模
- 智能求解器选择（启发式→ILP备份）
- 内存效率优化，支持大规模场景
