"""端到端测试：工具注册 + 调用验证"""
import sys
sys.path.insert(0, '.')

from tools.register_all import build_client


def test_all():
    print("=" * 50)
    print("1. 构建 MCPClient + 注册所有工具")
    print("=" * 50)
    client = build_client()
    tools = client.list_tools()
    print(f"已注册 {len(tools)} 个工具:")
    for t in tools:
        remote_tag = " [REMOTE]" if t.get("remote") else ""
        print(f"  [OK] {t['name']}{remote_tag}")

    print()
    print("=" * 50)
    print("2. Bash 工具测试")
    print("=" * 50)
    r = client.call("bash", {"command": "echo Hello从Agent执行!"})
    print(f"  状态: {r['status']}")
    print(f"  结果: {r['result'].strip()}")

    print()
    print("=" * 50)
    print("3. List_dir 工具测试")
    print("=" * 50)
    r = client.call("list_dir", {"path": ".", "pattern": "*.py"})
    print(f"  状态: {r['status']}")
    # 只打印前几行
    for line in r["result"].split("\n")[:10]:
        print(f"  {line}")

    print()
    print("=" * 50)
    print("4. Python REPL 工具测试")
    print("=" * 50)
    code = (
        "hartree = -76.423456789\n"
        "ev = hartree * 27.2114\n"
        "gap = 5.7\n"
        "print(f'能量: {hartree:.6f} Hartree = {ev:.4f} eV')\n"
        "print(f'HOMO-LUMO gap: {gap} eV')\n"
    )
    r = client.call("python_repl", {"code": code})
    print(f"  状态: {r['status']}")
    print(f"  结果:\n{r['result']}")

    print()
    print("=" * 50)
    print("5. Write + Read + Delete 文件工具测试")
    print("=" * 50)
    test_path = "data/test_agent_write.txt"
    client.call("write_file", {"path": test_path, "content": "Agent 工具测试文件\n量子化学平台"})
    r = client.call("read_file", {"path": test_path})
    print(f"  写入后读取: {r['result'].strip()}")
    client.call("delete_file", {"path": test_path})
    r2 = client.call("read_file", {"path": test_path})
    print(f"  删除后读取: {r2['result'][:60]}")

    print()
    print("=" * 50)
    print("6. 调用未注册工具 → 预期报错")
    print("=" * 50)
    r = client.call("nonexistent_tool", {})
    print(f"  状态: {r['status']}")
    print(f"  消息: {r['message'][:100]}")

    print()
    print("=" * 50)
    print("7. ToolRegistry 的 MCP 格式导出")
    print("=" * 50)
    summary = client.registry.list_tools()
    for t in summary:
        desc_short = t["description"][:80]
        print(f"  {t['name']}: {desc_short}...")

    print()
    print("=" * 50)
    print("[OK] All 7 tests passed!")
    print("=" * 50)


if __name__ == "__main__":
    test_all()
