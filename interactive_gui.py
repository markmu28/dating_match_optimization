#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
相亲活动分组优化工具 - 交互式图形界面
用户可以通过简单的GUI界面进行配置和运行
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import subprocess
import os
import sys
from pathlib import Path
import threading
import queue
import time

class DatingMatchGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("相亲活动分组优化工具")
        self.root.geometry("1000x800")
        
        # 变量
        self.input_file = tk.StringVar()
        self.group_size = tk.StringVar(value="4")
        self.round_number = tk.StringVar(value="1")
        self.pairing_mode = tk.BooleanVar(value=False)
        self.export_xlsx = tk.BooleanVar(value=True)
        self.solver_choice = tk.StringVar(value="auto")
        self.mode_choice = tk.StringVar(value="ranking")
        
        # 运行状态
        self.is_running = False
        self.output_queue = queue.Queue()
        self.process = None
        
        self.setup_ui()
        
    def setup_ui(self):
        """设置用户界面"""
        # 标题
        title_frame = ttk.Frame(self.root)
        title_frame.pack(pady=20)
        
        title_label = ttk.Label(title_frame, text="相亲活动分组优化工具", 
                               font=("Arial", 20, "bold"))
        title_label.pack()
        
        subtitle_label = ttk.Label(title_frame, text="Dating Match Optimization System", 
                                  font=("Arial", 12))
        subtitle_label.pack()
        
        # 主框架 - 使用PanedWindow分割界面
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(padx=20, pady=20, fill="both", expand=True)
        
        # 左侧控制面板
        control_frame = ttk.Frame(main_paned)
        main_paned.add(control_frame, weight=1)
        
        # 右侧输出面板
        output_frame = ttk.Frame(main_paned)
        main_paned.add(output_frame, weight=1)
        
        # ===== 左侧控制面板 =====
        # 输入文件选择
        file_frame = ttk.LabelFrame(control_frame, text="输入文件", padding=10)
        file_frame.pack(fill="x", pady=5)
        
        file_input_frame = ttk.Frame(file_frame)
        file_input_frame.pack(fill="x")
        
        # 文件路径输入框
        self.file_entry = ttk.Entry(file_input_frame, textvariable=self.input_file)
        self.file_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        # 选择文件按钮，指定宽度确保文字显示完整
        ttk.Button(file_input_frame, text="选择文件", command=self.select_file, width=10).pack(side="right")
        
        ttk.Label(file_frame, text="支持格式: Excel (.xlsx) 或 CSV (.csv)", 
                 font=("Arial", 9), foreground="gray").pack(anchor="w", pady=(5, 0))
        
        # 配置选项
        config_frame = ttk.LabelFrame(control_frame, text="配置选项", padding=10)
        config_frame.pack(fill="x", pady=5)
        
        # 第一行配置
        row1_frame = ttk.Frame(config_frame)
        row1_frame.pack(fill="x", pady=5)
        
        ttk.Label(row1_frame, text="每组人数:").pack(side="left")
        ttk.Entry(row1_frame, textvariable=self.group_size, width=10).pack(side="left", padx=(5, 20))
        
        ttk.Label(row1_frame, text="第几轮:").pack(side="left")
        round_combo = ttk.Combobox(row1_frame, textvariable=self.round_number, 
                                  values=["1", "2"], width=8, state="readonly")
        round_combo.pack(side="left", padx=(5, 20))
        
        # 第二行配置
        row2_frame = ttk.Frame(config_frame)
        row2_frame.pack(fill="x", pady=5)
        
        ttk.Checkbutton(row2_frame, text="配对模式 (1v1配对)", 
                       variable=self.pairing_mode).pack(side="left", padx=(0, 20))
        
        ttk.Checkbutton(row2_frame, text="导出Excel文件", 
                       variable=self.export_xlsx).pack(side="left")
        
        # 第三行配置
        row3_frame = ttk.Frame(config_frame)
        row3_frame.pack(fill="x", pady=5)
        
        ttk.Label(row3_frame, text="求解器:").pack(side="left")
        solver_combo = ttk.Combobox(row3_frame, textvariable=self.solver_choice,
                                   values=["auto", "heuristic", "ilp"], width=12, state="readonly")
        solver_combo.pack(side="left", padx=(5, 20))
        
        ttk.Label(row3_frame, text="数据模式:").pack(side="left")
        mode_combo = ttk.Combobox(row3_frame, textvariable=self.mode_choice,
                                 values=["ranking", "text"], width=12, state="readonly")
        mode_combo.pack(side="left", padx=(5, 0))
        
        # 说明文本
        help_frame = ttk.LabelFrame(control_frame, text="说明", padding=10)
        help_frame.pack(fill="both", expand=True, pady=5)
        
        help_text = """使用说明:
1. 选择包含偏好数据的Excel或CSV文件
2. 设置每组人数（默认4人，最后一组可能少于此值）
3. 选择是第几轮分组（第二轮需要第一轮结果文件）
4. 配对模式将生成1v1配对，否则生成多人分组
5. 数据模式: ranking=ID排名模式，text=中文描述解析
6. 点击"开始分组"运行优化算法

输出文件将保存在 outputs/ 目录下，包含分组结果和统计信息。"""
        
        help_label = ttk.Label(help_frame, text=help_text, justify="left", 
                              font=("Arial", 10), foreground="darkblue")
        help_label.pack(anchor="w")
        
        # 控制按钮
        button_frame = ttk.Frame(control_frame)
        button_frame.pack(fill="x", pady=20)
        
        self.start_button = ttk.Button(button_frame, text="开始分组", command=self.start_optimization,
                                      style="Accent.TButton", width=10)
        self.start_button.pack(side="right", padx=(10, 0))
        
        self.stop_button = ttk.Button(button_frame, text="停止运行", command=self.stop_optimization,
                                     state="disabled", width=10)
        self.stop_button.pack(side="right", padx=(10, 0))
        
        ttk.Button(button_frame, text="清空日志", command=self.clear_log, width=8).pack(side="left")
        ttk.Button(button_frame, text="退出", command=self.root.quit, width=6).pack(side="right")
        
        # 进度状态
        progress_frame = ttk.LabelFrame(control_frame, text="运行状态", padding=10)
        progress_frame.pack(fill="x", pady=5)
        
        self.progress_var = tk.StringVar(value="准备就绪")
        ttk.Label(progress_frame, textvariable=self.progress_var).pack(anchor="w")
        
        self.progress_bar = ttk.Progressbar(progress_frame, mode='indeterminate')
        self.progress_bar.pack(fill="x", pady=(5, 0))
        
        # ===== 右侧输出面板 =====
        output_label_frame = ttk.LabelFrame(output_frame, text="运行日志 (实时输出)", padding=10)
        output_label_frame.pack(fill="both", expand=True)
        
        # 创建滚动文本框
        self.log_text = scrolledtext.ScrolledText(output_label_frame, 
                                                 font=("Consolas", 10),
                                                 bg="black", fg="lightgreen",
                                                 wrap=tk.WORD, height=30)
        self.log_text.pack(fill="both", expand=True)
        
        # 添加初始欢迎信息
        welcome_msg = """相亲活动分组优化工具 - 运行日志

准备就绪，等待开始运行...

"""
        self.log_text.insert(tk.END, welcome_msg)
        self.log_text.configure(state='disabled')  # 设为只读
        
        # 启动输出监控
        self.monitor_output()
        
    def select_file(self):
        """选择输入文件"""
        file_path = filedialog.askopenfilename(
            title="选择偏好数据文件",
            filetypes=[
                ("Excel文件", "*.xlsx"),
                ("CSV文件", "*.csv"),
                ("所有文件", "*.*")
            ]
        )
        if file_path:
            self.input_file.set(file_path)
    
    def validate_inputs(self):
        """验证输入参数"""
        if not self.input_file.get():
            messagebox.showerror("错误", "请选择输入文件")
            return False
            
        if not os.path.exists(self.input_file.get()):
            messagebox.showerror("错误", "输入文件不存在")
            return False
            
        try:
            group_size = int(self.group_size.get())
            if group_size < 2:
                messagebox.showerror("错误", "每组人数至少为2人")
                return False
        except ValueError:
            messagebox.showerror("错误", "请输入有效的组大小数字")
            return False
            
        return True
    
    def build_command(self):
        """构建CLI命令"""
        cmd = [sys.executable, "cli.py"]
        
        # 必需参数
        cmd.extend(["--input", self.input_file.get()])
        cmd.append("--verbose")  # 默认启用详细输出
        
        # 确保outputs目录存在
        os.makedirs("outputs", exist_ok=True)
        
        # 可选参数
        cmd.extend(["--group-size", self.group_size.get()])
        cmd.extend(["--mode", self.mode_choice.get()])
        cmd.extend(["--solver", self.solver_choice.get()])
        
        if self.pairing_mode.get():
            cmd.append("--pairing-mode")
        
        if self.export_xlsx.get():
            cmd.append("--export-xlsx")
        
        # 第二轮参数（暂时简化处理）
        if self.round_number.get() == "2":
            # 寻找第一轮结果文件
            first_round_files = [
                "outputs/安排结果_第一轮.json",
                "outputs/安排结果.json"
            ]
            first_round_file = None
            for f in first_round_files:
                if os.path.exists(f):
                    first_round_file = f
                    break
            
            if first_round_file:
                cmd.extend(["--round-two", "--first-round-file", first_round_file])
            else:
                messagebox.showwarning("警告", 
                    "未找到第一轮结果文件，将按第一轮模式运行")
        
        return cmd
    
    def add_log(self, text, tag=None):
        """添加日志到文本框"""
        self.log_text.configure(state='normal')
        
        # 添加时间戳
        timestamp = time.strftime("[%H:%M:%S] ")
        if not text.startswith('\n') and self.log_text.get("end-2c", "end-1c") != '\n':
            self.log_text.insert(tk.END, '\n')
        self.log_text.insert(tk.END, timestamp + text)
        
        # 自动滚动到底部
        self.log_text.see(tk.END)
        self.log_text.configure(state='disabled')
        
    def clear_log(self):
        """清空日志"""
        self.log_text.configure(state='normal')
        self.log_text.delete(1.0, tk.END)
        welcome_msg = """相亲活动分组优化工具 - 运行日志

准备就绪，等待开始运行...

"""
        self.log_text.insert(tk.END, welcome_msg)
        self.log_text.configure(state='disabled')
        
    def monitor_output(self):
        """监控输出队列并更新UI"""
        try:
            while True:
                line = self.output_queue.get_nowait()
                self.add_log(line)
        except queue.Empty:
            pass
        
        # 每100ms检查一次
        self.root.after(100, self.monitor_output)
        
    def read_process_output(self, process):
        """读取进程输出并放入队列"""
        try:
            while True:
                line = process.stdout.readline()
                if line:
                    self.output_queue.put(line.rstrip())
                elif process.poll() is not None:
                    # 进程已结束，读取剩余输出
                    remaining = process.stdout.read()
                    if remaining:
                        for remaining_line in remaining.splitlines():
                            if remaining_line.strip():
                                self.output_queue.put(remaining_line.strip())
                    break
                    
        except Exception as e:
            self.output_queue.put(f"读取输出时出错: {str(e)}")
            
    def stop_optimization(self):
        """停止运行"""
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.add_log("用户停止了运行")
            self.progress_var.set("已停止")
            self.progress_bar.stop()
            self.is_running = False
            self.start_button.configure(state="normal")
            self.stop_button.configure(state="disabled")

    def run_optimization(self):
        """在后台线程中运行优化"""
        try:
            cmd = self.build_command()
            
            # 更新状态
            self.progress_var.set("正在运行优化算法...")
            self.progress_bar.start()
            self.is_running = True
            
            self.add_log("开始运行分组优化...")
            self.add_log(f"执行命令: {' '.join(cmd)}")
            
            # 启动进程，实时捕获输出
            # 添加环境变量强制Python无缓冲输出
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
            env['PYTHONIOENCODING'] = 'utf-8'
            
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # 合并stderr到stdout
                text=True,
                encoding='utf-8',
                cwd=os.getcwd(),
                bufsize=0,  # 无缓冲
                universal_newlines=True,
                env=env
            )
            
            # 启动输出读取线程
            output_thread = threading.Thread(
                target=self.read_process_output, 
                args=(self.process,), 
                daemon=True
            )
            output_thread.start()
            
            # 等待进程完成
            return_code = self.process.wait()
            
            # 停止进度条
            self.progress_bar.stop()
            self.is_running = False
            self.start_button.configure(state="normal")
            self.stop_button.configure(state="disabled")
            
            if return_code == 0:
                self.progress_var.set("优化完成！结果已保存到 outputs/ 目录")
                self.add_log("✅ 分组优化完成！")
                self.add_log("📁 结果文件已保存到 outputs/ 目录")
                messagebox.showinfo("成功", "分组优化完成！\n\n结果文件已保存到 outputs/ 目录")
            else:
                self.progress_var.set("运行失败")
                self.add_log(f"❌ 运行失败，退出码: {return_code}")
                
        except Exception as e:
            self.progress_bar.stop()
            self.progress_var.set("运行出错")
            self.is_running = False
            self.start_button.configure(state="normal")
            self.stop_button.configure(state="disabled")
            error_msg = f"运行出错: {str(e)}"
            self.add_log(f"❌ {error_msg}")
            messagebox.showerror("错误", error_msg)
    
    def start_optimization(self):
        """开始优化"""
        if not self.validate_inputs():
            return
            
        if self.is_running:
            messagebox.showwarning("警告", "程序正在运行中，请稍候...")
            return
        
        # 更新按钮状态
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        
        # 在后台线程中运行，避免界面卡死
        thread = threading.Thread(target=self.run_optimization, daemon=True)
        thread.start()

def main():
    """主函数"""
    # 设置工作目录为脚本所在目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    # 创建GUI
    root = tk.Tk()
    app = DatingMatchGUI(root)
    
    # 设置样式
    style = ttk.Style()
    try:
        # 尝试使用更现代的主题
        style.theme_use('clam')
    except:
        pass
    
    # 运行GUI
    root.mainloop()

if __name__ == "__main__":
    main()