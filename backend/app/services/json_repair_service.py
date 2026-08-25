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
    if start == -1:
        raise JSONRepairError("LLM response does not contain a JSON object.")
    if end == -1 or end <= start:
        return cleaned[start:].strip()
    return cleaned[start : end + 1]


def _close_truncated_json(json_text: str) -> str:
    stack: list[str] = []
    in_string = False
    escaped = False
    for char in json_text:
        if escaped:
            escaped = False
            continue
        if char == "\\" and in_string:
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char in "{[":
            stack.append(char)
        elif char in "}]":
            if stack:
                stack.pop()
    if in_string:
        json_text += '"'
    closing = {"{": "}", "[": "]"}
    while stack:
        json_text += closing[stack.pop()]
    return json_text


def parse_llm_json(text: str) -> dict[str, Any]:
    json_text = _extract_json_object(text)
    try:
        return json.loads(json_text)
    except json.JSONDecodeError as exc:
        repaired = _close_truncated_json(json_text)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            raise JSONRepairError(f"Invalid JSON from LLM: {exc}") from exc
