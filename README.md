# 相亲活动分组优化工具

用于相亲活动分组/配对的命令行与图形界面工具，支持第一轮、第二轮（避重复）和第三轮 1v1 配对。

快速上手请看：`极简操作手册.md`

## 功能概览

- 支持两种输入模式：`ranking`（ID/姓名混合偏好）和 `text`（中文描述）
- 支持两轮分组：第一轮常规分组 + 第二轮基于第一轮结果惩罚重复单向喜欢
- 支持 `--pairing-mode`：1v1 配对；奇数总人数且男女差 1 时，允许 1 组三人，其余仍为 1v1
- 支持特权嘉宾（VIP）硬约束：`--privileged-guests`
- 支持独立嘉宾名单文件（姓名映射）：`--guest-map-file` / `--guest-map-sheet`
- 支持现场缺席：`--absent-guests`（姓名和 ID 可混输）
- 导出 JSON/CSV/Excel（`--export-xlsx`）

## 项目结构

```text
.
├── cli.py
├── interactive_gui.py
├── requirements.txt
├── src/
│   ├── parser_cn.py
│   ├── parser_ranking.py
│   ├── graph.py
│   ├── solver_heur.py
│   ├── solver_ilp.py
│   └── io_excel.py
├── 嘉宾偏好_第一轮.xlsx
├── 嘉宾偏好_第二轮.xlsx
├── 嘉宾偏好_第三轮.xlsx
├── 嘉宾名单.xlsx
├── 相亲分组工具.bat
└── 相亲分组工具.command
```

## 快速开始

### 1) 安装依赖

```bash
pip install -r requirements.txt
```

### 2) 命令行快速运行

```bash
python3 cli.py --input 嘉宾偏好_第一轮.xlsx --mode ranking --guest-map-file 嘉宾名单.xlsx --export-xlsx --verbose
```

### 3) 图形界面

- Windows：双击 `相亲分组工具.bat`
- macOS/Linux：双击 `相亲分组工具.command`

## 输入数据

### 偏好文件（`--input`）

- 默认 sheet：`偏好`（可用 `--sheet` 改）
- `ranking` 模式列：`嘉宾类型`、`编号`、`对象1ID`、`对象2ID`
  - 主体列（`编号`）支持混合填写：纯数字、`M1/F3`、中文名、英文名、别名
  - 也支持可选列 `嘉宾姓名`（有该列时优先按 `嘉宾姓名` 识别主体）
  - `对象1ID/对象2ID` 支持混合填写：`F3`/`M8`、纯数字、中文名、英文名、别名
  - 推荐搭配 `--guest-map-file` 使用姓名映射
- `text` 模式列：`嘉宾类型`、`编号`、`偏好描述`

### 嘉宾名单文件（可选，推荐）

- 参数：`--guest-map-file`（文件）+ `--guest-map-sheet`（sheet，默认 `嘉宾名单`）
- 建议列：
  - 必填：`嘉宾类型`、`编号`、`姓名`
  - 可选：`英文名`、`别名`（多个别名可用逗号分隔）
  - 可选：`是否到场`（是/否，空值默认到场）
- 用途：姓名展示、姓名/ID 混合输入解析（如 VIP、缺席名单）

## CLI 参数

### 必需参数

- `--input, -i`：输入 Excel 文件路径

### 输入参数

- `--sheet`：偏好 sheet（默认 `偏好`）
- `--mode`：`ranking` / `text`（默认 `ranking`）
- `--guest-map-file`：嘉宾名单文件路径（默认使用 `--input` 文件）
- `--guest-map-sheet`：嘉宾名单 sheet（默认 `嘉宾名单`）
- `--absent-guests`：缺席名单，逗号分隔，支持姓名或 ID（如 `张三,F8,M2`）

### 分组与约束

- `--two-by-two`：是否强制 2男2女（默认 `true`）
- `--strict-two-by-two`：严格模式；人数或性别不满足时直接报错（默认自动放宽）
- `--pairing-mode`：配对模式（1v1；奇数总人数且男女差 1 时允许 1 组三人）
- `--group-size`：常规分组时每组目标人数（默认 `4`）
- `--privileged-guests`：VIP 列表，逗号分隔，支持姓名或 ID

### 第二轮参数

- `--round-two`：开启第二轮分组
- `--first-round-file`：第一轮结果 JSON
- `--penalty-weight`：第一轮单向喜欢惩罚权重（默认 `-1.0`）

### 评分参数

- `--first-preference-weight`：第一偏好权重（默认 `2.0`）
- `--second-preference-weight`：第二偏好权重（默认 `1.0`）
- `--mutual-weight`：互相喜欢总权重（默认 `2.0`）

### 求解器参数

- `--solver`：`auto` / `heuristic` / `ilp`（默认 `auto`）
- `--seed`：随机种子
- `--max-iter`：启发式最大迭代（默认 `10000`）
- `--num-restarts`：启发式重启次数（默认 `5`）
- `--heur-algorithm`：`simulated_annealing` / `hill_climbing`
- `--ilp-time-limit`：ILP 超时秒数（默认 `300`）

### 输出与调试

- `--export-xlsx`：导出 Excel
- `--output-dir`：输出目录（默认 `outputs`）
- `--dry-run-parse`：仅解析不求解
- `--verbose`：详细日志

## 重要行为说明

- 第二轮不支持配对模式：`--round-two` 不能与 `--pairing-mode` 同时使用。
- `text` 模式暂不支持缺席重编号：使用缺席场景请优先 `ranking` 模式。
- 配对模式可行性：仅支持男女差值 `<= 1`；差值为 `1` 且总人数为奇数时，允许 1 组三人。
- VIP 硬约束：VIP 必须与至少一个自己喜欢的人同组；若输入偏好本身不可行会直接失败。
- 偏好主体/目标姓名匹配：支持中文名/英文名/别名；若重名无法唯一匹配会给出告警并按不可识别处理。

## 输出文件

默认输出到 `outputs/` 目录：

- 第一轮：`安排结果_第一轮.json/.csv/.xlsx`
- 第二轮：`安排结果_第二轮.json/.csv/.xlsx`
- 配对模式：`安排结果_双人配对.json/.csv/.xlsx`

## 使用范例（One-liner）

### 第一轮分组

```bash
python3 cli.py --input 嘉宾偏好_第一轮.xlsx --mode ranking --guest-map-file 嘉宾名单.xlsx --export-xlsx --verbose
```

### 第二轮分组

```bash
python3 cli.py --round-two --first-round-file outputs/安排结果_第一轮.json --input 嘉宾偏好_第二轮.xlsx --mode ranking --guest-map-file 嘉宾名单.xlsx --export-xlsx --verbose
```

### 双人配对（第三轮）

```bash
python3 cli.py --input 嘉宾偏好_第三轮.xlsx --mode ranking --guest-map-file 嘉宾名单.xlsx --pairing-mode --export-xlsx --verbose --privileged-guests M1,F1
```

### 指定名单 sheet

```bash
python3 cli.py --input 嘉宾偏好_第一轮.xlsx --mode ranking --guest-map-file 嘉宾名单.xlsx --guest-map-sheet 嘉宾名单 --export-xlsx
```

### 临时缺席（姓名/ID 混输）

```bash
python3 cli.py --input 嘉宾偏好_第一轮.xlsx --mode ranking --guest-map-file 嘉宾名单.xlsx --absent-guests 张三,F8,M2 --export-xlsx --verbose
```

### 缺席后仍强制 2男2女（不可行则失败）

```bash
python3 cli.py --input 嘉宾偏好_第一轮.xlsx --mode ranking --guest-map-file 嘉宾名单.xlsx --absent-guests 李二 --strict-two-by-two --export-xlsx
```

### VIP 使用姓名

```bash
python3 cli.py --input 嘉宾偏好_第一轮.xlsx --mode ranking --guest-map-file 嘉宾名单.xlsx --privileged-guests 王五,F3 --export-xlsx
```

### 仅解析检查

```bash
python3 cli.py --input 嘉宾偏好_第一轮.xlsx --mode ranking --dry-run-parse --verbose
```
