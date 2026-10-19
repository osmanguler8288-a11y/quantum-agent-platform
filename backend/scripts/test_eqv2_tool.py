"""EqV2 工具层联调 —— 走 MCPClient，和 Agent 主链路同一条路。

用法（必须从 backend/ 运行）:
    python scripts/test_eqv2_tool.py

与 scripts/test_eqv2_api.py 的分工：
    test_eqv2_api.py   直连 HTTP，测**服务**的契约与错误语义
    本脚本             走 build_client()，测**工具**的注册、返回格式与埋点契约

⚠️ 本脚本特别关注一个机械契约：失败必须返回 `[错误] ...` 前缀的字符串。
   tools/instrumented_client.py 的 `_ERR_PREFIX = "[错误]"` 靠这个前缀把调用
   归类为 error；返回英文 `[ERROR]` 会被记成一次**成功**调用，工具库的
   调用统计直接失真。这里用断言把它钉死。

退出码即结论：全过 0，任一失败 1。
"""

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from config.settings import settings  # noqa: E402
from tools.register_all import build_client  # noqa: E402
from tools.instrumented_client import _ERR_PREFIX  # noqa: E402

_H2_STRETCHED = "2\nH2 stretched\nH 0.0 0.0 0.0\nH 0.0 0.0 1.20\n"

# 仓库里的 water_dipole.gjf 被 .gitignore 的 `*.gjf` 排除、不在版本控制里，
# 直接依赖它会让本脚本换台机器就断。自带一份等价 fixture。
_WATER_GJF = """%chk=water_dipole.chk
%mem=4GB
%nprocshared=4
#p B3LYP/6-311+G(d,p) opt freq

water dipole moment

0 1
O   0.000000   0.000000   0.117790
H   0.000000   0.755450  -0.471160
H   0.000000  -0.755450  -0.471160

"""


def gjf_fixture() -> str:
    """优先用仓库里的真实 .gjf，没有就生成一份到临时目录。"""
    if Path("water_dipole.gjf").is_file():
        return "water_dipole.gjf"
    tmp = Path(tempfile.mkdtemp(prefix="eqv2-fixture-"))
    path = tmp / "water_dipole.gjf"
    path.write_text(_WATER_GJF, encoding="utf-8")
    return str(path)


class Case:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.failures = []

    def section(self, title: str):
        print(f"\n{'─' * 66}\n  {title}\n{'─' * 66}")

    def check(self, name: str, ok: bool, detail: str = ""):
        if ok:
            self.passed += 1
            print(f"  [PASS] {name}")
        else:
            self.failed += 1
            self.failures.append(name)
            print(f"  [FAIL] {name}")
        if detail:
            for line in str(detail).splitlines():
                print(f"         {line}")

    def summary(self) -> int:
        total = self.passed + self.failed
        print(f"\n{'═' * 66}")
        print(f"  合计 {total} 项：通过 {self.passed}，失败 {self.failed}")
        if self.failures:
            print("  失败项:")
            for f in self.failures:
                print(f"    ✗ {f}")
        print(f"{'═' * 66}")
        return 1 if self.failed else 0


def main() -> int:
    c = Case()
    client = build_client()
    names = [t["name"] for t in client.list_tools()]

    print(f"\nEqV2 工具层联调（走 MCPClient）")
    print(f"  数据目录: {settings.EQV2_DATA_DIR}")

    # ── 1. 注册状态 ────────────────────────────────────────
    c.section("1. 工具注册")

    c.check("eqv2_predict 已注册", "eqv2_predict" in names)
    c.check("eqv2_relax 已注册", "eqv2_relax" in names)
    c.check("旧的 eqv2 已被两条新工具取代", "eqv2" not in names,
            f"当前量化计算类工具: "
            f"{[n for n in names if n.startswith('eqv2')]}")

    for tool_name in ("eqv2_predict", "eqv2_relax"):
        tool = client.registry.get(tool_name)
        params = (tool.parameters or {}).get("properties", {}) if tool else {}
        c.check(f"{tool_name} 参数契约含 xyz / input_file",
                {"xyz", "input_file"} <= set(params),
                f"properties={sorted(params)}")
        if tool_name == "eqv2_relax":
            c.check("eqv2_relax 参数契约含 fmax / max_steps",
                    {"fmax", "max_steps"} <= set(params),
                    f"properties={sorted(params)}")

    # ── 2. 单点计算（走 MCPClient） ────────────────────────
    c.section("2. eqv2_predict（走 MCPClient）")

    t0 = time.perf_counter()
    r = client.call("eqv2_predict", {"input_file": gjf_fixture()})
    dt = time.perf_counter() - t0
    c.check("input_file 形式调用成功", r.get("status") == "success",
            f"status={r.get('status')} 耗时 {dt:.2f}s")
    report = r.get("result") or ""
    if r.get("status") == "success":
        c.check("报告含能量与单位 eV", "eV" in report and "总能量" in report)
        c.check("报告含受力单位 eV/Å", "eV/Å" in report)
        c.check("报告标注了模型名", "eq2_31M_ec4_allmd.pt" in report)
        c.check("报告带 bond_analysis 的免责说明",
                "不等同于完整化学键分析" in report)
        c.check("报告长度可控（不进 prompt 爆炸）", len(report) < 4000,
                f"{len(report)} 字符")

    r2 = client.call("eqv2_predict", {"xyz": _H2_STRETCHED})
    c.check("xyz 内联形式调用成功", r2.get("status") == "success",
            f"status={r2.get('status')}")

    # ── 3. 参数校验（[错误] 前缀是埋点契约） ────────────────
    c.section("3. 参数校验与 [错误] 前缀契约")

    # ⚠️ 这里断言的是**前缀**，不是 envelope 的 status。
    #
    # 项目既有约定（见 tools/register_all.py 的注释与 agent/executor.py:123-125）：
    # builtin runner 用「返回 '[错误] ...' 字符串」表示失败，而 MCPClient 会把
    # 这类结果一律包成 {"status": "success"}。这是一个**已知偏差**，代码里明确
    # 写明留待 P5 统一修复。
    #
    # 所以 EqV2 两个工具遵循同一约定返回 [错误] 字符串，而不是做全仓库唯一一个
    # 抛异常的工具。代价是 executor 不会因此把任务标记为 FAILED —— 但请注意
    # executor 的重试循环本来就是死代码（MCPClient 从不外抛），真正的重试价值
    # 由 tools/eqv2/client.py 的退避逻辑承担。
    #
    # 埋点侧的正确性由下面第 4 节验证：InstrumentedMCPClient 靠这个前缀把调用
    # 记为 error，工具库的调用统计才不会失真。
    negative_cases = [
        ("两者都不传", {}),
        ("两者同时传", {"xyz": _H2_STRETCHED, "input_file": gjf_fixture()}),
        ("文件不存在", {"input_file": "no_such_file.gjf"}),
        ("fmax 越界", {"xyz": _H2_STRETCHED, "fmax": 9.9}),
    ]
    for label, params in negative_cases:
        tool = "eqv2_relax" if "fmax" in params else "eqv2_predict"
        r = client.call(tool, params)
        body = str(r.get("result") or "")
        c.check(f"{label} → 返回 [错误] 前缀",
                body.startswith(_ERR_PREFIX),
                f"{body[:95]}")

    # ── 4. 埋点契约：InstrumentedMCPClient 必须记成 error ──
    c.section("4. 埋点契约（工具库调用统计的依据）")

    import tools.instrumented_client as ic  # noqa: E402

    captured = []
    _orig = ic.record_invocation

    def _capture(**kw):
        captured.append(kw)

    ic.record_invocation = _capture
    try:
        instr = ic.InstrumentedMCPClient(client)
        instr.call("eqv2_predict", {})                    # 必然失败
        instr.call("eqv2_predict", {"xyz": _H2_STRETCHED})  # 必然成功
    finally:
        ic.record_invocation = _orig

    c.check("埋点捕获到 2 条记录", len(captured) == 2,
            f"got {len(captured)}")
    if len(captured) == 2:
        c.check("失败调用被记为 status='error'（靠 [错误] 前缀）",
                captured[0].get("status") == "error",
                f"status={captured[0].get('status')}, "
                f"tool={captured[0].get('tool_name')}")
        c.check("成功调用被记为 status='success'",
                captured[1].get("status") == "success",
                f"status={captured[1].get('status')}, "
                f"tool={captured[1].get('tool_name')}")
        c.check("失败记录带 error_message",
                bool(captured[0].get("error_message")),
                f"error_message={str(captured[0].get('error_message'))[:80]}")

    # ── 5. 结构优化（走 MCPClient） ────────────────────────
    c.section("5. eqv2_relax（走 MCPClient）")

    t0 = time.perf_counter()
    rr = client.call("eqv2_relax",
                     {"xyz": _H2_STRETCHED, "fmax": 0.5, "max_steps": 50})
    dt = time.perf_counter() - t0
    c.check("relax 调用成功", rr.get("status") == "success",
            f"status={rr.get('status')} 耗时 {dt:.1f}s")
    rreport = rr.get("result") or ""
    if rr.get("status") == "success":
        c.check("报告含收敛判定 converged", "converged" in rreport)
        c.check("报告含 fmax 阈值与步数",
                "fmax" in rreport and "步数" in rreport)
        c.check("报告明确 completed ≠ converged 的口径",
                "只以 result.converged 为准" in rreport)
        c.check("报告给出产物路径",
                "轨迹 CSV" in rreport and "优化后结构" in rreport)
        # ⚠️ 这条是本工具存在的最大理由：relax 的 trajectory 可能有几百个点，
        #    而 executor 会 str(state.results) 无截断地塞进 prompt。
        c.check("报告只出摘要，未回传完整轨迹", len(rreport) < 5000,
                f"{len(rreport)} 字符（轨迹本身已落盘到 CSV）")

    # ── 5. 产物落盘 ────────────────────────────────────────
    c.section("6. 产物落盘 data/eqv2/")

    data_dir = Path(settings.EQV2_DATA_DIR)
    c.check("数据目录已创建", data_dir.is_dir(), str(data_dir))
    if data_dir.is_dir():
        files = sorted(p.name for p in data_dir.iterdir())
        c.check("predict 产物存在",
                any(f.startswith("water_dipole") and f.endswith("_predict.json")
                    for f in files), f"目录内容: {files}")
        c.check("relax 轨迹 CSV 存在",
                any(f.endswith("_trajectory.csv") for f in files),
                f"目录内容: {files}")
        c.check("relax 结构文件存在",
                any(f.endswith("_relaxed.xyz") for f in files),
                f"目录内容: {files}")

        csvs = [p for p in data_dir.iterdir() if p.name.endswith("_trajectory.csv")]
        if csvs:
            body = csvs[0].read_text(encoding="utf-8").strip().splitlines()
            c.check("轨迹 CSV 表头正确",
                    body[0] == "step,energy_ev,fmax_ev_per_ang",
                    f"表头: {body[0]}")
            c.check("轨迹 CSV 有数据行", len(body) > 1,
                    f"{len(body) - 1} 行数据")

    # ── 6. 向后兼容 ────────────────────────────────────────
    c.section("7. 向后兼容")

    try:
        from tools.eqv2.runner import run_eqv2  # noqa: F401
        c.check("废弃入口 run_eqv2 仍可导入（不破坏历史调用点）", True)
    except ImportError as e:
        c.check("废弃入口 run_eqv2 仍可导入", False, str(e))

    # ── 7. 密钥不出现在产物里 ──────────────────────────────
    c.section("8. 机密泄漏检查")

    if settings.EQV2_API_KEY and data_dir.is_dir():
        leaked = []
        for p in data_dir.iterdir():
            if p.is_file() and settings.EQV2_API_KEY in p.read_text(
                    encoding="utf-8", errors="replace"):
                leaked.append(p.name)
        c.check("产物中不含 API Key", not leaked, f"泄漏文件: {leaked}")

    return c.summary()


if __name__ == "__main__":
    sys.exit(main())
