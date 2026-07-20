"""
HOMO-LUMO 分析工具 — 从 Gaussian .fchk 文件中提取轨道能

Agent 入口函数: run_homo_lumo(fchk_path, num_around=5)
"""

import os
import re


# ─── 解析 .fchk 文件（内部函数，逻辑不变）───────────────

def _parse_fchk(fchk_path: str) -> dict:
    """解析 .fchk，返回 {num_electrons, alpha_energies, beta_energies, total_energy}"""

    with open(fchk_path, "r") as f:
        lines = f.readlines()

    result = {
        "num_electrons": None,
        "alpha_energies": [],
        "beta_energies": [],
        "total_energy": None,
    }

    for line in lines:
        # 电子数
        if "Number of electrons" in line and "I" in line:
            parts = line.split()
            for i, p in enumerate(parts):
                if p == "I":
                    result["num_electrons"] = int(parts[i + 1])
                    break

        # 总能量
        if "Total Energy" in line and "R" in line:
            parts = line.split()
            for i, p in enumerate(parts):
                if p == "R":
                    result["total_energy"] = float(parts[i + 1].replace("D", "E"))
                    break

    result["alpha_energies"] = _parse_section(lines, "Alpha Orbital Energies")
    result["beta_energies"] = _parse_section(lines, "Beta Orbital Energies")

    return result


def _parse_section(lines: list[str], section_name: str) -> list[float]:
    """从 fchk 的命名段中提取浮点数数组"""
    energies = []
    in_section = False
    for line in lines:
        if section_name in line and "N=" in line:
            in_section = True
            continue
        if in_section:
            stripped = line.strip()
            if not stripped:
                break
            # 碰到下一个段标题就停: "Text ... I/R   N="
            if re.match(r"^[A-Za-z].*\b[IR]\s+N=", stripped):
                break
            for token in stripped.split():
                try:
                    energies.append(float(token.replace("D", "E")))
                except ValueError:
                    pass
    return energies


# ─── Agent 入口函数 ─────────────────────────────────

def run_homo_lumo(fchk_path: str, num_around: int = 5) -> str:
    """
    从 Gaussian .fchk 文件中提取 HOMO/LUMO 轨道能量，计算能隙。

    参数:
        fchk_path:  .fchk 文件路径（必填）
        num_around: 能隙附近显示的轨道数，默认 5

    返回:
        格式化的分析报告（纯文本）
    """
    # 1. 检查文件存在
    if not os.path.isfile(fchk_path):
        return f"[ERROR] 文件不存在: {fchk_path}"

    # 2. 解析
    try:
        data = _parse_fchk(fchk_path)
    except Exception as e:
        return f"[ERROR] 解析 .fchk 文件失败: {e}"

    # 3. 检查数据完整性
    nelec = data["num_electrons"]
    alpha = data["alpha_energies"]
    beta = data["beta_energies"]

    if nelec is None or len(alpha) == 0:
        return "[ERROR] 无法解析电子数或轨道能量，请检查 .fchk 文件是否完整"

    has_beta = len(beta) > 0

    # 4. 构建报告
    lines = []
    lines.append("=" * 60)
    lines.append("  HOMO / LUMO  Analysis")
    lines.append("=" * 60)
    lines.append(f"  File:       {os.path.basename(fchk_path)}")
    if data["total_energy"]:
        lines.append(f"  E_total:    {data['total_energy']:.8f} Hartree")
    lines.append(f"  Electrons:  {nelec}")
    lines.append(f"  Orbitals:   {len(alpha)} alpha" + (f", {len(beta)} beta" if has_beta else ""))
    lines.append("")

    if not has_beta:
        # ── Restricted closed-shell ──
        n_occ = nelec // 2
        homo_e = alpha[n_occ - 1]
        lumo_e = alpha[n_occ]
        gap = lumo_e - homo_e

        lines.append(f"  Type:       Restricted (closed-shell)")
        lines.append(f"  HOMO:       orb #{n_occ}     = {homo_e:10.6f} Hartree  ({homo_e * 27.2114:7.2f} eV)")
        lines.append(f"  LUMO:       orb #{n_occ + 1}   = {lumo_e:10.6f} Hartree  ({lumo_e * 27.2114:7.2f} eV)")
        lines.append(f"  Gap (dE):   {gap:10.6f} Hartree  ({gap * 27.2114:7.2f} eV)")
        lines.append("")

        lines.append(f"  Orbitals around the gap (+-{num_around}):")
        start = max(0, n_occ - 1 - num_around)
        end = min(len(alpha), n_occ + num_around)
        for i in range(start, end):
            tag = ""
            if i == n_occ - 1:
                tag = " <- HOMO"
            elif i == n_occ:
                tag = " <- LUMO"
            occ = "occ" if i < n_occ else "vir"
            lines.append(f"    #{i+1:4d}  {alpha[i]:12.6f} Hartree  [{occ}]{tag}")

    else:
        # ── Unrestricted (open-shell) ──
        n_alpha = nelec // 2 + (nelec % 2)
        n_beta = nelec - n_alpha

        lines.append("  Type:       Unrestricted (open-shell)")

        if n_alpha > 0 and n_alpha < len(alpha):
            alpha_homo = alpha[n_alpha - 1]
            alpha_lumo = alpha[n_alpha]
            alpha_gap = alpha_lumo - alpha_homo
            lines.append(f"  Alpha HOMO: orb #{n_alpha}     = {alpha_homo:10.6f} Hartree  ({alpha_homo * 27.2114:7.2f} eV)")
            lines.append(f"  Alpha LUMO: orb #{n_alpha + 1}   = {alpha_lumo:10.6f} Hartree  ({alpha_lumo * 27.2114:7.2f} eV)")
            lines.append(f"  Alpha Gap:  {alpha_gap:10.6f} Hartree  ({alpha_gap * 27.2114:7.2f} eV)")

        if n_beta > 0 and n_beta < len(beta):
            beta_homo = beta[n_beta - 1]
            beta_lumo = beta[n_beta]
            beta_gap = beta_lumo - beta_homo
            lines.append(f"  Beta  HOMO: orb #{n_beta}     = {beta_homo:10.6f} Hartree  ({beta_homo * 27.2114:7.2f} eV)")
            lines.append(f"  Beta  LUMO: orb #{n_beta + 1}   = {beta_lumo:10.6f} Hartree  ({beta_lumo * 27.2114:7.2f} eV)")
            lines.append(f"  Beta  Gap:  {beta_gap:10.6f} Hartree  ({beta_gap * 27.2114:7.2f} eV)")

    lines.append("")
    lines.append("=" * 60)

    return "\n".join(lines)
