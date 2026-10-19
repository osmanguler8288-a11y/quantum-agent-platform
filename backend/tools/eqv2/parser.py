"""EqV2 工具的输入解析与输出格式化。

═══════════════════════════════════════════════════════════════════════
为什么报告必须是"摘要"而不是原样回传
═══════════════════════════════════════════════════════════════════════

agent/executor.py 的 _execute_reasoning 会把 str(state.results) 整段塞进
reasoning prompt，**全程没有任何截断**。而 relax 的 trajectory 实测有水分子
201 步的记录 —— 原样回传会直接把上下文窗口吃掉。

所以这里的规则是：**返回值只带摘要，完整数据落盘到 data/eqv2/**，并在报告里
给出文件路径，让 LLM 需要时自己用 read_file / grep_file / python_repl 去取。
这也和项目里"文件即接口"的既有习惯一致（gaussian 写 .log、dipole 读 .out）。

═══════════════════════════════════════════════════════════════════════
两条绝不能省的口径说明
═══════════════════════════════════════════════════════════════════════

1. `completed` ≠ 收敛。前者只表示优化流程跑完了，后者要看 result.converged。
   文档 §5、§9 反复强调这一点，报告里必须写死。
2. `bond_analysis` 只是"面向首个原子"的简单几何分析，不是完整化学键分析。
   不写这句，LLM 很容易把它当成键级/键能结论来解读。
"""

import json
import math
import re
from pathlib import Path

# 元素符号表（1~118），用于本地校验输入，把 422 挡在出网之前
_ELEMENTS = {
    "H", "He", "Li", "Be", "B", "C", "N", "O", "F", "Ne",
    "Na", "Mg", "Al", "Si", "P", "S", "Cl", "Ar", "K", "Ca",
    "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn",
    "Ga", "Ge", "As", "Se", "Br", "Kr", "Rb", "Sr", "Y", "Zr",
    "Nb", "Mo", "Tc", "Ru", "Rh", "Pd", "Ag", "Cd", "In", "Sn",
    "Sb", "Te", "I", "Xe", "Cs", "Ba", "La", "Ce", "Pr", "Nd",
    "Pm", "Sm", "Eu", "Gd", "Tb", "Dy", "Ho", "Er", "Tm", "Yb",
    "Lu", "Hf", "Ta", "W", "Re", "Os", "Ir", "Pt", "Au", "Hg",
    "Tl", "Pb", "Bi", "Po", "At", "Rn", "Fr", "Ra", "Ac", "Th",
    "Pa", "U", "Np", "Pu", "Am", "Cm", "Bk", "Cf", "Es", "Fm",
    "Md", "No", "Lr", "Rf", "Db", "Sg", "Bh", "Hs", "Mt", "Ds",
    "Rg", "Cn", "Nh", "Fl", "Mc", "Lv", "Ts", "Og",
}

_CHARGE_MULT_RE = re.compile(r"^\s*-?\d+\s+\d+\s*$")

_NUM = r"(-?\d+\.?\d*(?:[eEdD][-+]?\d+)?)"
# Gaussian 输入里的原子行：严格 4 列，多一列就说明这不是原子块
_ATOM_LINE_RE = re.compile(rf"^\s*([A-Za-z]{{1,3}})\s+{_NUM}\s+{_NUM}\s+{_NUM}\s*$")

# XYZ 的原子行：允许**额外的尾部数值列**。
# ⚠️ 服务端 /structure 返回的是 ASE 扩展 XYZ，每行是
#     元素 x y z Fx Fy Fz
#   共 6 个数字。若这里按 4 列严格匹配，我们自己下载的优化后结构就再也读不回来 ——
#   "优化 → 拿优化后的结构继续算"这个最自然的闭环会断掉。
_XYZ_ATOM_RE = re.compile(rf"^\s*([A-Za-z]{{1,3}})\s+{_NUM}\s+{_NUM}\s+{_NUM}(?:\s+\S+)*\s*$")


# ─────────────────────────────────────────────────────────────
# 输入解析
# ─────────────────────────────────────────────────────────────

def _parse_gaussian(text: str) -> str | None:
    """从 Gaussian 输入文件（.gjf/.com）里抽出 XYZ 块。

    结构：link0(`%`) 若干 → route(`#`) → 空行 → 标题 → 空行 → 电荷/多重度
          → 原子块 → 空行。
    """
    lines = text.splitlines()
    i = 0
    n = len(lines)

    # 1. 跳过前导空行与 link0 行
    while i < n and (not lines[i].strip() or lines[i].lstrip().startswith("%")):
        i += 1
    # 2. 跳过 route 行（可能多行续行，以行尾 - 判断续行）
    while i < n and lines[i].lstrip().startswith("#"):
        continuation = lines[i].rstrip().endswith("-")
        i += 1
        if not continuation:
            break
    # 3. 跳过空行 → 标题（可多行，但常见是单行）
    while i < n and not lines[i].strip():
        i += 1
    title = ""
    if i < n:
        title = lines[i].strip()
        i += 1
    while i < n and not lines[i].strip():
        i += 1
    # 4. 跳过电荷/多重度行
    if i < n and _CHARGE_MULT_RE.match(lines[i]):
        i += 1
    else:
        return None                 # 不是标准 Gaussian 输入
    # 5. 收原子块，到空行或 EOF 为止
    atoms = []
    while i < n:
        line = lines[i]
        if not line.strip():
            break
        m = _ATOM_LINE_RE.match(line)
        if not m:
            break
        elem = m.group(1).capitalize()
        atoms.append(
            f"{elem:<2s} {float(m.group(2)):>14.8f} "
            f"{float(m.group(3)):>14.8f} {float(m.group(4)):>14.8f}"
        )
        i += 1

    if not atoms:
        return None
    return f"{len(atoms)}\n{title or 'molecule'}\n" + "\n".join(atoms) + "\n"


def _parse_xyz(text: str) -> str | None:
    """校验并规范化一个标准 XYZ 文本。"""
    lines = [ln for ln in text.splitlines()]
    # 去掉首尾空行，但保留内部结构
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if len(lines) < 3:
        return None
    try:
        natoms = int(lines[0].strip())
    except ValueError:
        return None
    atom_lines = lines[2:2 + natoms]
    if len(atom_lines) < natoms:
        return None
    out = [str(natoms), lines[1].strip() or "molecule"]
    for ln in atom_lines:
        m = _XYZ_ATOM_RE.match(ln)
        if not m:
            return None
        out.append(
            f"{m.group(1).capitalize():<2s} {float(m.group(2)):>14.8f} "
            f"{float(m.group(3)):>14.8f} {float(m.group(4)):>14.8f}"
        )
    return "\n".join(out) + "\n"


def read_xyz_text(path: str) -> str:
    """读文件并转成 XYZ 文本。支持 .xyz / .gjf / .com / .log 片段。

    抛 ValueError（由 runner 转成 [错误] 字符串）。
    """
    p = Path(path)
    if not p.exists():
        raise ValueError(f"文件不存在: {path}")
    if not p.is_file():
        raise ValueError(f"不是文件: {path}")

    text = p.read_text(encoding="utf-8", errors="replace")
    suffix = p.suffix.lower()

    if suffix in (".gjf", ".com", ".gjf2", ".gau"):
        xyz = _parse_gaussian(text)
        if xyz is None:
            raise ValueError(
                f"无法从 {p.name} 中解析出 Gaussian 原子块"
                f"（期望 link0/route/标题/电荷多重度/原子坐标 的结构）"
            )
    else:
        xyz = _parse_xyz(text)
        if xyz is None:
            # 兜底：有的 .log/.out 里嵌着 XYZ，或用户给的是 .gjf 却用了别的后缀
            xyz = _parse_gaussian(text)
        if xyz is None:
            raise ValueError(
                f"无法从 {p.name} 中解析出 XYZ 结构"
                f"（支持 .xyz，以及 .gjf/.com 形式的 Gaussian 输入）"
            )
    return xyz


def normalize_xyz(raw: str, source_label: str = "inline") -> str:
    """把直接传入的字符串规范成 XYZ 文本。

    既能吃 XYZ，也能吃一段 Gaussian 输入 —— Planner 有时会把文件内容
    整段贴进参数里。
    """
    if not raw or not raw.strip():
        raise ValueError("xyz 参数为空")
    xyz = _parse_xyz(raw) or _parse_gaussian(raw)
    if xyz is None:
        raise ValueError(
            f"{source_label}: 不是合法的 XYZ 文本"
            f"（首行应为原子数，第二行注释，随后每行 '元素 x y z'）"
        )
    return xyz


def count_atoms(xyz: str) -> int:
    return int(xyz.splitlines()[0].strip())


def validate_xyz(xyz: str, max_atoms: int) -> None:
    """本地预检。把能在本地判定的错误挡在出网之前。

    服务端会返回 422，但"先发出去再拿 422 当流程控制"会让用户多等一个
    网络往返，且错误信息不如本地判定得清楚。
    """
    lines = [ln for ln in xyz.splitlines() if ln.strip()]
    try:
        natoms = int(lines[0].strip())
    except (ValueError, IndexError):
        raise ValueError("XYZ 首行必须是原子数")

    atom_lines = lines[2:]
    if len(atom_lines) != natoms:
        raise ValueError(
            f"XYZ 原子数不一致：首行声明 {natoms}，实际给出 {len(atom_lines)} 行"
        )
    if natoms <= 0:
        raise ValueError("XYZ 至少要有 1 个原子")
    if natoms > max_atoms:
        raise ValueError(
            f"原子数 {natoms} 超过 EqV2 服务上限 {max_atoms}"
        )

    bad = []
    for ln in atom_lines:
        m = _ATOM_LINE_RE.match(ln)
        if not m:
            bad.append(ln.strip()[:40])
            continue
        if m.group(1).capitalize() not in _ELEMENTS:
            bad.append(f"未知元素 '{m.group(1)}'")
    if bad:
        raise ValueError(f"XYZ 存在非法原子行: {'; '.join(bad[:3])}")


# ─────────────────────────────────────────────────────────────
# 输出格式化
# ─────────────────────────────────────────────────────────────

def force_stats(forces: list) -> dict:
    """由 forces 计算最大/均方根受力，并找出受力最大的原子。"""
    mags = [math.sqrt(sum(c * c for c in f)) for f in forces]
    if not mags:
        return {"max": 0.0, "rms": 0.0, "argmax": -1}
    rms = math.sqrt(sum(m * m for m in mags) / len(mags))
    idx = max(range(len(mags)), key=lambda i: mags[i])
    return {"max": max(mags), "rms": rms, "argmax": idx, "mags": mags}


def format_predict_report(data: dict, label: str, model: str = "") -> str:
    """单点计算报告。"""
    natoms = data.get("natoms", 0)
    elements = data.get("elements") or []
    forces = data.get("forces_ev_per_ang") or []
    energy = data.get("energy_ev")

    L = []
    L.append("=" * 62)
    L.append(f"  EqV2 单点计算  |  {label}")
    L.append("=" * 62)
    if model:
        L.append(f"  模型      : {model} (机器学习势，非 DFT)")
    L.append(f"  原子数    : {natoms}")
    if elements:
        L.append(f"  元素组成  : {','.join(elements)}")
    L.append(f"  总能量    : {energy} eV")
    L.append("")

    if forces:
        st = force_stats(forces)
        L.append("  [受力统计]  单位: eV/Å")
        L.append("  " + "-" * 40)
        L.append(f"    最大受力 |F|max = {st['max']:.6f}")
        L.append(f"    均方根   |F|rms = {st['rms']:.6f}")
        if st["argmax"] >= 0 and st["argmax"] < len(elements):
            L.append(
                f"    受力最大原子    = #{st['argmax']} {elements[st['argmax']]}"
            )
        L.append("")

        # 逐原子表封顶 —— 大分子下这表能到 200 行，全塞进 prompt 不值得
        cap = 20
        order = sorted(range(len(forces)),
                       key=lambda i: st["mags"][i], reverse=True)
        shown = order[:cap]
        L.append(f"  [逐原子受力]  按 |F| 降序，显示前 {min(cap, len(forces))} 个")
        L.append("  " + "-" * 40)
        L.append("     idx  elem        Fx          Fy          Fz        |F|")
        for i in sorted(shown):
            f = forces[i]
            elem = elements[i] if i < len(elements) else "?"
            L.append(
                f"    {i:>4}  {elem:<4s} {f[0]:>11.5f} {f[1]:>11.5f} "
                f"{f[2]:>11.5f} {st['mags'][i]:>10.5f}"
            )
        if len(forces) > cap:
            L.append(f"    ... 其余 {len(forces) - cap} 个原子见产物 JSON")
        L.append("")

    bond = data.get("bond_analysis")
    if bond:
        L.append("  [键几何分析]")
        L.append("  " + "-" * 40)
        center = bond.get("center_atom") or {}
        if center:
            L.append(f"    中心原子: #{center.get('index')} {center.get('symbol')}")
        for key in ("bond_1", "bond_2", "bond_3", "bond_4"):
            b = bond.get(key)
            if isinstance(b, dict):
                L.append(
                    f"    {key}    : #{b.get('index')} {b.get('symbol')}  "
                    f"键长 {b.get('length_ang')} Å"
                )
        if bond.get("angle_deg") is not None:
            L.append(f"    键角    : {bond.get('angle_deg')} °")
        L.append("")
        L.append("  ⚠️ 以上仅为面向首个原子的简单几何分析，")
        L.append("     不等同于完整化学键分析（无键级/键能结论）。")

    L.append("=" * 62)
    return "\n".join(L)


def format_relax_report(job: dict, label: str, model: str = "",
                        artifacts: dict = None) -> str:
    """结构优化报告 —— **只出摘要**，轨迹落盘。

    见模块 docstring：trajectory 可能有几百步，原样回传会撑爆上下文。
    """
    result = job.get("result") or {}
    status = job.get("status")
    job_id = job.get("job_id", "-")
    converged = result.get("converged")

    L = []
    L.append("=" * 62)
    L.append(f"  EqV2 结构优化  |  {label}")
    L.append("=" * 62)
    if model:
        L.append(f"  模型      : {model} (机器学习势，非 DFT)")
    L.append(f"  作业 ID   : {job_id}")
    L.append(f"  作业状态  : {status}")
    L.append("")

    if status == "failed" or not result:
        L.append("  ⚠️ 作业未能返回结果。请向服务方报告该作业 ID。")
        L.append("=" * 62)
        return "\n".join(L)

    L.append("  [能量]  单位: eV")
    L.append("  " + "-" * 40)
    L.append(f"    初始能量      = {result.get('initial_energy_ev')}")
    L.append(f"    最终能量      = {result.get('final_energy_ev')}")
    L.append(f"    能量变化      = {result.get('energy_change_ev')}")
    L.append("")
    L.append("  [受力]  单位: eV/Å")
    L.append("  " + "-" * 40)
    L.append(f"    初始 |F|max   = {result.get('initial_fmax_ev_per_ang')}")
    L.append(f"    最终 |F|max   = {result.get('final_fmax_ev_per_ang')}")
    L.append(f"    收敛阈值 fmax = {result.get('fmax_threshold')}")
    L.append("")
    L.append("  [收敛判定]")
    L.append("  " + "-" * 40)
    L.append(f"    converged     = {converged}")
    L.append(f"    步数          = {result.get('nsteps')} / {result.get('max_steps')}")
    L.append("")

    # ── 结论段：这一节的口径必须明确，否则 LLM 会把 completed 当收敛 ──
    if converged is True:
        L.append("  ✅ 几何优化**已收敛**：最终最大受力低于 fmax 阈值。")
    else:
        L.append("  ❌ 几何优化**未收敛**：已用满步数仍未达到 fmax 阈值。")
        L.append(f"     最终 |F|max = {result.get('final_fmax_ev_per_ang')} eV/Å，"
                 f"阈值 = {result.get('fmax_threshold')} eV/Å。")
        L.append("     下载的结构是「当前最优中间构型」，不是收敛构型。")
        L.append("     如需收敛，可提高 max_steps 后重试。")
    L.append("")
    L.append("  ⚠️ 注意：作业状态 completed 只表示流程执行结束，")
    L.append("     是否收敛**只以 result.converged 为准**。")
    L.append("")

    if artifacts:
        L.append("  [完整产物]")
        L.append("  " + "-" * 40)
        for name, path in artifacts.items():
            L.append(f"    {name:<12s}: {path}")
        L.append("")
        L.append("    轨迹含全部步数的能量与受力，需要画收敛曲线或逐步分析时，")
        L.append("    用 read_file / python_repl 读取上述文件（报告只给摘要）。")

    L.append("=" * 62)
    return "\n".join(L)


# ─────────────────────────────────────────────────────────────
# 落盘
# ─────────────────────────────────────────────────────────────

def save_json(obj, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


def save_text(text: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def save_trajectory_csv(trajectory: list, path: Path) -> Path:
    """把 trajectory 写成 CSV。这就是"报告只出摘要"的底气所在。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["step,energy_ev,fmax_ev_per_ang"]
    for point in trajectory or []:
        lines.append(
            f"{point.get('step')},{point.get('energy_ev')},"
            f"{point.get('fmax_ev_per_ang')}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
