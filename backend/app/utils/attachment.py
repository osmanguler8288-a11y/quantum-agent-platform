"""用户上传的分子结构附件 —— 解析、净化、落盘，并把它交给 Planner。

═══════════════════════════════════════════════════════════════════════
这件事在链路里的位置
═══════════════════════════════════════════════════════════════════════

前端（`StructureInput.vue` 的三个标签页）已经把结构文本读出来，塞进
`input_data.structure` 随消息发到 `/api/workflow/stream`。本模块负责后半段：

    请求体 structure
      → 校验 + 净化文件名
      → parser.normalize_xyz 解析（同时吃 XYZ 文本与整段 Gaussian 输入）
      → 落盘成规范 XYZ
      → 交给 Planner 一段上下文（含文件路径）
      → Planner 把路径写进 eqv2_predict / eqv2_relax 的 params.input_file

**为什么不走 executor 的 `input_data`**：`agent/executor.py` 的
`{**input_data, **step.get("params", {})}` 是无 schema 过滤的字典合并，而
`MCPClient._call_local` 会 `tool.func(**params)` —— 任何工具不认识这个键就
TypeError 直接失败；键名若叫 `input_file` 更糟，会**同时**喂给 gaussian /
multiwfn / eqv2 而静默传错参数。何况 `workflow.py` 调 `execute_stream(state)`
时根本没传 input_data，那条路本来就通不了。所以路径**只能**由 Planner 显式
写进 params。

═══════════════════════════════════════════════════════════════════════
为什么上下文块里的路径必须是正斜杠（本模块最要紧的一处设计）
═══════════════════════════════════════════════════════════════════════

本机仓库路径形如 `D:\\自己做的项目\\Claude专属\\...`。若把这个串交给 LLM，
它在 JSON 里写单反斜杠，`\\自` 是**非法 JSON 转义** → `json.loads` 失败 →
`Planner._parse_response` 返回 `[]` → 命中 `workflow.py` 的「空计划」分支 →
**整轮变成一句聊天回复：工具一次没跑，用户零提示，日志里连个错误都没有。**

所以：`to_context_block()` 只输出 `Path.as_posix()`，并明写「不要转义」。
`pin_attachment_paths()` 再兜一层 —— 按 **basename** 匹配改写，只要 LLM 保住
了文件名（UUID 后缀那段它没有动机改），整条路径就能被救回来。

`tests/test_attachments.py` 里有一条断言专门盯着「上下文块不含反斜杠绝对路径」。

═══════════════════════════════════════════════════════════════════════
已知限制（有意为之，不是 bug）
═══════════════════════════════════════════════════════════════════════

- 附件**不落库**，刷新页面后消息里的附件标记会消失；文件仍在
  `data/attachments/` 下，可用路径再次引用。
- **不支持跨轮引用**：第二轮「再优化一下」拿不到上一轮的附件信息，
  用户需重新上传或手敲路径。
- `data/attachments/` **没有自动清理机制**（与 `data/eqv2/` 一致），
  需要时手工删目录。
- SMILES 输入不支持（项目未集成 RDKit，EqV2 也只接受 XYZ）。
"""

import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.utils.logger import logger
from config.settings import settings
from tools.eqv2 import parser as P

# 复用 eqv2 runner 的既有文件名清洗器。它是私有符号，但**必须**复用：
# 文件名清洗逻辑分叉出第二份实现才是真正的风险（两边规则一旦漂移，
# 落盘名与工具侧读回的名字就对不上）。将来若要做共享工具再提升到 tools/utils/。
from tools.eqv2.runner import _safe_label

# ── 错误码：同时作为 SSE error 事件的 code，前端据此把附件块标成失败 ──
CODE_EMPTY = "ATTACHMENT_EMPTY"
CODE_FORMAT = "ATTACHMENT_FORMAT"
CODE_PARSE = "ATTACHMENT_PARSE"
CODE_TOO_LARGE = "ATTACHMENT_TOO_LARGE"
CODE_WRITE = "ATTACHMENT_WRITE"

# 已知不支持的结构格式。命中就直接拒绝 —— 这些扩展名能通过前端的 accept，
# 但我们的解析器读不了，让它们走到解析失败只会给出难懂的错误。
_UNSUPPORTED_SUFFIXES = {".mol", ".sdf", ".pdb", ".cif", ".mol2"}

# 前端允许的 format（structure.format 字段）
_TEXT_FORMATS = ("xyz", "file")

_HINT_XYZ = "请提供 .xyz 坐标文件，或 Gaussian 输入文件（.gjf/.com）"


class AttachmentError(ValueError):
    """附件不合法。`code` 会透传到 SSE error 事件。"""

    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Attachment:
    """一份已解析、已落盘的结构附件。"""
    path: Path
    filename: str            # 浏览器原始文件名（已剥掉任何目录成分），仅用于展示
    natoms: int
    elements: tuple[str, ...]
    formula: str             # Hill 式，如 C6H6 / H2O
    xyz: str                 # 规范 XYZ 文本
    source_format: str       # 'xyz' | 'file'

    # ── 给 Planner：绝对 POSIX 路径 ────────────────────────
    def to_context_block(self) -> str:
        """注入 Planner 上下文的那一段。

        ⚠️ 路径用 `as_posix()`，理由见模块 docstring —— 反斜杠会让 LLM 写出
           非法 JSON 转义，进而让整轮静默降级成「空计划」。
        """
        return (
            "## 用户本轮上传的分子结构\n"
            "用户上传了一个结构文件，系统已解析、校验并保存为规范 XYZ：\n"
            f"- 文件路径（正斜杠形式，请**原样整串复制**，不要做任何转义）："
            f"{self.path.as_posix()}\n"
            f"- 原始文件名：{self.filename}\n"
            f"- 原子数：{self.natoms}\n"
            f"- 元素组成：{self.formula}\n"
            "调用 eqv2_predict / eqv2_relax 时，把 `input_file` 设为上面那个文件路径，"
            "整串原样复制；**不要**再传 `xyz` 参数，**不要**自己编造或猜测路径，"
            "也**不要**用 write_file 重新生成结构文件（结构已经在盘上了）。\n"
            "如果用户本轮的问题与这个结构无关（闲聊或问别的事），忽略本段。"
        )

    # ── 给前端：相对路径 ──────────────────────────────────
    def to_event_data(self) -> dict:
        """回传前端的元数据。

        这里给**相对 backend cwd 的路径**而不是绝对路径：一是它正是用户后续
        要引用时该敲的串（read_file / list_dir 都按 backend cwd 解析），
        二是绝对路径里含服务器上的中文目录，没必要回传给浏览器。
        """
        return {
            "filename": self.filename,
            "format": self.source_format,
            "natoms": self.natoms,
            "formula": self.formula,
            "path": _display_path(self.path),
        }


# ─────────────────────────────────────────────────────────────
# 构造
# ─────────────────────────────────────────────────────────────

def build_attachment(payload: dict) -> Attachment:
    """校验并落盘一份附件。失败抛 AttachmentError（带 code）。

    检查顺序本身就是设计：尺寸先于解析（不浪费解析）、格式先于解析
    （给出比"解析失败"更具体的文案）、原子上限先于 validate_xyz
    （这样"超上限"与"原子数不一致"能拿到不同的 code）。
    """
    # 1. 类型护栏
    if not isinstance(payload, dict):
        raise AttachmentError("附件数据格式不正确", CODE_FORMAT)
    data = payload.get("data")
    if not isinstance(data, str):
        raise AttachmentError("附件内容缺失或类型不正确", CODE_FORMAT)

    # 2. 尺寸（先于解析）
    size = len(data.encode("utf-8"))
    max_bytes = settings.ATTACHMENT_MAX_BYTES
    if size > max_bytes:
        raise AttachmentError(
            f"附件文本 {size} 字节，超过 {max_bytes} 字节上限。"
            f"分子结构文件通常不足 100 KB，请确认选对了文件。",
            CODE_TOO_LARGE,
        )

    # 3. 空
    if not data.strip():
        raise AttachmentError(
            "上传的内容是空的，请检查文件是否为文本格式的 XYZ 或 Gaussian 输入。",
            CODE_EMPTY,
        )

    # 4/5. format
    fmt = str(payload.get("format") or "xyz").strip().lower()
    if fmt == "smiles":
        raise AttachmentError(
            f"SMILES 输入暂不支持：后端未集成 RDKit，且 EqV2 只接受 XYZ 结构。{_HINT_XYZ}。",
            CODE_FORMAT,
        )
    if fmt not in _TEXT_FORMATS:
        raise AttachmentError(f"未知的结构格式 '{fmt}'", CODE_FORMAT)

    # 6. 文件名净化 —— 最关键的一步。
    # ⚠️ 必须先把反斜杠归一成 '/' 再取 .name：Windows 客户端发来的
    #    "..\\..\\evil.xyz" 在 POSIX 语义下 Path(...).name 会返回整串。
    raw_name = str(payload.get("filename") or "")
    base = Path(raw_name.replace("\\", "/")).name
    suffix = Path(base).suffix.lower()

    # 7. 已知不支持的格式：明确拒绝，别让它走到笼统的解析失败
    if suffix in _UNSUPPORTED_SUFFIXES:
        raise AttachmentError(
            f"暂不支持 {suffix} 格式。{_HINT_XYZ}。",
            CODE_FORMAT,
        )

    # ⚠️ _safe_label 用 `[^0-9A-Za-z_\-]+` 把所有非 ASCII 都替换成下划线，
    #    所以**中文文件名在磁盘上会整个消失**（水分子 → ""）。这是它作为 eqv2
    #    产物名清洗器的既有设计，对附件同样安全，故沿用、不另写第二份。
    #    用户可见的地方不受影响：display_name 用的是原始文件名（含中文），
    #    附件 chip 与上下文块的「原始文件名」都照原样显示。
    stem = Path(base).stem if base else ""
    label = _safe_label(stem) if stem else "structure"
    if label == "eqv2":
        # _safe_label 的空值哨兵是 "eqv2"（借用模型名）。它出现在附件文件名里
        # 语义不通，会让用户以为跟模型有关；换成中性的 structure。
        label = "structure"
    display_name = base or "structure.xyz"

    # 8. 解析。normalize_xyz 是嗅探式的：XYZ 文本与整段 Gaussian 输入都能吃，
    #    所以**不按扩展名分岔**（用户把 XYZ 存成 .txt 也该能用）。
    try:
        xyz = P.normalize_xyz(data, source_label=f"附件 {display_name}")
    except ValueError as e:
        raise AttachmentError(
            f"无法解析上传的结构（{display_name}）：{e}。{_HINT_XYZ}。",
            CODE_PARSE,
        ) from e

    # 9. 原子数上限：自己先判，好让超限与"原子数不一致"拿到不同的 code
    try:
        natoms = P.count_atoms(xyz)
    except (ValueError, IndexError) as e:
        raise AttachmentError(f"无法解析上传的结构（{display_name}）：{e}", CODE_PARSE) from e

    if natoms > settings.EQV2_MAX_ATOMS:
        raise AttachmentError(
            f"结构含 {natoms} 个原子，超过 EqV2 服务上限 {settings.EQV2_MAX_ATOMS}。"
            f"请裁剪结构后重试。",
            CODE_TOO_LARGE,
        )
    try:
        P.validate_xyz(xyz, settings.EQV2_MAX_ATOMS)
    except ValueError as e:
        raise AttachmentError(
            f"结构校验失败（{display_name}）：{e}", CODE_PARSE
        ) from e

    # 10. 元素
    lines = [ln for ln in xyz.splitlines() if ln.strip()]
    elements = tuple(ln.split()[0] for ln in lines[2:])

    # 11. 落盘
    path = _save(xyz, label)

    attachment = Attachment(
        path=path, filename=display_name, natoms=natoms, elements=elements,
        formula=_hill_formula(elements), xyz=xyz, source_format=fmt,
    )
    logger.bind(component="attachment").info(
        "[attachment] 已就绪 | file={} | natoms={} | formula={} | path={}",
        attachment.filename, natoms, attachment.formula, path,
    )
    return attachment


def _save(xyz: str, label: str) -> Path:
    """把规范 XYZ 写到 ATTACHMENT_DATA_DIR，返回落盘路径。

    ⚠️ settings 在**函数内**读，不要提成模块级常量 —— 否则测试无法用
       monkeypatch 重定向目录，原子上限同理。
    """
    data_dir = Path(settings.ATTACHMENT_DATA_DIR)

    # label 放在 uuid 之前：eqv2 的 runner 用 Path(input_file).stem 当产物名前缀，
    # 这样产物会是 benzene_a1b2c3d4_predict.json 而不是 a1b2c3d4_predict.json。
    path = data_dir / f"{label}_{uuid.uuid4().hex[:8]}.xyz"

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # 纵深防御：将来重构改坏了也不能写出目录
        if path.parent.resolve() != data_dir.resolve():
            raise AttachmentError("附件落盘路径越界（内部错误）", CODE_WRITE)
        # ⚠️ 不复用 parser.save_text：它没指定 newline，Windows 上会把 \n 翻成
        #    \r\n，让"规范"产物带上平台相关字节。
        path.write_text(xyz, encoding="utf-8", newline="\n")
    except AttachmentError:
        raise
    except OSError as e:
        raise AttachmentError(f"附件写入失败：{e}", CODE_WRITE) from e

    return path


# ─────────────────────────────────────────────────────────────
# 路径钉扎（首个风险的兜底）
# ─────────────────────────────────────────────────────────────

def pin_attachment_paths(plan: list, attachment: Attachment) -> int:
    """把 Planner 计划里指向本附件的路径，改写成真实落盘路径。返回改写条数。

    按 **basename** 匹配而不是整串比较 —— LLM 可能把分隔符写成反斜杠、或把
    中文目录名敲错一个字，但 UUID 后缀那段它没有动机改，所以按文件名匹配能
    把整条路径救回来。

    同时处理 LLM 把路径误塞进 `xyz` 参数的情况（改写成 input_file）—— 那会让
    eqv2 报「不是合法的 XYZ 文本」，用户看到的是一句莫名其妙的错误。

    只动与本附件 basename 一致的值；指向别的文件（如 .fchk）的路径一律不碰。
    """
    if not plan or not isinstance(plan, list):
        return 0

    target_name = attachment.path.name
    real_path = attachment.path.as_posix()
    fixed = 0

    for step in plan:
        if not isinstance(step, dict):
            continue
        params = step.get("params")
        if not isinstance(params, dict):
            continue

        for key in ("input_file", "xyz"):
            value = params.get(key)
            if not isinstance(value, str) or not value:
                continue
            # XYZ 文本含换行；只有"像路径"的值才做匹配
            if "\n" in value or len(value) > 500:
                continue
            if Path(value.replace("\\", "/")).name != target_name:
                continue

            if key == "input_file":
                params["input_file"] = real_path
                fixed += 1
                logger.bind(component="attachment").info(
                    "[attachment] 已校正 params.input_file | step={} | {} → {}",
                    step.get("step"), value[:80], real_path,
                )
            else:
                # 路径被误当成 XYZ 文本传了：挪到 input_file
                params.pop("xyz", None)
                params["input_file"] = real_path
                fixed += 1
                logger.bind(component="attachment").warning(
                    "[attachment] Planner 把路径塞进了 xyz 参数，已改为 input_file | step={}",
                    step.get("step"),
                )

    return fixed


# ─────────────────────────────────────────────────────────────
# 小工具
# ─────────────────────────────────────────────────────────────

def _display_path(path: Path) -> str:
    """绝对路径 → 相对 backend cwd 的 POSIX 路径；做不到就退回文件名。"""
    try:
        rel = os.path.relpath(path, Path.cwd())
    except ValueError:
        # Windows 跨盘符时 relpath 会抛
        return path.name
    if rel.startswith(".."):
        return path.name
    return Path(rel).as_posix()


def _hill_formula(elements: tuple[str, ...]) -> str:
    """按 Hill 记法拼分子式：有碳则 C、H 在前，其余按字母序；无碳则全按字母序。"""
    if not elements:
        return ""
    counts: dict[str, int] = {}
    for el in elements:
        counts[el] = counts.get(el, 0) + 1

    order: list[str] = []
    if "C" in counts:
        order.append("C")
        if "H" in counts:
            order.append("H")
        order += sorted(k for k in counts if k not in ("C", "H"))
    else:
        order += sorted(counts)

    return "".join(
        f"{el}{counts[el] if counts[el] > 1 else ''}" for el in order
    )
