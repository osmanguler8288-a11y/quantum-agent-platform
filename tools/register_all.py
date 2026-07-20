"""
一键注册所有可用工具到 ToolRegistry + MCPClient。

用法：
    from tools.register_all import build_client
    mcp_client = build_client()
    result = mcp_client.call("bash", {"command": "echo hello"})
"""

from tools.tool_register import ToolRegistry
from agent.mcp_client import MCPClient

# ─── 导入所有工具函数 ───
from tools.bash.runner import run_bash
from tools.file_tools.runner import read_file, write_file, list_dir, delete_file
from tools.python_repl.runner import run_python
from tools.grep_tool.runner import grep_file
from tools.gaussian.runner import run_gaussian
from tools.eqv2.runner import run_eqv2
from tools.multiwfn.runner import run_multiwfn
from tools.humo_lumo.runner import run_homo_lumo
from tools.dip.runner import run_dipole


def build_registry() -> ToolRegistry:
    """构建并注册所有本地工具的 ToolRegistry"""
    registry = ToolRegistry()

    # ── 基础系统工具 ──────────────────────────────
    registry.register_function(
        name="bash",
        description="执行 Shell 命令。用于文件操作、脚本运行、进程管理等系统级操作。参数: command(必填), cwd(可选,工作目录), timeout(可选,超时秒数,默认300)",
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "要执行的 shell 命令"},
                "cwd": {"type": "string", "description": "工作目录，默认项目根"},
                "timeout": {"type": "integer", "description": "超时秒数，默认 300"},
            },
            "required": ["command"],
        },
        func=run_bash,
    )

    # ── 文件操作工具 ──────────────────────────────
    registry.register_function(
        name="read_file",
        description="读取文件内容。用于查看输入文件、计算结果、日志等。参数: path(必填,文件路径), max_lines(可选,最大行数,默认500)",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "max_lines": {"type": "integer", "description": "最大读取行数，默认 500"},
            },
            "required": ["path"],
        },
        func=read_file,
    )

    registry.register_function(
        name="write_file",
        description="写入内容到文件（自动创建父目录）。用于生成输入文件、保存结果等。参数: path(必填), content(必填), append(可选,是否追加,默认覆盖)",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "content": {"type": "string", "description": "要写入的内容"},
                "append": {"type": "boolean", "description": "是否追加写入，默认 False（覆盖）"},
            },
            "required": ["path", "content"],
        },
        func=write_file,
    )

    registry.register_function(
        name="list_dir",
        description="列出目录内容。用于浏览项目结构、查找文件。参数: path(可选,目录路径,默认当前目录), pattern(可选,文件名匹配,如'*.gjf')",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "目录路径，默认 '.'"},
                "pattern": {"type": "string", "description": "文件名匹配模式，如 '*.gjf', '*.log'"},
            },
            "required": [],
        },
        func=list_dir,
    )

    registry.register_function(
        name="delete_file",
        description="删除指定文件（不能删除目录）。参数: path(必填,文件路径)",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "要删除的文件路径"},
            },
            "required": ["path"],
        },
        func=delete_file,
    )

    # ── 数据处理工具 ──────────────────────────────
    registry.register_function(
        name="python_repl",
        description="执行 Python 代码进行数据处理。用于提取能量、计算 gap、单位换算、统计分析等。预导入了 math, json, re, statistics, Counter。参数: code(必填,Python代码), timeout(可选,默认10秒)",
        parameters={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python 代码"},
                "timeout": {"type": "integer", "description": "超时秒数，默认 10"},
            },
            "required": ["code"],
        },
        func=run_python,
    )

    # ── 文本搜索工具 ──────────────────────────────
    registry.register_function(
        name="grep_file",
        description="在文件中搜索匹配行（支持正则）。用于解析大型输出文件（Gaussian log 等），定位能量、频率、虚频等关键信息。预设模式: energy, homo_lumo, imag_freq, normal_termination, error_termination, convergence, dipole, thermo。参数: path(必填), pattern(必填), context_lines(可选,默认3), preset(可选,预设模式名)",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "pattern": {"type": "string", "description": "搜索模式（Python 正则表达式）"},
                "context_lines": {"type": "integer", "description": "每个匹配前后的上下文行数，默认 3"},
                "max_matches": {"type": "integer", "description": "最多返回匹配数，默认 50"},
                "preset": {"type": "string", "description": "预设搜索模式: energy, homo_lumo, imag_freq, normal_termination, error_termination, convergence, dipole, thermo"},
                "ignore_case": {"type": "boolean", "description": "是否忽略大小写，默认 True"},
            },
            "required": ["path"],
        },
        func=grep_file,
    )

    # ── 量子化学专业工具 ──────────────────────────
    registry.register_function(
        name="gaussian",
        description="运行 Gaussian 量子化学计算。参数: input_file(必填,Gaussian输入文件路径), output_file(必填,输出文件路径)",
        parameters={
            "type": "object",
            "properties": {
                "input_file": {"type": "string", "description": "Gaussian 输入文件路径 (.gjf)"},
                "output_file": {"type": "string", "description": "输出文件路径 (.log)"},
            },
            "required": ["input_file", "output_file"],
        },
        func=run_gaussian,
    )

    registry.register_function(
        name="eqv2",
        description="运行 EqV2 构象搜索。参数: input_file(必填), output_file(必填)",
        parameters={
            "type": "object",
            "properties": {
                "input_file": {"type": "string", "description": "输入文件路径"},
                "output_file": {"type": "string", "description": "输出文件路径"},
            },
            "required": ["input_file", "output_file"],
        },
        func=run_eqv2,
    )

    registry.register_function(
        name="multiwfn",
        description="运行 Multiwfn 波函数分析（HOMO/LUMO/键级/ESP等）。参数: input_file(必填,波函数文件路径), commands(必填,Multiwfn命令字符串)",
        parameters={
            "type": "object",
            "properties": {
                "input_file": {"type": "string", "description": "波函数文件路径 (.fchk, .wfn 等)"},
                "commands": {"type": "string", "description": "Multiwfn 交互命令字符串"},
            },
            "required": ["input_file", "commands"],
        },
        func=run_multiwfn,
    )

    registry.register_function(
        name="homo_lumo",
        description="从 Gaussian .fchk 文件中提取 HOMO/LUMO 轨道能量并计算能隙。用于分析分子稳定性、反应活性。参数: fchk_path(必填,.fchk文件路径), num_around(可选,能隙附近显示的轨道数,默认5)",
        parameters={
            "type": "object",
            "properties": {
                "fchk_path": {"type": "string", "description": "Gaussian .fchk 文件路径"},
                "num_around": {"type": "integer", "description": "能隙附近显示的轨道数，默认 5"},
            },
            "required": ["fchk_path"],
        },
        func=run_homo_lumo,
    )
    registry.register_function(
        name="dipole",
        description="从 Gaussian .out 文件中提取偶极矩（Dipole Moment）及可选的四极矩。用于分析分子电荷分布、极性。参数: out_path(必填,.out文件路径), extract_quadrupole(可选,是否提取四极矩), extract_traceless(可选,是否提取无迹四极矩)",
        parameters={
            "type": "object",
            "properties": {
                "out_path": {"type": "string", "description": "Gaussian .out 文件路径"},
                "extract_quadrupole": {"type": "boolean", "description": "是否同时提取四极矩，默认 False"},
                "extract_traceless": {"type": "boolean", "description": "是否同时提取无迹四极矩，默认 False"},
            },
            "required": ["out_path"],
        },
        func=run_dipole,
    )
    return registry


def build_client() -> MCPClient:
    """构建包含所有已注册工具的 MCPClient"""
    registry = build_registry()
    return MCPClient(registry)
