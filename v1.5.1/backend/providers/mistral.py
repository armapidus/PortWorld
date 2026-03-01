from __future__ import annotations

import json
import inspect
from typing import Any, AsyncIterator

import httpx
from fastapi import HTTPException

from backend.config.settings import SETTINGS
from backend.core.debug import DEBUG_MAX_CAPTURED_TOKENS, sanitize_debug_value, sanitize_headers_for_debug, truncate_debug_text
from backend.core.profile import ProviderConfig, RuntimeProfile
from backend.core.utils import auth_headers, extract_choice_text, join_url
from backend.tracing.manager import TraceManager


async def _call_chat_non_stream(
    *,
    provider: ProviderConfig,
    temperature: float,
    max_tokens: int,
    messages: list[dict[str, Any]],
    tracer: TraceManager,
    stage_prefix: str,
    debug_capture: dict[str, Any] | None = None,
) -> str:
    url = join_url(provider.base_url, provider.path)
    headers = {
        **auth_headers(provider.api_key, base_url=provider.base_url),
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": provider.model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }

    if debug_capture is not None:
        debug_capture["request"] = {
            "url": url,
            "headers": sanitize_headers_for_debug(headers),
            "json": sanitize_debug_value(payload),
        }

    await tracer.event(f"{stage_prefix}.request", data={"url": url, "model": provider.model})

    timeout = httpx.Timeout(SETTINGS.request_timeout_s)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        if debug_capture is not None:
            debug_capture["error"] = str(exc)
        await tracer.event(f"{stage_prefix}.error", status="error", data={"message": str(exc)})
        raise HTTPException(status_code=502, detail=f"{stage_prefix} request failed: {exc}") from exc

    if resp.status_code >= 400:
        if debug_capture is not None:
            debug_capture["response"] = {
                "status_code": resp.status_code,
                "text_preview": truncate_debug_text(resp.text, max_chars=700),
            }
        await tracer.event(
            f"{stage_prefix}.upstream_error",
            status="error",
            data={"status_code": resp.status_code, "text": truncate_debug_text(resp.text, max_chars=700)},
        )
        raise HTTPException(
            status_code=502,
            detail=f"{stage_prefix} upstream error {resp.status_code}: {resp.text[:500]}",
        )

    try:
        response_payload = resp.json()
    except json.JSONDecodeError as exc:
        await tracer.event(f"{stage_prefix}.invalid_json", status="error")
        raise HTTPException(status_code=502, detail=f"{stage_prefix} response was not JSON.") from exc

    if debug_capture is not None:
        debug_capture["response"] = {
            "status_code": resp.status_code,
            "json": sanitize_debug_value(response_payload),
        }

    choices = response_payload.get("choices")
    if not isinstance(choices, list) or not choices:
        await tracer.event(f"{stage_prefix}.missing_choices", status="error")
        raise HTTPException(status_code=502, detail=f"{stage_prefix} response missing choices.")
    first = choices[0]
    if not isinstance(first, dict):
        await tracer.event(f"{stage_prefix}.bad_choice_format", status="error")
        raise HTTPException(status_code=502, detail=f"{stage_prefix} choice format invalid.")

    assistant_text = extract_choice_text(first)
    if not assistant_text:
        await tracer.event(f"{stage_prefix}.empty_text", status="error")
        raise HTTPException(status_code=502, detail=f"{stage_prefix} response did not contain text.")

    if debug_capture is not None:
        debug_capture["assistant_text"] = assistant_text

    await tracer.event(f"{stage_prefix}.response", data={"assistant_chars": len(assistant_text)})
    return assistant_text


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, dict):
            text_value = item.get("text")
            if isinstance(text_value, str) and text_value.strip():
                parts.append(text_value.strip())
    return "\n".join(parts).strip()


def _messages_to_prompt(messages: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for message in messages:
        role = str(message.get("role") or "user").strip()
        text = _content_to_text(message.get("content")) or str(message.get("content") or "").strip()
        if not text:
            continue
        lines.append(f"{role}: {text}")
    return "\n\n".join(lines).strip()


def _extract_text_from_driver_result(result: Any) -> str:
    if isinstance(result, str):
        return result.strip()
    if isinstance(result, dict):
        for key in ("assistant_text", "output_text", "text", "response", "token"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        delta = result.get("delta")
        if isinstance(delta, dict):
            delta_content = delta.get("content")
            text = _content_to_text(delta_content)
            if text:
                return text
            if isinstance(delta_content, str) and delta_content.strip():
                return delta_content.strip()
        message = result.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            text = _content_to_text(content)
            if text:
                return text
            if isinstance(content, str) and content.strip():
                return content.strip()
        content = result.get("content")
        text = _content_to_text(content)
        if text:
            return text
        if isinstance(content, str) and content.strip():
            return content.strip()
        choices = result.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            return extract_choice_text(choices[0])
    if isinstance(result, list):
        parts: list[str] = []
        for item in result:
            part = _extract_text_from_driver_result(item)
            if part:
                parts.append(part)
        return "\n".join(parts).strip()
    return ""


async def _stream_text_from_driver_result(result: Any) -> AsyncIterator[str]:
    payload = result
    if inspect.isawaitable(payload):
        payload = await payload

    if isinstance(payload, str):
        text = payload.strip()
        if text:
            yield text
        return

    if isinstance(payload, dict):
        text = _extract_text_from_driver_result(payload)
        if text:
            yield text
        return

    if hasattr(payload, "__aiter__"):
        async for item in payload:
            text = _extract_text_from_driver_result(item)
            if text:
                yield text
        return

    if hasattr(payload, "__iter__"):
        for item in payload:
            text = _extract_text_from_driver_result(item)
            if text:
                yield text
        return

    text = _extract_text_from_driver_result(payload)
    if text:
        yield text


async def _iter_main_llm_tokens_with_strands_driver(
    *,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float,
    max_tokens: int,
) -> AsyncIterator[str]:
    try:
        import strands  # type: ignore
    except Exception as exc:
        raise RuntimeError("strands package is not available. Install optional dependency `strands-agents`.") from exc

    system_prompt = ""
    for message in messages:
        if str(message.get("role") or "").strip() == "system":
            system_prompt = _content_to_text(message.get("content")) or str(message.get("content") or "").strip()
            if system_prompt:
                break

    normalized_messages: list[dict[str, str]] = []
    for message in messages:
        role = str(message.get("role") or "user").strip() or "user"
        text = _content_to_text(message.get("content")) or str(message.get("content") or "").strip()
        if text:
            normalized_messages.append({"role": role, "content": text})

    prompt_text = _messages_to_prompt(messages)
    errors: list[str] = []
    produced_any = False

    async def _try_stream(method: Any, payload: Any, *, kwargs_mode: bool = False) -> AsyncIterator[str]:
        nonlocal produced_any
        try:
            if kwargs_mode and isinstance(payload, dict):
                result = method(**payload)
            else:
                result = method(payload)
        except TypeError:
            result = method()
        except Exception as exc:
            errors.append(str(exc))
            return

        try:
            async for text in _stream_text_from_driver_result(result):
                if text:
                    produced_any = True
                    yield text
        except Exception as exc:
            errors.append(str(exc))

    agent_cls = getattr(strands, "Agent", None)
    if callable(agent_cls):
        constructor_variants: list[dict[str, Any]] = [
            {
                "model": model,
                "system_prompt": system_prompt,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            {"model": model, "temperature": temperature, "max_tokens": max_tokens},
            {"model": model},
            {},
        ]
        for kwargs in constructor_variants:
            try:
                agent = agent_cls(**kwargs)
            except Exception as exc:
                errors.append(str(exc))
                continue

            for method_name in ("stream", "astream", "stream_tokens", "token_stream", "stream_response"):
                method = getattr(agent, method_name, None)
                if not callable(method):
                    continue
                for payload in (
                    {"messages": normalized_messages},
                    normalized_messages,
                    {"prompt": prompt_text},
                    prompt_text,
                ):
                    async for token in _try_stream(method, payload):
                        yield token
                    if produced_any:
                        return

            for method_name in ("invoke", "run", "chat", "complete", "respond", "__call__"):
                method = getattr(agent, method_name, None)
                if method_name == "__call__" and not callable(agent):
                    continue
                if method_name != "__call__" and not callable(method):
                    continue
                target = agent if method_name == "__call__" else method
                if target is None:
                    continue
                for payload in (
                    {"messages": normalized_messages},
                    normalized_messages,
                    {"prompt": prompt_text},
                    prompt_text,
                ):
                    async for token in _try_stream(target, payload):
                        yield token
                    if produced_any:
                        return

    for fn_name in ("stream", "astream", "stream_tokens", "token_stream", "stream_response", "invoke", "run", "chat", "complete"):
        fn = getattr(strands, fn_name, None)
        if not callable(fn):
            continue
        for payload in (
            {"model": model, "messages": normalized_messages, "temperature": temperature, "max_tokens": max_tokens},
            {"messages": normalized_messages},
            {"prompt": prompt_text},
            prompt_text,
        ):
            kwargs_mode = isinstance(payload, dict)
            async for token in _try_stream(fn, payload, kwargs_mode=kwargs_mode):
                yield token
            if produced_any:
                return

    preview = "; ".join(errors[:5]) if errors else "No compatible streaming callable found on strands module."
    raise RuntimeError(f"Unable to stream main LLM via strands driver. {preview}")


async def _call_main_llm_with_strands_driver(
    *,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float,
    max_tokens: int,
) -> str:
    try:
        import strands  # type: ignore
    except Exception as exc:
        raise RuntimeError("strands package is not available. Install optional dependency `strands-agents`.") from exc

    system_prompt = ""
    for message in messages:
        if str(message.get("role") or "").strip() == "system":
            system_prompt = _content_to_text(message.get("content")) or str(message.get("content") or "").strip()
            if system_prompt:
                break

    normalized_messages: list[dict[str, str]] = []
    for message in messages:
        role = str(message.get("role") or "user").strip() or "user"
        text = _content_to_text(message.get("content")) or str(message.get("content") or "").strip()
        if text:
            normalized_messages.append({"role": role, "content": text})

    prompt_text = _messages_to_prompt(messages)
    errors: list[str] = []

    async def _invoke_candidate(method: Any, payload: Any) -> str:
        try:
            result = method(payload)
        except TypeError:
            result = method()
        if inspect.isawaitable(result):
            result = await result
        return _extract_text_from_driver_result(result)

    agent_cls = getattr(strands, "Agent", None)
    if callable(agent_cls):
        constructor_variants: list[dict[str, Any]] = [
            {
                "model": model,
                "system_prompt": system_prompt,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            {"model": model, "temperature": temperature, "max_tokens": max_tokens},
            {"model": model},
            {},
        ]
        for kwargs in constructor_variants:
            try:
                agent = agent_cls(**kwargs)
            except Exception as exc:
                errors.append(f"Agent constructor failed with kwargs={list(kwargs.keys())}: {exc}")
                continue

            for method_name in ("invoke", "run", "chat", "complete", "respond", "__call__"):
                method = getattr(agent, method_name, None)
                if method_name == "__call__" and not callable(agent):
                    continue
                if method_name != "__call__" and not callable(method):
                    continue
                target = agent if method_name == "__call__" else method
                if target is None:
                    continue
                for payload in (
                    {"messages": normalized_messages},
                    normalized_messages,
                    {"prompt": prompt_text},
                    prompt_text,
                ):
                    try:
                        text = await _invoke_candidate(target, payload)
                    except Exception as exc:
                        errors.append(f"{method_name} failed: {exc}")
                        continue
                    if text:
                        return text

    for fn_name in ("invoke", "run", "chat", "complete"):
        fn = getattr(strands, fn_name, None)
        if not callable(fn):
            continue
        for payload in (
            {"model": model, "messages": normalized_messages, "temperature": temperature, "max_tokens": max_tokens},
            {"messages": normalized_messages},
            {"prompt": prompt_text},
            prompt_text,
        ):
            try:
                if isinstance(payload, dict):
                    result = fn(**payload)
                else:
                    result = fn(payload)
                if inspect.isawaitable(result):
                    result = await result
            except Exception as exc:
                errors.append(f"{fn_name} failed: {exc}")
                continue

            text = _extract_text_from_driver_result(result)
            if text:
                return text

    preview = "; ".join(errors[:5]) if errors else "No compatible callable found on strands module."
    raise RuntimeError(f"Unable to execute main LLM via strands driver. {preview}")


async def call_main_llm_non_stream(
    *,
    profile: RuntimeProfile,
    model: str,
    messages: list[dict[str, Any]],
    tracer: TraceManager,
    debug_capture: dict[str, Any] | None = None,
) -> str:
    requested_driver = str(profile.options.get("main_llm_driver") or profile.metadata.get("main_llm_driver") or "openai_compat").strip().lower()
    if requested_driver == "strands":
        if debug_capture is not None:
            debug_capture["driver"] = "strands"
        await tracer.event("main_llm.driver", data={"driver": "strands", "model": model})
        try:
            assistant_text = await _call_main_llm_with_strands_driver(
                model=model,
                messages=messages,
                temperature=profile.temperatures["main_llm"],
                max_tokens=profile.max_tokens["main_llm"],
            )
            if debug_capture is not None:
                debug_capture["assistant_text"] = assistant_text
            await tracer.event("main_llm.response", data={"driver": "strands", "assistant_chars": len(assistant_text)})
            return assistant_text
        except Exception as exc:
            if debug_capture is not None:
                debug_capture["driver_error"] = str(exc)
            await tracer.event("main_llm.strands_error", status="error", data={"message": str(exc)})
            await tracer.event("main_llm.strands_fallback", data={"fallback_driver": "openai_compat"})

    provider = ProviderConfig(
        base_url=profile.main_llm.base_url,
        api_key=profile.main_llm.api_key,
        path=profile.main_llm.path,
        model=model,
    )
    return await _call_chat_non_stream(
        provider=provider,
        temperature=profile.temperatures["main_llm"],
        max_tokens=profile.max_tokens["main_llm"],
        messages=messages,
        tracer=tracer,
        stage_prefix="main_llm",
        debug_capture=debug_capture,
    )


async def iter_main_llm_tokens(
    *,
    profile: RuntimeProfile,
    model: str,
    messages: list[dict[str, Any]],
    tracer: TraceManager,
    debug_capture: dict[str, Any] | None = None,
) -> AsyncIterator[str]:
    requested_driver = str(profile.options.get("main_llm_driver") or profile.metadata.get("main_llm_driver") or "openai_compat").strip().lower()
    if requested_driver == "strands":
        if debug_capture is not None:
            debug_capture["driver"] = "strands"
            debug_capture["token_count"] = 0
            debug_capture["tokens"] = []
        await tracer.event("main_llm_stream.driver", data={"driver": "strands", "model": model})

        produced = 0
        try:
            async for token in _iter_main_llm_tokens_with_strands_driver(
                model=model,
                messages=messages,
                temperature=profile.temperatures["main_llm"],
                max_tokens=profile.max_tokens["main_llm"],
            ):
                if not token:
                    continue
                produced += 1
                if debug_capture is not None:
                    debug_capture["token_count"] = int(debug_capture.get("token_count", 0)) + 1
                    tokens = debug_capture.setdefault("tokens", [])
                    if isinstance(tokens, list) and len(tokens) < DEBUG_MAX_CAPTURED_TOKENS:
                        tokens.append(token)
                yield token
            if produced > 0:
                return
        except Exception as exc:
            if debug_capture is not None:
                debug_capture["driver_error"] = str(exc)
            await tracer.event("main_llm_stream.strands_error", status="error", data={"message": str(exc)})

        await tracer.event("main_llm_stream.strands_fallback", data={"fallback_driver": "openai_compat"})
        text = await call_main_llm_non_stream(
            profile=profile,
            model=model,
            messages=messages,
            tracer=tracer,
            debug_capture=debug_capture,
        )
        if text:
            if debug_capture is not None:
                debug_capture["token_count"] = max(int(debug_capture.get("token_count", 0)), 1)
                tokens = debug_capture.setdefault("tokens", [])
                if isinstance(tokens, list) and len(tokens) < DEBUG_MAX_CAPTURED_TOKENS:
                    tokens.append(text)
            yield text
        return

    provider = profile.main_llm
    url = join_url(provider.base_url, provider.path)
    headers = {
        **auth_headers(provider.api_key, base_url=provider.base_url),
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": profile.temperatures["main_llm"],
        "max_tokens": profile.max_tokens["main_llm"],
        "stream": True,
    }

    if debug_capture is not None:
        debug_capture["request"] = {
            "url": url,
            "headers": sanitize_headers_for_debug(headers),
            "json": sanitize_debug_value(payload),
        }
        debug_capture["token_count"] = 0
        debug_capture["tokens"] = []

    await tracer.event("main_llm_stream.request", data={"url": url, "model": model})

    timeout = httpx.Timeout(connect=30.0, read=None, write=30.0, pool=30.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                if resp.status_code >= 400:
                    body = (await resp.aread())[:600].decode("utf-8", errors="replace")
                    if debug_capture is not None:
                        debug_capture["response"] = {
                            "status_code": resp.status_code,
                            "text_preview": truncate_debug_text(body, max_chars=700),
                        }
                    await tracer.event(
                        "main_llm_stream.upstream_error",
                        status="error",
                        data={"status_code": resp.status_code, "text": truncate_debug_text(body, max_chars=700)},
                    )
                    raise HTTPException(
                        status_code=502,
                        detail=f"Main LLM streaming upstream error {resp.status_code}: {body}",
                    )

                if debug_capture is not None:
                    debug_capture["response"] = {"status_code": resp.status_code}

                async for raw_line in resp.aiter_lines():
                    line = raw_line.strip()
                    if not line:
                        continue
                    if line.startswith("event:"):
                        continue
                    if not line.startswith("data:"):
                        continue

                    payload_line = line[5:].strip()
                    if not payload_line:
                        continue
                    if payload_line == "[DONE]":
                        break

                    try:
                        chunk = json.loads(payload_line)
                    except json.JSONDecodeError:
                        continue

                    choices = chunk.get("choices")
                    if not isinstance(choices, list) or not choices:
                        continue
                    first = choices[0]
                    if not isinstance(first, dict):
                        continue

                    token = extract_choice_text(first)
                    if token:
                        if debug_capture is not None:
                            debug_capture["token_count"] = int(debug_capture.get("token_count", 0)) + 1
                            tokens = debug_capture.setdefault("tokens", [])
                            if isinstance(tokens, list) and len(tokens) < DEBUG_MAX_CAPTURED_TOKENS:
                                tokens.append(token)
                        yield token
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        if debug_capture is not None:
            debug_capture["error"] = str(exc)
        await tracer.event("main_llm_stream.error", status="error", data={"message": str(exc)})
        raise HTTPException(status_code=502, detail=f"Main LLM stream request failed: {exc}") from exc


async def call_vision_llm_non_stream(
    *,
    profile: RuntimeProfile,
    messages: list[dict[str, Any]],
    tracer: TraceManager,
    debug_capture: dict[str, Any] | None = None,
) -> str:
    return await _call_chat_non_stream(
        provider=profile.vision,
        temperature=profile.temperatures["vision"],
        max_tokens=profile.max_tokens["vision"],
        messages=messages,
        tracer=tracer,
        stage_prefix="vision_llm",
        debug_capture=debug_capture,
    )
