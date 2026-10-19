"""附件模块（app/utils/attachment.py）的单元测试。

用法（必须从 backend/ 运行）:
    python tests/test_attachments.py        # 直接跑，退出码即结论
    pytest tests/test_attachments.py        # 若装了 pytest 也能收集

⚠️ 本项目**没有装 pytest**，也没有 pytest 配置（tests/ 里多是把占位脚本、
   其中几个在 import 期就会真发 LLM 请求）。所以这里刻意写成**两种方式都能跑**：
   测试函数一律叫 test_* 且**不接 fixture**，自己管临时目录与 settings 覆盖
   （fixture 参数会让直接 python 运行变得别扭）；main() 汇总结果并给出退出码。

⚠️ 全部用例都不往仓库里写东西 —— 目录由 _patched() 重定向到临时目录。
"""

import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from app.utils import attachment as A  # noqa: E402
from config.settings import settings  # noqa: E402
from tools.eqv2 import parser as P  # noqa: E402

WATER_XYZ = (
    "3\nwater\n"
    "O 0.000000 0.000000 0.117790\n"
    "H 0.000000 0.755450 -0.471160\n"
    "H 0.000000 -0.755450 -0.471160\n"
)

WATER_GJF = """%chk=water.chk
%mem=4GB
#p B3LYP/6-311+G(d,p) opt

water dipole moment

0 1
O   0.000000   0.000000   0.117790
H   0.000000   0.755450  -0.471160
H   0.000000  -0.755450  -0.471160

"""


@contextmanager
def _patched(**overrides):
    """临时覆盖 settings 上的属性，退出时还原；并给一个干净的临时数据目录。"""
    tmp = Path(tempfile.mkdtemp(prefix="att-test-"))
    saved = {}
    try:
        overrides.setdefault("ATTACHMENT_DATA_DIR", str(tmp))
        for k, v in overrides.items():
            saved[k] = getattr(settings, k)
            setattr(settings, k, v)
        yield tmp
    finally:
        for k, v in saved.items():
            setattr(settings, k, v)
        shutil.rmtree(tmp, ignore_errors=True)


def _expect_error(payload, code):
    """断言 build_attachment 抛 AttachmentError 且 code 匹配，返回该异常。"""
    try:
        A.build_attachment(payload)
    except A.AttachmentError as e:
        assert e.code == code, f"期望 code={code}，实际 {e.code}: {e}"
        return e
    raise AssertionError(f"期望抛 AttachmentError({code})，但没有抛异常")


# ─────────────────────────────────────────────────────────────
# 正常路径
# ─────────────────────────────────────────────────────────────

def test_xyz_format_ok():
    with _patched() as tmp:
        att = A.build_attachment({"format": "xyz", "data": WATER_XYZ})
        assert att.natoms == 3, att.natoms
        assert att.formula == "H2O", att.formula
        assert att.elements == ("O", "H", "H"), att.elements
        assert att.source_format == "xyz"
        assert att.path.exists(), "附件应已落盘"
        assert att.path.parent == tmp, f"应落在临时目录内，实际 {att.path.parent}"


def test_saved_file_roundtrip():
    """落盘的内容必须能被工具侧解析器原样读回（闭环）。"""
    with _patched():
        att = A.build_attachment({"format": "xyz", "data": WATER_XYZ})
        back = P.read_xyz_text(str(att.path))
        assert P.count_atoms(back) == att.natoms
        assert back == att.xyz, "读回的内容应与规范 XYZ 完全一致"


def test_file_format_gaussian():
    """上传 Gaussian 输入文件（format='file'）也应能解析出原子块。"""
    with _patched():
        att = A.build_attachment(
            {"format": "file", "data": WATER_GJF, "filename": "water.gjf"}
        )
        assert att.natoms == 3, att.natoms
        assert att.source_format == "file"
        assert att.filename == "water.gjf"


def test_formula_hill_notation():
    """Hill 记法：C 在前、H 次之，其余元素按字母序。"""
    with _patched():
        benzene = (
            "12\nbenzene\n"
            "C 0.0000 1.3940 0.0000\n"
            "C 1.2070 0.6970 0.0000\n"
            "C 1.2070 -0.6970 0.0000\n"
            "C 0.0000 -1.3940 0.0000\n"
            "C -1.2070 -0.6970 0.0000\n"
            "C -1.2070 0.6970 0.0000\n"
            "H 0.0000 2.4790 0.0000\n"
            "H 2.1470 1.2390 0.0000\n"
            "H 2.1470 -1.2390 0.0000\n"
            "H 0.0000 -2.4790 0.0000\n"
            "H -2.1470 -1.2390 0.0000\n"
            "H -2.1470 1.2390 0.0000\n"
        )
        att = A.build_attachment({"format": "xyz", "data": benzene})
        assert att.formula == "C6H6", att.formula
        assert att.natoms == 12, att.natoms

    # 无碳时全按字母序：H2O 而不是 OH2
    with _patched():
        att = A.build_attachment({"format": "xyz", "data": WATER_XYZ})
        assert att.formula == "H2O", att.formula


# ─────────────────────────────────────────────────────────────
# 文件名的目录穿越 —— 本轮最重要的断言
# ─────────────────────────────────────────────────────────────

def test_filename_traversal_blocked():
    """POSIX 反斜杠形式的目录穿越必须被挡住。"""
    with _patched() as tmp:
        att = A.build_attachment(
            {"format": "file", "data": WATER_XYZ, "filename": "../../../../evil.xyz"}
        )
        assert att.path.parent.resolve() == tmp.resolve(), \
            f"落盘逃出了数据目录: {att.path}"
        name = att.path.name
        assert "/" not in name and "\\" not in name and ".." not in name, name


def test_filename_backslash_traversal_blocked():
    """Windows 反斜杠形式的目录穿越同样要挡住。

    这条专门盯住「先归一反斜杠再取 .name」那一行 —— 少了它
    Path("..\\\\..\\\\evil.xyz").name 在 POSIX 语义下会返回整串。
    """
    with _patched() as tmp:
        att = A.build_attachment(
            {"format": "file", "data": WATER_XYZ, "filename": "..\\..\\evil.xyz"}
        )
        assert att.path.parent.resolve() == tmp.resolve(), \
            f"落盘逃出了数据目录: {att.path}"
        assert "\\" not in att.path.name, att.path.name
        assert ".." not in att.path.name, att.path.name


def test_filename_absolute_path_stripped():
    with _patched() as tmp:
        att = A.build_attachment(
            {"format": "file", "data": WATER_XYZ, "filename": "/etc/passwd.xyz"}
        )
        assert att.path.parent.resolve() == tmp.resolve()
        assert att.path.name.startswith("passwd"), att.path.name


def test_chinese_filename_display_kept_disk_sanitized():
    """中文文件名：展示层保留，磁盘名走 ASCII。

    _safe_label 会把所有非 ASCII 替换掉，所以磁盘上的 label 不含中文 ——
    这是刻意的（与 eqv2 产物名清洗共用同一份逻辑）。但**用户可见的两处**
    （附件 chip 的 filename、上下文块的「原始文件名」）必须保留中文原名。
    """
    with _patched():
        att = A.build_attachment(
            {"format": "file", "data": WATER_XYZ, "filename": "水分子.xyz"}
        )
        assert att.filename == "水分子.xyz", att.filename
        assert "水分子" in att.to_context_block(), "上下文块应显示原始中文名"
        assert att.to_event_data()["filename"] == "水分子.xyz"
        # 磁盘名必须是安全 ASCII，且不能退化成 _safe_label 的 "eqv2" 哨兵
        assert att.path.name.isascii(), att.path.name
        assert not att.path.name.startswith("eqv2"), att.path.name
        assert att.path.name.startswith("structure_"), att.path.name


# ─────────────────────────────────────────────────────────────
# 各类拒绝
# ─────────────────────────────────────────────────────────────

def test_mol_rejected():
    with _patched():
        e = _expect_error(
            {"format": "file", "data": "whatever", "filename": "x.mol"},
            A.CODE_FORMAT,
        )
        # 文案要点明"不支持什么"与"该用什么"
        assert ".mol" in str(e), str(e)
        assert ".xyz" in str(e), str(e)


def test_sdf_rejected():
    with _patched():
        _expect_error(
            {"format": "file", "data": "whatever", "filename": "x.sdf"},
            A.CODE_FORMAT,
        )


def test_smiles_rejected():
    with _patched():
        e = _expect_error({"format": "smiles", "data": "c1ccccc1"}, A.CODE_FORMAT)
        assert "SMILES" in str(e) or "RDKit" in str(e), str(e)


def test_unknown_format_rejected():
    with _patched():
        _expect_error({"format": "pickle", "data": WATER_XYZ}, A.CODE_FORMAT)


def test_bad_text_rejected():
    with _patched():
        _expect_error({"format": "xyz", "data": "这不是一个分子结构"}, A.CODE_PARSE)


def test_empty_rejected():
    with _patched():
        _expect_error({"format": "xyz", "data": "   \n  \n"}, A.CODE_EMPTY)


def test_missing_data_rejected():
    with _patched():
        _expect_error({"format": "xyz"}, A.CODE_FORMAT)


def test_non_dict_rejected():
    with _patched():
        _expect_error("not a dict", A.CODE_FORMAT)  # type: ignore[arg-type]


def test_oversize_text_rejected():
    with _patched(ATTACHMENT_MAX_BYTES=256):
        big = WATER_XYZ + ("# padding\n" * 100)
        e = _expect_error({"format": "xyz", "data": big}, A.CODE_TOO_LARGE)
        # 尺寸检查必须先于解析：报错里应出现字节数，而不是"无法解析"
        assert "字节" in str(e), str(e)


def test_atom_count_mismatch_rejected():
    """首行声明 3 个原子但只给 2 行 —— 应归为解析/校验失败。"""
    with _patched():
        _expect_error(
            {"format": "xyz", "data": "3\nbad\nO 0 0 0\nH 0 0 1\n"},
            A.CODE_PARSE,
        )


def test_atom_cap_reads_settings():
    """原子上限必须读 settings，不能硬编码 —— 用 monkeypatch 证明。"""
    with _patched(EQV2_MAX_ATOMS=2):
        e = _expect_error({"format": "xyz", "data": WATER_XYZ}, A.CODE_TOO_LARGE)
        assert "3" in str(e) and "2" in str(e), str(e)


# ─────────────────────────────────────────────────────────────
# 上下文块 / 事件数据：路径形态（首要风险的防线）
# ─────────────────────────────────────────────────────────────

def test_context_block_has_no_backslash():
    """⚠️ 本文件最要紧的一条断言。

    上下文块里只要出现反斜杠形式的绝对路径，LLM 就可能写出非法 JSON 转义，
    导致整轮静默降级成"空计划"（工具不跑、无报错）。见模块 docstring。
    """
    with _patched():
        att = A.build_attachment({"format": "xyz", "data": WATER_XYZ})
        ctx = att.to_context_block()
        assert "\\" not in ctx, f"上下文块出现了反斜杠: {ctx}"
        assert att.path.as_posix() in ctx, "上下文块应含 POSIX 形式的路径"
        assert "input_file" in ctx, "必须明确告诉 Planner 用哪个参数"
        assert str(att.natoms) in ctx and att.formula in ctx


def test_event_data_hides_absolute_path():
    """回传前端的路径应是相对的，不该泄露服务器上的绝对目录。"""
    with _patched() as tmp:
        att = A.build_attachment({"format": "xyz", "data": WATER_XYZ})
        data = att.to_event_data()
        assert data["natoms"] == 3 and data["formula"] == "H2O"
        assert not str(data["path"]).startswith(str(tmp)), data["path"]
        assert tmp.name not in str(data["path"]), f"泄露了临时目录名: {data['path']}"
        assert data["path"].endswith(".xyz"), data["path"]


# ─────────────────────────────────────────────────────────────
# 路径钉扎
# ─────────────────────────────────────────────────────────────

def test_pin_rewrites_only_matching():
    """只改写指向本附件的那条，别人的路径（如 .fchk）一律不碰。"""
    with _patched():
        att = A.build_attachment({"format": "xyz", "data": WATER_XYZ})
        plan = [
            {"type": "tool", "step": "eqv2_relax",
             "params": {"input_file": "D:\\some\\wrong\\dir\\" + att.path.name,
                        "fmax": 0.3}},
            {"type": "tool", "step": "homo_lumo",
             "params": {"fchk_path": "D:\\other\\thing.fchk"}},
        ]
        n = A.pin_attachment_paths(plan, att)
        assert n == 1, f"应只改写 1 条，实际 {n}"
        assert plan[0]["params"]["input_file"] == att.path.as_posix()
        assert plan[0]["params"]["fmax"] == 0.3, "不该动其它参数"
        assert plan[1]["params"]["fchk_path"] == "D:\\other\\thing.fchk", \
            "不该碰指向别的文件的路径"


def test_pin_moves_path_out_of_xyz_param():
    """Planner 把路径塞进 xyz 参数时应挪到 input_file —— 否则用户看到莫名其妙的报错。"""
    with _patched():
        att = A.build_attachment({"format": "xyz", "data": WATER_XYZ})
        plan = [{"type": "tool", "step": "eqv2_predict",
                 "params": {"xyz": att.path.name}}]
        n = A.pin_attachment_paths(plan, att)
        assert n == 1
        assert "xyz" not in plan[0]["params"], "应把 xyz 参数摘掉"
        assert plan[0]["params"]["input_file"] == att.path.as_posix()


def test_pin_ignores_inline_xyz_text():
    """值是真 XYZ 文本（含换行）时，绝不能被当成路径匹配。"""
    with _patched():
        att = A.build_attachment({"format": "xyz", "data": WATER_XYZ})
        plan = [{"type": "tool", "step": "eqv2_predict", "params": {"xyz": WATER_XYZ}}]
        n = A.pin_attachment_paths(plan, att)
        assert n == 0, "内联 XYZ 文本不该被改写"
        assert plan[0]["params"]["xyz"] == WATER_XYZ


def test_pin_handles_malformed_plan():
    with _patched():
        att = A.build_attachment({"format": "xyz", "data": WATER_XYZ})
        assert A.pin_attachment_paths([], att) == 0
        assert A.pin_attachment_paths(None, att) == 0            # type: ignore[arg-type]
        assert A.pin_attachment_paths(["not a dict"], att) == 0
        assert A.pin_attachment_paths([{"params": None}], att) == 0


# ─────────────────────────────────────────────────────────────
# 运行器（无 pytest 时也能跑）
# ─────────────────────────────────────────────────────────────

def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = []
    print(f"\n附件模块单元测试 —— 共 {len(tests)} 项\n" + "─" * 62)
    for name, fn in tests:
        try:
            fn()
            print(f"  [PASS] {name}")
        except Exception as e:  # noqa: BLE001
            failed.append(name)
            print(f"  [FAIL] {name}\n         {type(e).__name__}: {e}")
    print("─" * 62)
    print(f"  通过 {len(tests) - len(failed)} / {len(tests)}")
    if failed:
        print("  失败项:")
        for f in failed:
            print(f"    ✗ {f}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
