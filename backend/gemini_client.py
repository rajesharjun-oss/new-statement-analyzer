"""
Small compatibility wrapper for Gemini calls.

The backend prefers the supported google-genai SDK, while retaining a lazy
fallback for local environments that have not installed the new package yet.
"""
from __future__ import annotations

import io
from typing import Any, Iterable, List


def _pil_to_png_bytes(image: Any) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _normalize_new_sdk_contents(contents: Any) -> Any:
    from google.genai import types

    if isinstance(contents, (str, bytes, bytearray)):
        items: Iterable[Any] = [contents]
    else:
        items = contents

    normalized: List[Any] = []
    for item in items:
        if isinstance(item, str):
            normalized.append(item)
        elif isinstance(item, (bytes, bytearray)):
            normalized.append(types.Part.from_bytes(data=bytes(item), mime_type="image/png"))
        elif hasattr(item, "save"):
            normalized.append(types.Part.from_bytes(data=_pil_to_png_bytes(item), mime_type="image/png"))
        else:
            normalized.append(item)
    return normalized


def generate_gemini_text(
    api_key: str,
    model: str,
    contents: Any,
    *,
    max_output_tokens: int | None = None,
) -> str:
    """
    Generate text with Gemini using google-genai when available.

    The deprecated google-generativeai package is imported only as a local
    fallback so tests and developer machines do not break before dependencies
    are refreshed.
    """
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        import google.generativeai as legacy_genai

        legacy_genai.configure(api_key=api_key)
        generation_config = None
        if max_output_tokens:
            generation_config = legacy_genai.types.GenerationConfig(max_output_tokens=max_output_tokens)
        response = legacy_genai.GenerativeModel(model).generate_content(
            contents,
            generation_config=generation_config,
        )
        return (getattr(response, "text", None) or "").strip()

    client = genai.Client(api_key=api_key)
    config = None
    if max_output_tokens:
        config = types.GenerateContentConfig(max_output_tokens=max_output_tokens)

    response = client.models.generate_content(
        model=model,
        contents=_normalize_new_sdk_contents(contents),
        config=config,
    )
    return (getattr(response, "text", None) or "").strip()
