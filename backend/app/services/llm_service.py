import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass
class LLMResult:
    text: str
    model: str
    latency_ms: int


class LLMServiceError(RuntimeError):
    pass


def _load_dotenv():
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_llm_mode() -> str:
    _load_dotenv()
    return os.getenv("LLM_MODE", "mock").strip().lower()


def get_openai_model() -> str:
    _load_dotenv()
    return os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()


def call_openai(prompt: str) -> LLMResult:
    _load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
    model = get_openai_model()
    timeout = int(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
    max_tokens = int(os.getenv("LLM_MAX_TOKENS", "8192"))
    thinking_mode = os.getenv("LLM_THINKING", "disabled").strip().lower()

    if not api_key:
        raise LLMServiceError("OPENAI_API_KEY is empty. Set LLM_MODE=mock or configure an API key.")

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "你是一个面向国内技术求职者的 AI 求职教练，必须输出严格 JSON，不要输出解释文字。",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    if "deepseek" in base_url or os.getenv("LLM_THINKING"):
        payload["thinking"] = {"type": "enabled" if thinking_mode == "enabled" else "disabled"}

    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    started_at = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise LLMServiceError(f"OpenAI API HTTP {exc.code}: {detail[:500]}") from exc
    except TimeoutError as exc:
        raise LLMServiceError(f"OpenAI-compatible API request timed out after {timeout}s.") from exc
    except Exception as exc:
        raise LLMServiceError(f"OpenAI API request failed: {exc}") from exc

    latency_ms = int((time.perf_counter() - started_at) * 1000)
    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMServiceError("OpenAI API returned an unexpected response shape.") from exc

    return LLMResult(text=text, model=model, latency_ms=latency_ms)
