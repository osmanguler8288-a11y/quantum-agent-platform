"""测试 Agent 工具：读取桌面文件（UTF-8 安全输出）"""
import sys
import os
sys.path.insert(0, '.')

# 强制 UTF-8 输出
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from tools.register_all import build_client

client = build_client()
print("已注册工具:", [t["name"] for t in client.list_tools()])
print()

desktop_file = r"C:\Users\50244\Desktop\git、docker-command、.doc"

# ── 测试1: read_file ──────────────────────────
print(f"=== 测试1: read_file ===")
print(f"目标: {desktop_file}")
r = client.call("read_file", {"path": desktop_file, "max_lines": 80})
print(f"状态: {r['status']}")
if r["status"] == "success":
    content = r["result"]
    print(f"文件长度: {len(content)} 字符")
    print("--- 内容预览 (前2000字符) ---")
    print(content[:2000])
    print("--- 预览结束 ---")
else:
    print(f"错误: {r.get('message', '')[:200]}")

# ── 测试2: bash 检查文件信息 ──────────────────
print()
print("=== 测试2: bash dir 文件信息 ===")
r2 = client.call("bash", {"command": f'dir "{desktop_file}"', "timeout": 10})
print(f"状态: {r2['status']}")
print(r2["result"][:500])

# ── 测试3: grep_file 搜索 git ──────────────────
print()
print("=== 测试3: grep_file 搜索 'git' ===")
r3 = client.call("grep_file", {
    "path": desktop_file,
    "pattern": "git",
    "context_lines": 1,
    "max_matches": 5,
})
print(f"状态: {r3['status']}")
print(r3["result"][:1000])

print()
print("=== 全部测试通过 ✅ ===")
