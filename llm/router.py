class LLMRouter:
    """根据任务类型路由到不同的 LLM 模型"""

    def __init__(self):
        self.models: dict[str, object] = {}

    def register(self, name: str, client):
        """注册一个模型：router.register('planner', planner_llm)"""
        self.models[name] = client

    def route(self, task_type: str):
        """获取模型；没注册就回退到 default"""
        return self.models.get(task_type, self.models.get("default"))
