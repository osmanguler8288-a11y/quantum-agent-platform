"""
偶极矩 & 多极矩提取工具 — 从 Gaussian .out 文件中提取偶极矩

Agent 入口函数: run_dipole(out_path, extract_quadrupole=False, extract_traceless=False)
"""

import re
import sys
import argparse
from pathlib import Path


# ============================================================
# 解析器（内部函数，逻辑不变）
# ============================================================

def _parse_dipole(text: str) -> dict | None:
    """从 .out 文件内容中提取偶极矩 (Debye)。
    返回 dict: {X: float, Y: float, Z: float, Tot: float} 或 None
    """
    # 匹配行: "    X=             -1.2816    Y=             -1.3689    Z=              3.0977  Tot=              3.6210"
    m = re.search(
        r"Dipole moment.*Debye.*\n\s*X=\s*([-\d.]+)\s+Y=\s*([-\d.]+)\s+Z=\s*([-\d.]+)\s+Tot=\s*([-\d.]+)",
        text
    )
    if m:
        return {
            "X": float(m.group(1)),
            "Y": float(m.group(2)),
            "Z": float(m.group(3)),
            "Tot": float(m.group(4)),
        }
    return None


def _parse_quadrupole(text: str) -> dict | None:
    """从 .out 文件内容中提取四极矩 (Debye-Ang)。
    返回 dict 或 None
    """
    # Quadrupole moment (field-independent basis, Debye-Ang):
    #   XX=           -108.2001   YY=           -113.5836   ZZ=           -129.0184
    #   XY=             -4.3293   XZ=              9.4262   YZ=             -0.2010
    m = re.search(
        r"Quadrupole moment.*Debye-Ang.*\n"
        r"\s*XX=\s*([-\d.]+)\s+YY=\s*([-\d.]+)\s+ZZ=\s*([-\d.]+)\s*\n"
        r"\s*XY=\s*([-\d.]+)\s+XZ=\s*([-\d.]+)\s+YZ=\s*([-\d.]+)",
        text
    )
    if m:
        return {
            "XX": float(m.group(1)),
            "YY": float(m.group(2)),
            "ZZ": float(m.group(3)),
            "XY": float(m.group(4)),
            "XZ": float(m.group(5)),
            "YZ": float(m.group(6)),
        }
    return None


def _parse_traceless_quadrupole(text: str) -> dict | None:
    """提取无迹四极矩 (Debye-Ang)。"""
    m = re.search(
        r"Traceless Quadrupole moment.*Debye-Ang.*\n"
        r"\s*XX=\s*([-\d.]+)\s+YY=\s*([-\d.]+)\s+ZZ=\s*([-\d.]+)\s*\n"
        r"\s*XY=\s*([-\d.]+)\s+XZ=\s*([-\d.]+)\s+YZ=\s*([-\d.]+)",
        text
    )
    if m:
        return {
            "XX": float(m.group(1)),
            "YY": float(m.group(2)),
            "ZZ": float(m.group(3)),
            "XY": float(m.group(4)),
            "XZ": float(m.group(5)),
            "YZ": float(m.group(6)),
        }
    return None


# ─── Agent 入口函数 ─────────────────────────────────

def run_dipole(
    out_path: str,
    extract_quadrupole: bool = False,
    extract_traceless: bool = False,
) -> str:
    """
    从 Gaussian .out 文件中提取偶极矩（Dipole Moment）和可选的多极矩。

    参数:
        out_path:              Gaussian .out 文件路径（必填）
        extract_quadrupole:    是否同时提取四极矩，默认 False
        extract_traceless:     是否同时提取无迹四极矩，默认 False

    返回:
        格式化的分析报告（纯文本）
    """
    # 1. 检查文件存在
    p = Path(out_path)
    if not p.exists():
        return f"[ERROR] 文件不存在: {out_path}"

    # 2. 读取文件内容
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception as e:
        return f"[ERROR] 无法读取文件: {e}"

    # 3. 解析偶极矩（核心数据）
    dipole = _parse_dipole(text)
    if dipole is None:
        return f"[WARN] 在 {p.name} 中未找到偶极矩，请确认是 Gaussian 单点能 .out 文件"

    # 4. 构建报告
    lines = []
    lines.append("=" * 60)
    lines.append(f"  File: {p.name}")
    lines.append("=" * 60)
    lines.append("")
    lines.append("  [Dipole Moment] (Debye)")
    lines.append("  " + "-" * 30)
    lines.append(f"    X   = {dipole['X']:>12.4f}")
    lines.append(f"    Y   = {dipole['Y']:>12.4f}")
    lines.append(f"    Z   = {dipole['Z']:>12.4f}")
    lines.append("  " + "-" * 30)
    lines.append(f"    Tot = {dipole['Tot']:>12.4f}  Debye")
    lines.append("")

    # 5. 可选: 四极矩
    if extract_quadrupole:
        quad = _parse_quadrupole(text)
        if quad:
            lines.append("  [Quadrupole Moment] (Debye-Ang)")
            lines.append("  " + "-" * 30)
            for comp in ["XX", "YY", "ZZ", "XY", "XZ", "YZ"]:
                lines.append(f"    {comp}  = {quad[comp]:>12.4f}")
            lines.append("")
        else:
            lines.append("  [Quadrupole Moment] NOT FOUND")
            lines.append("")

    # 6. 可选: 无迹四极矩
    if extract_traceless:
        trace = _parse_traceless_quadrupole(text)
        if trace:
            lines.append("  [Traceless Quadrupole] (Debye-Ang)")
            lines.append("  " + "-" * 30)
            for comp in ["XX", "YY", "ZZ", "XY", "XZ", "YZ"]:
                lines.append(f"    {comp}  = {trace[comp]:>12.4f}")
            lines.append("")
        else:
            lines.append("  [Traceless Quadrupole] NOT FOUND")
            lines.append("")

    lines.append("=" * 60)

    return "\n".join(lines)


# ============================================================
# CLI 入口（保留向后兼容）
# ============================================================

def _format_single(name: str, dipole: dict, quad=None, traceless=None) -> str:
    """格式化单个文件的偶极矩 + 多极矩（供 CLI 使用）"""
    return run_dipole(
        out_path=name,
        extract_quadrupole=quad is not None or traceless is not None,
        extract_traceless=traceless is not None,
    )


def _print_comparison(results: list):
    """批量对比表格"""
    print(f"\n{'File':<30s} {'X':>10s} {'Y':>10s} {'Z':>10s} {'Tot':>10s}")
    print("-" * 70)
    for name, dipole in results:
        if dipole:
            print(f"{name:<30s} {dipole['X']:+10.4f} {dipole['Y']:+10.4f} "
                  f"{dipole['Z']:+10.4f} {dipole['Tot']:10.4f}")
        else:
            print(f"{name:<30s} {'N/A':>10s} {'N/A':>10s} {'N/A':>10s} {'N/A':>10s}")


def _export_csv(results: list, csv_path: str):
    """导出批量结果为 CSV"""
    with open(csv_path, "w", encoding="utf-8-sig") as f:
        f.write("file,dipole_x,dipole_y,dipole_z,dipole_tot\n")
        for name, dipole in results:
            if dipole:
                f.write(f'"{name}",{dipole["X"]:.6f},{dipole["Y"]:.6f},'
                        f'{dipole["Z"]:.6f},{dipole["Tot"]:.6f}\n')
            else:
                f.write(f'"{name}",,,,\n')
    print(f"\n[DONE] CSV saved: {csv_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Gaussian .out 偶极矩 & 多极矩提取器"
    )
    parser.add_argument("out_files", nargs="+", help="一个或多个 .out 文件")
    parser.add_argument("--csv", default=None,
                        help="批量模式: 输出 CSV 路径")
    parser.add_argument("--quadrupole", action="store_true",
                        help="同时提取四极矩")
    parser.add_argument("--traceless", action="store_true",
                        help="同时提取无迹四极矩")
    args = parser.parse_args()

    results = []
    for path_str in args.out_files:
        p = Path(path_str)
        if not p.exists():
            print(f"[SKIP] 文件不存在: {p}")
            continue

        dipole = _parse_dipole(p.read_text(encoding="utf-8", errors="replace"))
        results.append((p.name, dipole))

        if len(args.out_files) == 1 or args.csv is None:
            quad = _parse_quadrupole(p.read_text(encoding="utf-8", errors="replace")) if args.quadrupole else None
            trace = _parse_traceless_quadrupole(p.read_text(encoding="utf-8", errors="replace")) if args.traceless else None
            print(_format_single(p.name, dipole, quad, trace))

    # 批量对比
    if len(args.out_files) > 1:
        _print_comparison(results)

        if args.csv:
            _export_csv(results, args.csv)

    # 检查是否有任何结果
    if all(d is None for _, d in results):
        print("\n[WARNING] 所有文件均未找到偶极矩，请确认是 Gaussian 单点能 .out 文件")
        sys.exit(1)


if __name__ == "__main__":
    main()
