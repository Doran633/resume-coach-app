import json
import re
from typing import Any


class JSONRepairError(ValueError):
    pass


def _strip_code_fence(text: str) -> str:
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()
    return text.strip()


def _extract_json_object(text: str) -> str:
    cleaned = _strip_code_fence(text)
    if cleaned.startswith("{") and cleaned.endswith("}"):
        return cleaned

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise JSONRepairError("LLM response does not contain a JSON object.")
    return cleaned[start : end + 1]


def parse_llm_json(text: str) -> dict[str, Any]:
    json_text = _extract_json_object(text)
    try:
        return json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise JSONRepairError(f"Invalid JSON from LLM: {exc}") from exc
