# 第六课：真实工具接入 — subprocess 调量子化学程序

## 本课目标

- 用 `subprocess` 调起真实的命令行程序（Gaussian、EqV2、Multiwfn）
- 理解进程管理：超时、错误捕获、输出解析
- 把 fake MCPClient 替换成真实版本
- 子进程生命周期管理

## 前置要求

- 第五课完成（Agent 闭环跑通）
- 至少有一个量子化学工具装在本机（g16 / multiwfn / eqv2 任意一个即可学习）

---

## 6.1 subprocess 是什么

Python 里执行外部命令就靠 `subprocess`。相当于 Go 的 `exec.Command`。

```go
// Go
cmd := exec.Command("g16", "input.gjf")
output, err := cmd.CombinedOutput()
```

```python
# Python
import subprocess
result = subprocess.run(
    ["g16", "input.gjf"],
    capture_output=True,
    text=True,
)
print(result.stdout)    # 标准输出
print(result.stderr)    # 标准错误
print(result.returncode)  # 退出码，0 = 成功
```

**`subprocess.run` 的参数：**

| 参数 | 含义 | Go 对照 |
|------|------|---------|
| `["g16", "input.gjf"]` | 命令 + 参数列表 | `exec.Command("g16", "input.gjf")` |
| `capture_output=True` | 捕获 stdout + stderr | `cmd.CombinedOutput()` |
| `text=True` | 返回 str 而非 bytes | Go 默认就是 string |
| `timeout=3600` | 超时秒数，超时抛异常 | `context.WithTimeout()` |
| `cwd="/path"` | 工作目录 | `cmd.Dir = "/path"` |

---

## 6.2 工具目录已有骨架，逐个填肉

你项目里 `tools/` 已经有三个子包。本课把骨架填成能真正调命令行的代码。

### 6.2.1 Gaussian Runner

打开 [tools/gaussian/runner.py](../tools/gaussian/runner.py)，改成：

```python
import subprocess
import os


def run_gaussian(input_file: str, work_dir: str = "./data/processed") -> str:
    """执行 Gaussian 计算，返回输出文本"""
    os.makedirs(work_dir, exist_ok=True)

    result = subprocess.run(
        ["g16", input_file],
        capture_output=True,
        text=True,
        timeout=3600,   # Gaussian 可能跑很久
        cwd=work_dir,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Gaussian 异常退出: code={result.returncode}\n"
            f"stderr: {result.stderr[:500]}"
        )

    return result.stdout


def check_normal_termination(output: str) -> bool:
    """Gaussian 正常结束的标志"""
    return "Normal termination" in output
```

**`os.makedirs(work_dir, exist_ok=True)`**：递归创建目录，`exist_ok=True` 是指已存在不报错——Go 的 `os.MkdirAll(path, 0755)`。

**`raise RuntimeError(...)`**：主动抛异常。Go 里是 `return nil, fmt.Errorf(...)`，Python 是 `raise XxxError(...)`。RuntimeError 是 Python 内置的通用异常。

### 6.2.2 Multiwfn Runner

Multiwfn 是交互式程序，需要把命令通过 stdin 管道传进去：

打开 [tools/multiwfn/runner.py](../tools/multiwfn/runner.py)：

```python
import subprocess


def run_multiwfn(input_file: str, commands: str, work_dir: str = "./data/processed") -> str:
    """执行 Multiwfn 分析
    input_file: .fchk 或 .wfn 路径
    commands: Multiwfn 的键盘命令序列，如 "18\\n1\\n" 表示选功能18再选1
    """
    result = subprocess.run(
        ["multiwfn", input_file],
        input=commands,            # 通过 stdin 传入命令
        capture_output=True,
        text=True,
        timeout=600,
        cwd=work_dir,
    )
    return result.stdout


def make_homo_command() -> str:
    """生成计算 HOMO 的 Multiwfn 命令序列"""
    # 功能0=显示信息, 功能200=轨道能量, etc.
    # 这里只是示例，实际要根据 Multiwfn 手册调整
    return "200\n1\nq\n"  # 功能200 → 输出轨道能量 → 退出
```

**`input=commands`**：subprocess 把字符串通过 stdin 管道传给子进程。相当于：

```bash
echo -e "200\n1\nq" | multiwfn molecule.fchk
```

### 6.2.3 EqV2 Runner

打开 [tools/eqv2/runner.py](../tools/eqv2/runner.py)：

```python
import subprocess


def run_eqv2(input_file: str, output_file: str = "",
             n_conformers: int = 10, work_dir: str = "./data/processed") -> str:
    """执行 EqV2 构象搜索"""
    cmd = ["eqv2", input_file, "-n", str(n_conformers)]
    if output_file:
        cmd.extend(["-o", output_file])

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,
        cwd=work_dir,
    )
    return result.stdout
```

`cmd.extend(["-o", output_file])`：给命令列表加更多参数。`list.extend()` 就是 Go 的 `append(slice, items...)`。

### 6.2.4 输出解析器

[tools/eqv2/parser.py](../tools/eqv2/parser.py)：

```python
import re


def parse_conformers(output: str) -> list[dict]:
    """从 EqV2 输出中提取构象列表"""
    conformers = []
    for line in output.split("\n"):
        if "Conformer" in line and "energy" in line.lower():
            parts = line.split()
            conformers.append({
                "name": parts[0] + parts[1] if len(parts) >= 2 else line.strip(),
                "energy": float(parts[-1]) if parts else 0.0,
            })
    return conformers
```

[tools/multiwfn/descriptor.py](../tools/multiwfn/descriptor.py)：

```python
def extract_orbital_energies(output: str) -> dict:
    """从 Multiwfn 轨道能量输出中提取 HOMO/LUMO"""
    homo = lumo = None
    for line in output.split("\n"):
        if "HOMO" in line and "eV" in line:
            parts = line.split()
            for i, p in enumerate(parts):
                if "HOMO" in p and i + 1 < len(parts):
                    try:
                        homo = float(parts[i + 1])
                    except ValueError:
                        pass
    return {"homo": homo, "lumo": lumo}
```

`re`（正则表达式）和 `split()` 是文本解析的两种主要方式。`split()` 是简单粗暴按空格/换行切分；`re` 用于复杂模式。这里先用 split 足够了。

---

## 6.3 改造 MCPClient：从 fake 到真实

[agent/mcp_client.py](../agent/mcp_client.py) 里面的 `_call_local` 方法，现在替换成真正调工具：

```python
import subprocess
from tools.gaussian.runner import run_gaussian
from tools.multiwfn.runner import run_multiwfn
from tools.eqv2.runner import run_eqv2


class MCPClient:
    def __init__(self):
        self.servers: dict[str, str] = {}

    def call(self, tool_name: str, params: dict) -> dict:
        server = self.servers.get(tool_name, "local")

        if server == "local":
            return self._call_local(tool_name, params)
        else:
            return self._call_remote(server, tool_name, params)

    def _call_local(self, tool_name: str, params: dict) -> dict:
        """本地 subprocess 调用工具"""
        print(f"[mcp] calling {tool_name} with {params}")

        try:
            if tool_name == "gaussian":
                output = run_gaussian(
                    input_file=params.get("input", ""),
                    work_dir=params.get("work_dir", "./data/processed"),
                )
                return {"status": "success", "tool": tool_name, "output": output}

            elif tool_name == "multiwfn":
                output = run_multiwfn(
                    input_file=params.get("input", ""),
                    commands=params.get("commands", "200\nq\n"),
                    work_dir=params.get("work_dir", "./data/processed"),
                )
                return {"status": "success", "tool": tool_name, "output": output}

            elif tool_name == "eqv2":
                output = run_eqv2(
                    input_file=params.get("input", ""),
                    n_conformers=params.get("n_conformers", 10),
                    work_dir=params.get("work_dir", "./data/processed"),
                )
                return {"status": "success", "tool": tool_name, "output": output}

            else:
                return {
                    "status": "error",
                    "message": f"未知工具: {tool_name}",
                }

        except subprocess.TimeoutExpired:
            return {"status": "error", "message": f"{tool_name} 执行超时"}
        except FileNotFoundError:
            return {"status": "error", "message": f"{tool_name} 程序未安装或不在 PATH 中"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _call_remote(self, server: str, tool_name: str, params: dict) -> dict:
        raise NotImplementedError("远程 MCP server 调用暂未实现")
```

**设计要点：**

- 所有工具调用的错误都被包成 `{"status": "error", ...}` 返回，不会让上层崩溃
- Executor 拿到 `status == "error"` 就知道该重试还是跳过
- 新增工具时，在 `_call_local` 里加一个 `elif` 分支就行

---

## 6.4 输入文件生成

Gaussian 需要 `.gjf` 输入文件。加一个生成器：

[tools/utils/file_io.py](../tools/utils/file_io.py) 里追加：

```python
def generate_gaussian_input(molecule: str, method: str = "B3LYP",
                            basis: str = "6-31G(d)", action: str = "sp",
                            charge: int = 0, spin: int = 1,
                            output_path: str = "input.gjf") -> str:
    """生成 Gaussian 输入文件"""
    action_keyword = {"opt": "opt", "sp": "", "freq": "freq"}.get(action, "")

    content = f"""%chk={molecule}.chk
# {method}/{basis} {action_keyword}

{molecule} {action}

{charge} {spin}
(molecule: {molecule}, need real coordinates)
"""
    with open(output_path, "w") as f:
        f.write(content)
    return output_path
```

这就是一个模板填充——把参数扔进输入文件模板。实际使用时分子坐标需要从别处获取（数据库、SMILES、xyz 文件等）。

---

## 6.5 如果你本地没有装工具怎么办

没有 Gaussian/Multiwfn/EqV2 照样可以验证框架。写一个 fake 命令行脚本：

```python
# tools/fake_tool.py — 模拟工具输出
import sys
print("Normal termination of Gaussian")
print("SCF Done: E(RB3LYP) = -154.123456789")
print("HOMO energy: -0.28765 a.u.")
```

然后在 MCPClient 里用 `python3 tools/fake_tool.py` 代替 `g16`，验证 subprocess 调用链路是否正确。

```python
result = subprocess.run(
    ["python3", "tools/fake_tool.py"],
    capture_output=True,
    text=True,
)
# result.stdout = "Normal termination..."
# 你的 parser 能正常工作吗？
```

---

## 6.6 工具调用的完整流程

```
Executor
  → MCPClient.call("gaussian", {"input": "ethanol.gjf", "action": "opt"})
    → _call_local()
      → run_gaussian("ethanol.gjf", "./data/processed")
        → subprocess.run(["g16", "ethanol.gjf"], ...)
          → g16 启动，执行计算
          → stdout: "Normal termination..."
        → return result.stdout
      → return {"status": "success", "output": "...", "tool": "gaussian"}
    → Executor 收到结果，写入 state.results
```

---

## 6.7 本课检查清单

- [ ] 能用 `subprocess.run` 在终端外调起一个命令行程序
- [ ] 理解 `capture_output`、`text`、`timeout`、`cwd` 四个参数
- [ ] Gaussian/Multiwfn/EqV2 至少跑通一个（或跑通 fake 脚本验证链路）
- [ ] MCPClient._call_local 里能正确分发到不同工具 runner
- [ ] 工具执行出错时返回 error dict 而不是崩溃

---

## 6.8 常见报错

| 报错 | 原因 | 解决 |
|------|------|------|
| `FileNotFoundError: g16` | Gaussian 不在 PATH | `which g16` 确认安装路径，或用绝对路径 |
| `TimeoutExpired` | 计算时间超过了 timeout | 增大 timeout 或检查输入文件 |
| `Permission denied` | 输入文件不可读 | `chmod 644 input.gjf` |
| 输出解析结果为空 | parser 的 key 和实际输出对不上 | 先 `print(output)` 看实际输出格式 |

---

下一课：[第七课：RAG 系统 — 知识入库与检索](lesson-07-rag.md)
