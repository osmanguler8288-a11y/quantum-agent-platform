class PromptEngine:
    """管理 prompt 模板：注册 → 渲染"""

    def __init__(self):
        self.templates: dict[str, str] = {}

    def register(self, name: str, template: str):
        """注册一个字符串模板"""
        self.templates[name] = template

    def load(self, name: str, filepath: str):
        """从文件读取模板，注册到指定名称"""
        with open(filepath) as f:
            self.templates[name] = f.read()

    def render(self, name: str, **kwargs) -> str:
        """用变量填充模板"""
        template = self.templates.get(name, "")
        if not template:
            raise ValueError(f"模板不存在: {name}")
        return template.format(**kwargs)
