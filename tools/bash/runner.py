"""
Bash 工具 — Agent 最基础的操作能力

安全设计：
  - 工作目录默认锁定在项目根
  - 超时兜底（防止命令卡死）
  - 危险命令告警（rm -rf / 等，但不阻止，因为用户是研究者本人）
"""

import subprocess
import os

# 项目根目录，所有 bash 命令默认在此执行
PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)

# 高危命令模式（只告警，不阻止）
_DANGEROUS_PATTERNS = [
    "rm -rf /", "mkfs.", "dd if=", ":(){ :|:& };:",
    "> /dev/sda", "chmod 777 /",
]


def run_bash(command: str, cwd: str = None, timeout: int = 300) -> str:
    """
    执行 shell 命令，返回 stdout + stderr。

    Args:
        command: 要执行的 shell 命令
        cwd:     工作目录（默认项目根目录）
        timeout: 超时秒数（默认 300）

    Returns:
        命令的标准输出 + 标准错误（如有）
    """
    work_dir = cwd or PROJECT_ROOT

    # 高危命令告警
    for pattern in _DANGEROUS_PATTERNS:
        if pattern in command:
            print(f"[bash] [WARN] dangerous pattern: '{pattern}'")

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=work_dir,
            timeout=timeout,
        )
        output = result.stdout
        if result.stderr:
            output += "\n[stderr]\n" + result.stderr
        if result.returncode != 0:
            output += f"\n[退出码: {result.returncode}]"

        return output or "(命令执行成功，无输出)"

    except subprocess.TimeoutExpired:
        return f"[错误] 命令超时 ({timeout}s): {command}"
    except FileNotFoundError:
        return f"[错误] 命令不存在: {command.split()[0] if command else command}"
    except Exception as e:
        return f"[错误] 命令执行异常: {e}"
