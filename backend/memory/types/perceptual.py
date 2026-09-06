"""PerceptualMemory — 感知记忆（多模态预留）

存放文件路径、图片、音频等感知输入。
当前阶段只记 file_path + modality，未来可接入多模态 Embedding。
"""

from memory.types.base import BaseMemory


class PerceptualMemory(BaseMemory):
    def __init__(self, config, store, user_id="default_user"):
        super().__init__(config, store, user_id)
        self.memory_type = "perceptual"

    def add(self, content: str, importance: float = 0.5,
            session_id=None, file_path: str = None, modality: str = None, **metadata):
        """感知记忆专属：自动推断模态"""
        if file_path and not modality:
            modality = self._infer_modality(file_path)
        metadata.update({"file_path": file_path, "modality": modality})
        return super().add(content, importance, session_id, **metadata)

    @staticmethod
    def _infer_modality(file_path: str) -> str:
        ext = file_path.lower().rsplit(".", 1)[-1] if "." in file_path else ""
        mapping = {
            "png": "image", "jpg": "image", "jpeg": "image",
            "wav": "audio", "mp3": "audio",
            "txt": "text", "md": "text", "pdf": "text",
        }
        return mapping.get(ext, "unknown")
