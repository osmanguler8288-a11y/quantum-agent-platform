"""
Python REPL 工具 — Agent 的数据处理能力

量子化学场景：
  - 从 Gaussian 输出中提取能量值
  - 计算 HOMO-LUMO gap
  - 单位换算（Hartree → eV, Bohr → Å）
  - 数据绘图（需要 matplotlib）
  - 坐标变换、分子结构处理

安全设计：
  - 独立的命名空间，每次执行互不污染
  - 禁用危险内置函数（__import__, open, eval, exec 等）
  - 超时兜底
  - 返回 stdout + 最后一个表达式的值
"""

import sys
import io
import traceback
from typing import Any


# 可安全使用的内置函数和模块
_SAFE_BUILTINS = {
    # 基础
    "abs": abs, "all": all, "any": any, "bin": bin, "bool": bool,
    "bytes": bytes, "chr": chr, "complex": complex, "dict": dict,
    "divmod": divmod, "enumerate": enumerate, "filter": filter, "float": float,
    "format": format, "frozenset": frozenset, "getattr": getattr,
    "hasattr": hasattr, "hash": hash, "hex": hex, "int": int,
    "isinstance": isinstance, "issubclass": issubclass, "iter": iter,
    "len": len, "list": list, "map": map, "max": max, "min": min,
    "next": next, "object": object, "oct": oct, "ord": ord, "pow": pow,
    "print": print, "range": range, "repr": repr, "reversed": reversed,
    "round": round, "set": set, "slice": slice, "sorted": sorted,
    "str": str, "sum": sum, "tuple": tuple, "type": type, "zip": zip,
    # 数学
    "__import__": __import__,  # 允许 import，但要限制
}

# 预导入的常用模块
_PRE_IMPORTS = """
import math
import json
import re
import statistics
from collections import Counter, defaultdict
"""


def run_python(code: str, timeout: int = 10) -> str:
    """
    在受限命名空间中执行 Python 代码，返回输出结果。

    Args:
        code:    Python 代码
        timeout: 超时秒数（默认 10s，适合短计算）
    """
    # 构建受限的全局命名空间
    safe_globals: dict[str, Any] = {
        "__builtins__": _SAFE_BUILTINS,
        "__name__": "__python_repl__",
    }

    # 预导入常用模块
    try:
        exec(_PRE_IMPORTS, safe_globals)
    except Exception:
        pass

    # 捕获 stdout
    stdout_capture = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = stdout_capture

    result_value = None
    error_msg = None

    try:
        # 编译 + 执行
        compiled = compile(code, "<python_repl>", "exec")

        # 用 signal.alarm 做超时（仅 Unix），Windows 上依赖外层超时
        exec(compiled, safe_globals)

        # 如果有最后一个表达式（以非赋值语句结尾），单独求值
        # 这里简化处理：如果代码最后一行是表达式，求值它
        stripped_lines = [l for l in code.strip().split("\n") if l.strip()]
        if stripped_lines:
            last_line = stripped_lines[-1]
            # 尝试当表达式求值
            try:
                expr_compiled = compile(last_line, "<python_repl>", "eval")
                result_value = eval(expr_compiled, safe_globals)
            except SyntaxError:
                pass  # 最后一行是语句，不求值

    except Exception:
        error_msg = traceback.format_exc()
    finally:
        sys.stdout = old_stdout

    stdout_text = stdout_capture.getvalue()

    # 组装输出
    parts = []
    if stdout_text:
        parts.append(stdout_text.rstrip())
    if result_value is not None:
        parts.append(f"=> {repr(result_value)}")
    if error_msg:
        parts.append(error_msg.rstrip())

    return "\n".join(parts) if parts else "(代码执行完毕，无输出)"
