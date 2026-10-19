"""EqV2 服务层联调 —— 直连远程 HTTP 服务，不依赖本项目后端启动。

用法（必须从 backend/ 运行）:
    python scripts/test_eqv2_api.py            # 快速用例
    python scripts/test_eqv2_api.py --full     # 追加未收敛优化用例（约 30s+）
    python scripts/test_eqv2_api.py --burst 10 # 自定义限流韧性测试的连发次数

⚠️ 退出码即结论：全过退出 0，任一失败退出 1。不要像 tests/test_tools_e2e.py
   那样无条件打印"全部通过"—— 那种脚本在 CI 里等于没有。

本脚本覆盖的是"接口契约 + 错误语义 + 限流韧性"，而工具层（MCPClient 注册、
[错误] 前缀埋点、产物落盘）在 scripts/test_eqv2_tool.py 里测。
"""

import argparse
import pathlib
import sys
import tempfile
import time

sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import requests  # noqa: E402  仅用于绕过客户端的负例探测

from config.settings import settings  # noqa: E402
from tools.eqv2 import parser as P  # noqa: E402
from tools.eqv2.client import (  # noqa: E402
    EqV2AuthError,
    EqV2Client,
    EqV2Error,
    EqV2InputError,
)

_H2_STRETCHED = "2\nH2 stretched\nH 0.0 0.0 0.0\nH 0.0 0.0 1.20\n"
_H2_RELAXED = "2\nH2 relaxed\nH 0.0 0.0 0.2278\nH 0.0 0.0 0.9722\n"

# 仓库根下确实有 water_dipole.gjf / methanol.gjf，但它们被 .gitignore 的
# `*.gjf` 规则排除、**不在版本控制里**。直接依赖它们会让本脚本换台机器就断，
# 所以这里自带 fixture：优先用仓库里的真实文件（更能反映实际输入），
# 没有就地生成一份等价的 Gaussian 输入。
_FIXTURES = {
    "water_dipole.gjf": """%chk=water_dipole.chk
%mem=4GB
%nprocshared=4
#p B3LYP/6-311+G(d,p) opt freq

water dipole moment

0 1
O   0.000000   0.000000   0.117790
H   0.000000   0.755450  -0.471160
H   0.000000  -0.755450  -0.471160

""",
    "methanol.gjf": """%chk=methanol.chk
%mem=2GB
%nprocshared=4
# B3LYP/6-31G(d) Opt Freq

methanol IR spectrum

0 1
C  0.000000  0.000000  0.000000
O  1.400000  0.000000  0.000000
H  1.900000  0.900000  0.000000
H -0.500000  0.900000  0.000000
H -0.400000 -0.700000  0.600000
H -0.400000 -0.700000 -0.600000

""",
}


def gjf_fixture(name: str) -> str:
    """返回一个可用的 .gjf 路径：优先仓库里的，否则生成到临时目录。"""
    if pathlib.Path(name).is_file():
        return name
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="eqv2-fixture-"))
    path = tmp / name
    path.write_text(_FIXTURES[name], encoding="utf-8")
    return str(path)


# ─────────────────────────────────────────────────────────────
# 极简断言框架
# ─────────────────────────────────────────────────────────────

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

    def raises(self, name: str, exc_type, fn, detail: str = ""):
        """断言 fn() 抛出 exc_type。"""
        try:
            result = fn()
        except exc_type as e:
            self.check(name, True, f"{type(e).__name__}: {str(e)[:160]}")
            return
        except Exception as e:  # noqa: BLE001
            self.check(name, False,
                       f"抛了 {type(e).__name__} 而不是 {exc_type.__name__}: {e}")
            return
        self.check(name, False, f"没有抛异常，返回了: {str(result)[:160]}")

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


def _retry_capture():
    """挂一个 loguru sink 统计客户端实际触发的退避重试次数。

    这是"限流韧性"用例的断言依据 —— 只断言"全部成功"是不够的，
    因为服务恰好不忙时也会全部成功，那样测试就没证明任何东西。
    """
    from loguru import logger as _lg

    stats = {"backoff": 0, "auth_fail": 0}

    def _sink(message):
        rec = message.record
        if rec["extra"].get("component") != "eqv2":
            return
        if "退避" in rec["message"]:
            stats["backoff"] += 1
        if "鉴权失败" in rec["message"]:
            stats["auth_fail"] += 1

    sink_id = _lg.add(_sink, level="WARNING")
    return stats, sink_id


# ─────────────────────────────────────────────────────────────
# 用例
# ─────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="EqV2 服务层联调")
    ap.add_argument("--full", action="store_true",
                    help="追加「未收敛优化」用例（耗时长）")
    ap.add_argument("--burst", type=int, default=6,
                    help="限流韧性测试的连发次数，默认 6；设 0 跳过")
    args = ap.parse_args()

    c = Case()
    stats, sink_id = _retry_capture()

    print(f"\nEqV2 服务层联调")
    print(f"  base_url : {settings.EQV2_API_BASE_URL}")
    print(f"  API Key  : {'已配置 (' + str(len(settings.EQV2_API_KEY)) + ' 字符)' if settings.EQV2_API_KEY else '⚠️ 未配置'}")
    print(f"  超时/重试: {settings.EQV2_TIMEOUT}s / {settings.EQV2_MAX_RETRIES} 次")
    print(f"  轮询间隔 : {settings.EQV2_POLL_INTERVAL}s")

    if not settings.EQV2_API_KEY:
        print("\n[中止] 未配置 EQV2_API_KEY，无法执行。请在 .env 中设置。")
        return 1

    client = EqV2Client()

    # ── 1. 存活与鉴权 ──────────────────────────────────────
    c.section("1. 存活与鉴权")

    try:
        info = client.health()
        c.check("/health 免 Key 可达", info.get("status") == "ok", info)
        c.check("模型已加载", bool(info.get("model_loaded")), info)
    except Exception as e:  # noqa: BLE001
        c.check("/health 免 Key 可达", False, f"{type(e).__name__}: {e}")
        print("\n[中止] 服务不可达，后续用例无意义。")
        return c.summary()

    no_key = EqV2Client(api_key="")
    c.raises("/v1/models 无 Key → 401", EqV2AuthError,
             lambda: no_key.models())

    bad_key = EqV2Client(api_key="definitely-not-the-right-key")
    c.raises("/v1/predict 错 Key → 401", EqV2AuthError,
             lambda: bad_key.predict(_H2_RELAXED))
    c.check("错 Key 不重试（401 一次即终止）", stats["auth_fail"] >= 2,
            f"观察到 {stats['auth_fail']} 次鉴权失败（应为 2，无多余重试）")

    # ── 2. 模型元信息 ──────────────────────────────────────
    c.section("2. 模型元信息")

    models = client.models()
    c.check("模型名与文档一致", models.get("model") == "eq2_31M_ec4_allmd.pt", models)
    c.check("max_atoms 与本地配置一致",
            models.get("max_atoms") == settings.EQV2_MAX_ATOMS,
            f"服务端={models.get('max_atoms')} 本地={settings.EQV2_MAX_ATOMS}")
    c.check("max_steps 上限为 200", models.get("max_steps") == 200, models)
    c.check("concurrency == 1（必须串行的依据）",
            models.get("concurrency") == 1, models)

    # ── 3. 单点计算 ────────────────────────────────────────
    c.section("3. 单点计算 /v1/predict")

    for label, fixture, expect_n in (("水分子", "water_dipole.gjf", 3),
                                     ("甲醇", "methanol.gjf", 6)):
        try:
            xyz = P.read_xyz_text(gjf_fixture(fixture))
            P.validate_xyz(xyz, settings.EQV2_MAX_ATOMS)
            t0 = time.perf_counter()
            data = client.predict(xyz)
            dt = time.perf_counter() - t0
            forces = data.get("forces_ev_per_ang") or []
            energy = data.get("energy_ev")
            c.check(f"{label} predict 返回成功", True, f"耗时 {dt:.2f}s")
            c.check(f"{label} 原子数 = {expect_n}",
                    data.get("natoms") == expect_n, f"natoms={data.get('natoms')}")
            c.check(f"{label} 能量为有限值",
                    isinstance(energy, (int, float)),
                    f"energy_ev={energy}")
            c.check(f"{label} 受力行数 = 原子数",
                    len(forces) == expect_n,
                    f"len(forces)={len(forces)}, natoms={expect_n}")
            c.check(f"{label} 每个力向量都是 3 维",
                    all(len(f) == 3 for f in forces), "")
        except Exception as e:  # noqa: BLE001
            c.check(f"{label} predict", False, f"{type(e).__name__}: {e}")

    # ── 4. 输入负例（服务端 422 语义） ──────────────────────
    c.section("4. 输入负例 → 422")

    c.raises("原子数与首行不符 → 422", EqV2InputError,
             lambda: client.predict("3\nbad\nO 0 0 0\nH 0 0 1\n"))
    c.raises("非法元素 → 422", EqV2InputError,
             lambda: client.predict("1\nbad\nXx 0 0 0\n"))
    c.raises("XYZ 过短（<6 字符）→ 422", EqV2InputError,
             lambda: client.predict("ab"))
    c.raises("fmax 越界(6.0) → 422", EqV2InputError,
             lambda: client.submit_relax(_H2_RELAXED, fmax=6.0))
    c.raises("max_steps 越界(999) → 422", EqV2InputError,
             lambda: client.submit_relax(_H2_RELAXED, max_steps=999))

    # 本地预检必须能在出网前挡下同样的输入
    c.raises("本地预检挡下原子数不符（不出网）", ValueError,
             lambda: P.validate_xyz("3\nbad\nO 0 0 0\nH 0 0 1\n", 200))
    c.raises("本地预检挡下非法元素", ValueError,
             lambda: P.validate_xyz("1\nbad\nXx 0 0 0\n", 200))
    c.raises("本地预检挡下超原子上限", ValueError,
             lambda: P.validate_xyz(
                 "201\nbig\n" + "H 0 0 0\n" * 201, 200))

    # ── 5. 未知作业 → 404 ──────────────────────────────────
    c.section("5. 未知作业 → 404")

    c.raises("未知 job_id → EqV2Error（不重试）", EqV2Error,
             lambda: client.get_job("00000000-0000-0000-0000-000000000000"))

    # ── 6. 结构优化（收敛路径） ─────────────────────────────
    c.section("6. 结构优化 /v1/relax（收敛路径）")

    try:
        t0 = time.perf_counter()
        job_id = client.submit_relax(_H2_STRETCHED, fmax=0.5, max_steps=50)
        c.check("relax 提交返回 job_id", bool(job_id), f"job_id={job_id}")

        job = client.wait_for_job(job_id, poll_interval=5)
        dt = time.perf_counter() - t0
        result = job.get("result") or {}

        c.check("作业到达 completed", job.get("status") == "completed",
                f"status={job.get('status')}，耗时 {dt:.1f}s")
        c.check("converged 为 True（fmax=0.5 宽松阈值）",
                result.get("converged") is True,
                f"converged={result.get('converged')}, "
                f"final_fmax={result.get('final_fmax_ev_per_ang')}")
        c.check("最终能量低于初始能量",
                (result.get("final_energy_ev") or 0)
                < (result.get("initial_energy_ev") or 0),
                f"{result.get('initial_energy_ev')} → {result.get('final_energy_ev')} eV")
        c.check("nsteps 不超过 max_steps",
                (result.get("nsteps") or 0) <= 50, f"nsteps={result.get('nsteps')}")
        c.check("返回 trajectory 且步数 = nsteps+1",
                len(result.get("trajectory") or []) == (result.get("nsteps") or 0) + 1,
                f"len(trajectory)={len(result.get('trajectory') or [])}")

        structure = client.get_structure(job_id)
        lines = structure.splitlines()
        # ASE 扩展 XYZ 的结构是：第1行原子数，第2行是带 energy=/forces 的元数据，之后才是原子
        header = lines[1] if len(lines) > 1 else ""
        c.check("结构下载成功且为扩展 XYZ",
                lines and lines[0].strip() == "2" and "energy=" in header,
                f"第 2 行: {header[:110]}")

        # 下载的结构应当能重新喂回 predict（闭环）
        data = client.predict(structure)
        c.check("下载的结构可再次 predict（闭环）",
                data.get("natoms") == 2, f"natoms={data.get('natoms')}")

        # 更关键的一环：我们**自己的解析器**也要能读回扩展 XYZ，否则
        # "优化 → 拿优化后的结构继续算"这条路在后端就断了。
        struct_path = pathlib.Path(settings.EQV2_DATA_DIR) / "_roundtrip.xyz"
        struct_path.parent.mkdir(parents=True, exist_ok=True)
        struct_path.write_text(structure, encoding="utf-8")
        try:
            reparsed = P.read_xyz_text(str(struct_path))
            c.check("扩展 XYZ（6 列）可被本地解析器读回",
                    P.count_atoms(reparsed) == 2, f"重新解析出 {P.count_atoms(reparsed)} 个原子")
        except ValueError as e:
            c.check("扩展 XYZ（6 列）可被本地解析器读回", False, f"ValueError: {e}")
        finally:
            struct_path.unlink(missing_ok=True)
    except Exception as e:  # noqa: BLE001
        c.check("relax 收敛路径", False, f"{type(e).__name__}: {e}")

    # ── 7. 结构优化（未收敛路径，--full） ───────────────────
    if args.full:
        c.section("7. 结构优化（未收敛路径）—— 验证 completed ≠ converged")

        try:
            xyz_water = P.read_xyz_text(gjf_fixture("water_dipole.gjf"))
            t0 = time.perf_counter()
            job_id = client.submit_relax(xyz_water, fmax=0.001, max_steps=30)
            job = client.wait_for_job(job_id, poll_interval=5)
            dt = time.perf_counter() - t0
            result = job.get("result") or {}

            c.check("作业状态仍是 completed（流程跑完了）",
                    job.get("status") == "completed", f"耗时 {dt:.1f}s")
            c.check("但 converged 为 False（未达阈值）",
                    result.get("converged") is False,
                    f"converged={result.get('converged')}, "
                    f"final_fmax={result.get('final_fmax_ev_per_ang')} > "
                    f"阈值 {result.get('fmax_threshold')}")
            c.check("nsteps 用满 max_steps",
                    result.get("nsteps") == 30, f"nsteps={result.get('nsteps')}")
        except Exception as e:  # noqa: BLE001
            c.check("relax 未收敛路径", False, f"{type(e).__name__}: {e}")

    # ── 8. 限流韧性（本次联调的核心回归测试） ───────────────
    if args.burst > 0:
        c.section(f"8. 限流韧性 —— 连发 {args.burst} 次 predict")

        print(f"  说明：服务端 concurrency=1 且 Nginx 限流，突发请求实测会被打成 503。")
        print(f"        断言「全部成功」不足以证明重试生效 —— 故同时统计退避次数。")
        before = stats["backoff"]
        t0 = time.perf_counter()
        ok_count = 0
        for i in range(args.burst):
            try:
                d = client.predict(_H2_RELAXED)
                if d.get("natoms") == 2:
                    ok_count += 1
            except Exception as e:  # noqa: BLE001
                print(f"        第 {i+1} 次失败: {type(e).__name__}: {str(e)[:100]}")
        dt = time.perf_counter() - t0
        backoffs = stats["backoff"] - before

        c.check(f"连发 {args.burst} 次全部成功", ok_count == args.burst,
                f"成功 {ok_count}/{args.burst}，总耗时 {dt:.1f}s")
        c.check("退避重试确实被触发（证明限流真实存在且被吸收）",
                backoffs > 0,
                f"触发 {backoffs} 次退避。若为 0，说明服务当时不忙，"
                f"本次未覆盖限流场景 —— 可加大 --burst 重测")

    from loguru import logger as _lg
    _lg.remove(sink_id)
    return c.summary()


if __name__ == "__main__":
    sys.exit(main())
