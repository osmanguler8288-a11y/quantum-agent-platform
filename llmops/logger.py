import logging

logger = logging.getLogger("llmops")
logger.setLevel(logging.DEBUG)

handler = logging.FileHandler("logs/llmops.log")
handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(handler)


def log_llm_call(model: str, prompt: str, response: str, latency_ms: float):
    logger.info(f"model={model} latency={latency_ms}ms prompt_len={len(prompt)} response_len={len(response)}")
