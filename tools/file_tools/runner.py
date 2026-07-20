"""
File Tools — 文件读写（Agent 操作文件系统的安全入口）

比 bash 更受控：只能做明确的文件操作，不能执行任意命令。
"""

import os
import glob as glob_module


def read_file(path: str, max_lines: int = 500) -> str:
    """
    读取文件内容。

    Args:
        path:     文件路径（相对路径基于项目根目录）
        max_lines: 最大读取行数，防止大文件撑爆上下文
    """
    if not os.path.exists(path):
        return f"[错误] 文件不存在: {path}"
    if not os.path.isfile(path):
        return f"[错误] 不是文件: {path}"

    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        total = len(lines)
        if total <= max_lines:
            return "".join(lines)

        # 超长文件：返回头尾各一半
        half = max_lines // 2
        head = "".join(lines[:half])
        tail = "".join(lines[-half:])
        return (
            f"{head}"
            f"\n... [省略中间 {total - max_lines} 行] ...\n"
            f"{tail}"
        )
    except Exception as e:
        return f"[错误] 读取文件失败: {e}"


def write_file(path: str, content: str, append: bool = False) -> str:
    """
    写入内容到文件（自动创建父目录）。

    Args:
        path:   文件路径
        content: 要写入的内容
        append:  True=追加写入, False=覆盖写入
    """
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        mode = "a" if append else "w"
        with open(path, mode, encoding="utf-8") as f:
            f.write(content)
        action = "追加" if append else "写入"
        return f"已{action} {len(content)} 字符到 {path}"
    except Exception as e:
        return f"[错误] 写入文件失败: {e}"


def list_dir(path: str = ".", pattern: str = "*") -> str:
    """
    列出目录内容。

    Args:
        path:    目录路径（默认当前目录）
        pattern: 文件名匹配模式（如 "*.gjf", "*.log"）
    """
    if not os.path.exists(path):
        return f"[错误] 目录不存在: {path}"
    if not os.path.isdir(path):
        return f"[错误] 不是目录: {path}"

    try:
        search_pattern = os.path.join(path, pattern)
        items = glob_module.glob(search_pattern)
        if not items:
            return f"(空 — 没有匹配 '{pattern}' 的文件)"

        lines = []
        for item in sorted(items):
            stat = os.stat(item)
            size_kb = stat.st_size / 1024
            type_tag = "[DIR]" if os.path.isdir(item) else "[FILE]"
            item_name = os.path.basename(item)
            lines.append(f"  {type_tag} {item_name} ({size_kb:.1f} KB)")

        return f"{path}\\ （{len(lines)} 项）:\n" + "\n".join(lines)
    except Exception as e:
        return f"[错误] 列出目录失败: {e}"


def delete_file(path: str) -> str:
    """删除文件（不删目录）"""
    if not os.path.exists(path):
        return f"[错误] 文件不存在: {path}"
    if os.path.isdir(path):
        return f"[错误] 是目录而非文件，请用 bash 删除: {path}"
    try:
        os.remove(path)
        return f"已删除: {path}"
    except Exception as e:
        return f"[错误] 删除失败: {e}"
