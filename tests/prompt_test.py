"""测试 PromptEngine + LLMClient 串联"""
from llm.prompt_engine import PromptEngine
from llm.client import LLMClient

# 1. 加载模板，渲染 prompt
engine = PromptEngine()
engine.load("planner", "agent/prompts/planner.txt")
prompt = engine.render("planner", role="量子化学", task="计算苯的HOMO-LUMO能隙", tools="gaussian, multiwfn")

print("=== 填充后的 prompt ===")
print(prompt)
print()

# 2. 发给 DeepSeek
client = LLMClient()
reply = client.generate(prompt)

print("=== LLM 回复 ===")
print(reply)
