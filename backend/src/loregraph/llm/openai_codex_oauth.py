"""Experimental ChatGPT Codex device-code OAuth support.

The endpoints used here are not part of the public OpenAI API contract.  Keep
this module isolated so the normal API-key OpenAI integration remains stable.
"""

import base64
import json
import time
from pathlib import Path
from typing import Any

import httpx
from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models.chat_models import (
    agenerate_from_stream,
    generate_from_stream,
)
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from langchain_openai import ChatOpenAI

from loregraph.exceptions import ConfigurationError

_ISSUER = "https://auth.openai.com"
_TOKEN_URL = f"{_ISSUER}/oauth/token"
_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
_SKEW_SECONDS = 120


def _instruction_text(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict):
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n\n".join(part.strip() for part in parts if part.strip())


class CodexChatOpenAI(ChatOpenAI):
    """Responses client adapted to the stricter ChatGPT Codex wire contract."""

    def _get_request_payload(
        self,
        input_: object,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)  # type: ignore[arg-type]
        response_input = payload.get("input")
        if not isinstance(response_input, list):
            return payload

        instructions: list[str] = []
        existing = payload.get("instructions")
        if isinstance(existing, str) and existing.strip():
            instructions.append(existing.strip())

        allowed_input: list[object] = []
        for item in response_input:
            if isinstance(item, dict) and item.get("role") in {
                "system",
                "developer",
            }:
                text = _instruction_text(item.get("content"))
                if text:
                    instructions.append(text)
                continue
            allowed_input.append(item)

        payload["input"] = allowed_input
        if instructions:
            payload["instructions"] = "\n\n".join(instructions)
        return payload

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Codex requires every Responses request to use SSE streaming."""
        return generate_from_stream(
            self._stream_responses(
                messages, stop=stop, run_manager=run_manager, **kwargs
            )
        )

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Aggregate the required SSE stream back into LangChain's result."""
        return await agenerate_from_stream(
            self._astream_responses(
                messages, stop=stop, run_manager=run_manager, **kwargs
            )
        )


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return value if isinstance(value, dict) else {}


def _save(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:  # Windows ACLs are inherited from the data directory.
        pass


def _expiry(access_token: str) -> float:
    try:
        payload = access_token.split(".")[1] + "==="
        value = json.loads(base64.urlsafe_b64decode(payload))
        return float(value.get("exp", 0))
    except (IndexError, ValueError, TypeError, json.JSONDecodeError):
        return 0


def account_id(access_token: str) -> str | None:
    """Extract the account header required by the ChatGPT Codex backend."""
    try:
        payload = access_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
        auth = claims.get("https://api.openai.com/auth", {})
        value = auth.get("chatgpt_account_id") if isinstance(auth, dict) else None
        return value if isinstance(value, str) and value else None
    except (IndexError, ValueError, TypeError, json.JSONDecodeError):
        return None


def request_headers(access_token: str) -> dict[str, str]:
    headers = {
        "User-Agent": "codex_cli_rs/0.0.0 (Loregraph experimental)",
        "originator": "codex_cli_rs",
    }
    identifier = account_id(access_token)
    if identifier:
        headers["ChatGPT-Account-ID"] = identifier
    return headers


def available_models(path: Path) -> list[str]:
    """Return the live, account-specific catalog; never invent model ids."""
    token = access_token(path)
    response = httpx.get(
        "https://chatgpt.com/backend-api/codex/models?client_version=1.0.0",
        headers={"Authorization": f"Bearer {token}", **request_headers(token)},
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    entries = data.get("models", []) if isinstance(data, dict) else []
    ranked: list[tuple[int, str]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        slug = item.get("slug")
        visibility = str(item.get("visibility", "")).lower()
        if (
            not isinstance(slug, str)
            or not slug.strip()
            or visibility in {"hide", "hidden"}
        ):
            continue
        priority = item.get("priority")
        rank = int(priority) if isinstance(priority, (int, float)) else 10_000
        ranked.append((rank, slug.strip()))
    return list(dict.fromkeys(slug for _, slug in sorted(ranked)))


def start(path: Path) -> dict[str, str]:
    response = httpx.post(
        f"{_ISSUER}/api/accounts/deviceauth/usercode",
        json={"client_id": _CLIENT_ID}, timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    user_code = str(data.get("user_code", ""))
    device_auth_id = str(data.get("device_auth_id", ""))
    if not user_code or not device_auth_id:
        raise ConfigurationError(
            "OpenAI Codex OAuth returned an incomplete device code"
        )
    _save(path, {"pending": {"user_code": user_code, "device_auth_id": device_auth_id}})
    return {"user_code": user_code, "verification_url": f"{_ISSUER}/codex/device"}


def poll(path: Path) -> bool:
    state = _load(path)
    pending = state.get("pending")
    if not isinstance(pending, dict):
        raise ConfigurationError("Start OpenAI Codex OAuth before checking its status")
    response = httpx.post(
        f"{_ISSUER}/api/accounts/deviceauth/token", json=pending, timeout=15
    )
    if response.status_code in {403, 404}:
        return False
    response.raise_for_status()
    code_data = response.json()
    code = str(code_data.get("authorization_code", ""))
    verifier = str(code_data.get("code_verifier", ""))
    if not code or not verifier:
        raise ConfigurationError(
            "OpenAI Codex OAuth returned an incomplete authorization"
        )
    token_response = httpx.post(
        _TOKEN_URL,
        data={
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": f"{_ISSUER}/deviceauth/callback",
            "client_id": _CLIENT_ID, "code_verifier": verifier,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=15,
    )
    token_response.raise_for_status()
    tokens = token_response.json()
    if not tokens.get("access_token") or not tokens.get("refresh_token"):
        raise ConfigurationError("OpenAI Codex OAuth did not return usable credentials")
    _save(path, {"tokens": tokens})
    return True


def connected(path: Path) -> bool:
    return bool(_load(path).get("tokens", {}).get("access_token"))


def logout(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def access_token(path: Path) -> str:
    state = _load(path)
    tokens = state.get("tokens")
    if not isinstance(tokens, dict):
        raise ConfigurationError("OpenAI Codex OAuth is not connected")
    token = str(tokens.get("access_token", ""))
    refresh = str(tokens.get("refresh_token", ""))
    if token and _expiry(token) > time.time() + _SKEW_SECONDS:
        return token
    if not refresh:
        raise ConfigurationError(
            "OpenAI Codex OAuth credentials expired; connect again"
        )
    response = httpx.post(
        _TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh,
            "client_id": _CLIENT_ID,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=15,
    )
    response.raise_for_status()
    refreshed = response.json()
    if not refreshed.get("access_token"):
        raise ConfigurationError(
            "OpenAI Codex OAuth refresh did not return an access token"
        )
    refreshed.setdefault("refresh_token", refresh)
    _save(path, {"tokens": refreshed})
    return str(refreshed["access_token"])
