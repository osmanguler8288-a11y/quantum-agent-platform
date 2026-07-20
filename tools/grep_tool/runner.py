"""
Grep 工具 — 解析大型输出文件的专用工具

量子化学场景：
  - Gaussian 输出文件动辄几百 MB，Agent 不能整个读
  - 需要精准定位：能量收敛、虚频、HOMO/LUMO 轨道能等
  - 支持正则 + 上下文行
"""

import re
import os


# Gaussian 输出中常见的标志行（预置搜索模式）
GAUSSIAN_PATTERNS = {
    "energy": r"SCF Done:.*=\s*(-?\d+\.\d+)",
    "homo_lumo": r"(Alpha|Beta)\s+occ\. eigenvalues",
    "imag_freq": r"Frequencies --\s*(-?\d+\.\d+)",
    "normal_termination": r"Normal termination",
    "error_termination": r"Error termination",
    "optimized_params": r"Optimized Parameters",
    "convergence": r"Maximum Force|RMS\s+Force|Maximum Displacement|RMS\s+Displacement",
    "dipole": r"Dipole moment",
    "thermo": r"Thermal correction|Sum of electronic",
}


def grep_file(path: str, pattern: str,
              context_lines: int = 3,
              max_matches: int = 50,
              preset: str = None,
              ignore_case: bool = True) -> str:
    """
    在文件中搜索匹配行，支持正则和预置模式。

    Args:
        path:          文件路径
        pattern:       搜索模式（Python 正则）
        context_lines: 每个匹配前后显示的行数
        max_matches:   最多返回多少个匹配
        preset:        预置搜索模式名（如 "energy", "imag_freq"），
                       如果指定则覆盖 pattern
        ignore_case:   是否忽略大小写
    """
    # 如果指定了 preset，用预置的 pattern
    actual_pattern = pattern
    if preset and preset in GAUSSIAN_PATTERNS:
        actual_pattern = GAUSSIAN_PATTERNS[preset]
    elif preset and preset not in GAUSSIAN_PATTERNS:
        return f"[错误] 未知的预置模式: '{preset}'。可用: {list(GAUSSIAN_PATTERNS.keys())}"

    if not os.path.exists(path):
        return f"[错误] 文件不存在: {path}"
    if not os.path.isfile(path):
        return f"[错误] 不是文件: {path}"

    try:
        flags = re.IGNORECASE if ignore_case else 0
        regex = re.compile(actual_pattern, flags)

        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        # 找所有匹配行号
        match_indices = []
        for i, line in enumerate(lines):
            if regex.search(line):
                match_indices.append(i)

        if not match_indices:
            return f"(未找到匹配 '{actual_pattern}' — 已搜索 {len(lines)} 行)"

        # 收集匹配块（含上下文）
        result_blocks = []
        for idx in match_indices[:max_matches]:
            start = max(0, idx - context_lines)
            end = min(len(lines), idx + context_lines + 1)

            block_lines = []
            for j in range(start, end):
                prefix = ">> " if j == idx else "  "
                line_num = j + 1
                block_lines.append(f"{prefix}{line_num:6d}| {lines[j].rstrip()}")

            result_blocks.append("\n".join(block_lines))

        output = f"搜索 '{actual_pattern}' — 找到 {len(match_indices)} 处匹配"
        if len(match_indices) > max_matches:
            output += f"（仅显示前 {max_matches} 处）"
        output += ":\n\n" + "\n\n---\n\n".join(result_blocks)

        return output

    except re.error as e:
        return f"[错误] 正则表达式无效: {e}"
    except Exception as e:
        return f"[错误] 搜索失败: {e}"
