"""附件端到端联调 —— 从「上传的 structure」一路走到 EqV2 真实计算。

用法（必须从 backend/ 运行）:
    python scripts/test_attachment_flow.py             # 全流程（会真调 LLM + EqV2）
    python scripts/test_attachment_flow.py --offline   # 跳过需要网络的步骤

覆盖链路：
    build_attachment（解析/净化/落盘）
      → to_context_block（Planner 看到的路径形态）
      → Planner 规划出 eqv2_* 且用 input_file
      → 走 build_client() 真实执行
      → 产物与报告核对

⚠️ 退出码即结论：全过 0，任一失败 1。

⚠️ 脚本名以 test_ 开头，会被 pytest 收集（若将来装了 pytest）。所以**所有逻辑都
   收在 main() 里、函数一律叫 check_\***，不在模块层发任何请求。
"""

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from config.settings import settings  # noqa: E402
from tools.eqv2 import parser as P  # noqa: E402
from app.utils import attachment as A  # noqa: E402

WATER_XYZ = (
    "3\nwater\n"
    "O 0.000000 0.000000 0.117790\n"
    "H 0.000000 0.755450 -0.471160\n"
    "H 0.000000 -0.755450 -0.471160\n"
)


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
    ap = argparse.ArgumentParser(description="附件端到端联调")
    ap.add_argument("--offline", action="store_true",
                    help="跳过需要 LLM / EqV2 网络的步骤")
    args = ap.parse_args()

    c = Case()
    print("\n附件端到端联调")
    print(f"  附件目录 : {settings.ATTACHMENT_DATA_DIR}")
    print(f"  原子上限 : {settings.EQV2_MAX_ATOMS}")

    # 用临时目录跑，不污染仓库里的 data/attachments/
    tmp = Path(tempfile.mkdtemp(prefix="att-flow-"))
    saved_dir = settings.ATTACHMENT_DATA_DIR
    settings.ATTACHMENT_DATA_DIR = str(tmp)

    try:
        # ── 1. 解析与落盘 ──────────────────────────────────
        c.section("1. 解析与落盘")

        att = A.build_attachment(
            {"format": "file", "data": WATER_XYZ, "filename": "水分子.xyz"}
        )
        c.check("解析成功且原子数正确", att.natoms == 3, f"natoms={att.natoms}")
        c.check("分子式正确", att.formula == "H2O", f"formula={att.formula}")
        c.check("展示名保留中文原名", att.filename == "水分子.xyz", att.filename)
        c.check("文件已落盘", att.path.is_file(), str(att.path))
        c.check("落盘名是安全 ASCII", att.path.name.isascii(), att.path.name)

        # 往返闭合：工具侧解析器必须能读回我们落盘的东西
        back = P.read_xyz_text(str(att.path))
        c.check("工具侧解析器可读回（闭环）",
                P.count_atoms(back) == att.natoms and back == att.xyz,
                f"读回 {P.count_atoms(back)} 个原子")

        # ── 2. Planner 看到的路径形态 ──────────────────────
        c.section("2. 上下文块（Planner 看到的）")

        ctx = att.to_context_block()
        c.check("含 POSIX 形式的路径", att.path.as_posix() in ctx)
        c.check("不含任何反斜杠（否则 LLM 会写出非法 JSON 转义）",
                "\\" not in ctx,
                "上下文块里出现反斜杠 = 整轮可能静默降级成空计划")
        c.check("明确指向 input_file 参数", "input_file" in ctx)
        c.check("含原子数与元素组成",
                str(att.natoms) in ctx and att.formula in ctx)
        c.check("展示层保留中文原名", "水分子.xyz" in ctx)

        # ── 3. 路径钉扎 ────────────────────────────────────
        c.section("3. 路径钉扎（兜底）")

        bad_plan = [
            {"type": "tool", "step": "eqv2_predict",
             "params": {"input_file": "D:\\wrong\\dir\\" + att.path.name}},
            {"type": "tool", "step": "homo_lumo",
             "params": {"fchk_path": "D:\\other\\x.fchk"}},
        ]
        n = A.pin_attachment_paths(bad_plan, att)
        c.check("反斜杠错路径被改写回真实路径",
                n == 1 and bad_plan[0]["params"]["input_file"] == att.path.as_posix(),
                f"改写 {n} 条 → {bad_plan[0]['params']['input_file']}")
        c.check("指向别的文件的路径不受影响",
                bad_plan[1]["params"]["fchk_path"] == "D:\\other\\x.fchk")

        # ── 4. Planner 规划 ────────────────────────────────
        plan = []
        if args.offline:
            print("\n  [跳过] Planner 规划（--offline）")
        else:
            c.section("4. Planner 规划")

            from llm.client import LLMClient
            from agent.planner import Planner
            from agent.state import AgentState

            state = AgentState(task_id="att-test", user_query="算一下这个结构的能量")
            t0 = time.time()
            Planner(LLMClient()).plan(state, context=ctx)
            dt = time.time() - t0
            plan = state.plan or []
            print(f"  规划耗时 {dt:.1f}s，{len(plan)} 步")

            eqv2_steps = [s for s in plan
                          if isinstance(s, dict)
                          and str(s.get("step", "")).startswith("eqv2")]
            c.check("规划出了 eqv2_* 步骤", bool(eqv2_steps),
                    json.dumps(plan, ensure_ascii=False)[:300])

            if eqv2_steps:
                params = eqv2_steps[0].get("params") or {}
                c.check("用的是 input_file 而不是 xyz",
                        "input_file" in params and "xyz" not in params,
                        f"params={json.dumps(params, ensure_ascii=False)[:200]}")
                got = str(params.get("input_file") or "")
                # 只比 basename：容忍 LLM 改分隔符/目录写法
                c.check("input_file 指向本附件（按 basename 比对）",
                        Path(got.replace("\\", "/")).name == att.path.name,
                        f"LLM 给出: {got}")
                c.check("input_file 不含反斜杠",
                        "\\" not in got, f"LLM 给出: {got}")

        # ── 5. 真实执行 ────────────────────────────────────
        if args.offline:
            print("\n  [跳过] 工具执行（--offline）")
        elif not plan:
            c.check("有可执行的计划", False, "Planner 没产出步骤，无法继续")
        else:
            c.section("5. 工具真实执行（走 MCPClient）")

            from tools.register_all import build_client
            client = build_client()

            step = next((s for s in plan if isinstance(s, dict)
                         and str(s.get("step", "")).startswith("eqv2")), None)
            tool_name = step.get("step")
            params = dict(step.get("params") or {})
            # 钉扎后再执行 —— 与 route 的行为一致
            A.pin_attachment_paths([step], att)

            t0 = time.time()
            r = client.call(tool_name, params)
            dt = time.time() - t0
            result = str(r.get("result") or "")

            c.check(f"{tool_name} 执行成功", r.get("status") == "success",
                    f"status={r.get('status')} 耗时 {dt:.1f}s")
            c.check("结果不是 [错误] 前缀", not result.startswith("[错误]"),
                    result[:200])
            c.check("报告里的原子数与附件一致",
                    f"原子数    : {att.natoms}" in result,
                    result[:300].replace("\n", " "))

        # ── 6. 错误路径 ────────────────────────────────────
        c.section("6. 错误路径（都应快速失败，不烧 LLM）")

        for label, payload, code in [
            ("不支持 .mol", {"format": "file", "data": "x", "filename": "a.mol"},
             A.CODE_FORMAT),
            ("乱文本", {"format": "xyz", "data": "这不是结构"}, A.CODE_PARSE),
            ("空内容", {"format": "xyz", "data": "  "}, A.CODE_EMPTY),
            ("SMILES", {"format": "smiles", "data": "c1ccccc1"}, A.CODE_FORMAT),
        ]:
            try:
                A.build_attachment(payload)
                c.check(f"{label} → 应被拒绝", False, "竟然通过了")
            except A.AttachmentError as e:
                c.check(f"{label} → {code}", e.code == code, f"{e.code}: {e}")
            except Exception as e:  # noqa: BLE001
                c.check(f"{label} → {code}", False, f"{type(e).__name__}: {e}")

        return c.summary()
    finally:
        settings.ATTACHMENT_DATA_DIR = saved_dir
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
