"""
Universal multi-provider LLM interface supporting Gemini (including Gemini 4 Hydrogen
with Google Search Grounding), Claude, GPT, DeepSeek, and Ollama.
"""

import os
import json
import time
import logging
import urllib.request
import urllib.error
from typing import Optional, Dict, Any, List, Tuple

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger(__name__)


class UnifiedLLM:
    """Dispatches prompts to Gemini, Anthropic, OpenAI, DeepSeek, or local Ollama."""

    GEMINI_FALLBACK_CHAIN = [
        "gemini-4-hydrogen",
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-3.8-flash",
        "gemini-3-flash-preview",
        "gemini-flash-latest",
    ]

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = 25,
    ):
        self.provider, self.model = self._resolve_provider_and_model(provider, model)
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self._resolve_api_key()

    def _resolve_provider_and_model(self, provider: Optional[str], model: Optional[str]):
        if provider:
            p = provider.lower()
            m = model or self._default_model_for_provider(p)
            return p, m

        m = (model or "").lower()
        if "claude" in m:
            return "anthropic", model
        if any(x in m for x in ["gpt", "o1", "o3", "chatgpt"]):
            return "openai", model
        if "gemini" in m:
            return "gemini", model
        if "deepseek" in m:
            return "deepseek", model

        # Check environment variables
        if os.getenv("GEMINI_API_KEY"):
            return "gemini", model or "gemini-4-hydrogen"
        if os.getenv("OPENAI_API_KEY"):
            return "openai", model or "gpt-4o"
        if os.getenv("ANTHROPIC_API_KEY"):
            return "anthropic", model or "claude-3-5-sonnet-20241022"
        if os.getenv("DEEPSEEK_API_KEY"):
            return "deepseek", model or "deepseek-chat"

        return "gemini", model or "gemini-4-hydrogen"

    def _default_model_for_provider(self, provider: str) -> str:
        defaults = {
            "gemini": "gemini-4-hydrogen",
            "openai": "gpt-4o",
            "anthropic": "claude-3-5-sonnet-20241022",
            "deepseek": "deepseek-chat",
            "ollama": "llama3.2",
        }
        return defaults.get(provider, "gemini-4-hydrogen")

    def _resolve_api_key(self):
        if self.api_key:
            return
        key_map = {
            "gemini": "GEMINI_API_KEY",
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
        }
        env_var = key_map.get(self.provider)
        if env_var:
            self.api_key = os.getenv(env_var)

    def _post_json(self, url: str, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> Tuple[int, str]:
        hdrs = {"Content-Type": "application/json"}
        if headers:
            hdrs.update(headers)
        if requests is not None:
            resp = requests.post(url, json=payload, headers=hdrs, timeout=self.timeout)
            return resp.status_code, resp.text
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=hdrs, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.status, r.read().decode("utf-8", errors="ignore")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", errors="ignore")

    def generate(self, prompt: str, system_instruction: Optional[str] = None, use_google_search: bool = False) -> str:
        """Generate response via configured provider."""
        if self.provider == "gemini":
            text, _ = self._call_gemini(prompt, system_instruction, use_google_search=use_google_search)
            return text
        elif self.provider == "anthropic":
            return self._call_anthropic(prompt, system_instruction)
        elif self.provider in ("openai", "deepseek", "ollama") or self.base_url:
            return self._call_openai_compatible(prompt, system_instruction)
        else:
            text, _ = self._call_gemini(prompt, system_instruction, use_google_search=use_google_search)
            return text

    def generate_with_search(
        self, prompt: str, system_instruction: Optional[str] = None, use_google_search: bool = True
    ) -> Dict[str, Any]:
        """Generate response returning text, model used, and any Google Search grounding metadata."""
        if self.provider != "gemini":
            return {"text": self.generate(prompt, system_instruction), "model": self.model, "grounding": {}}
        text, meta = self._call_gemini(prompt, system_instruction, use_google_search=use_google_search)
        return {"text": text, "model": meta.get("model", self.model), "grounding": meta.get("grounding", {})}

    def _call_gemini(
        self, prompt: str, system_instruction: Optional[str], use_google_search: bool = False
    ) -> Tuple[str, Dict[str, Any]]:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured.")

        models_to_try = list(dict.fromkeys([m for m in [self.model] + self.GEMINI_FALLBACK_CHAIN if m]))

        # Try search-grounded call first if requested; fall back to ungrounded call if search tool is quota-blocked.
        search_modes = [True, False] if use_google_search else [False]
        last_error = None

        for with_search in search_modes:
            search_quota_blocked = False
            for m in models_to_try:
                if search_quota_blocked:
                    break
                for retry in range(2):
                    try:
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={self.api_key}"
                        payload: Dict[str, Any] = {
                            "contents": [{"role": "user", "parts": [{"text": prompt}]}]
                        }
                        if system_instruction:
                            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
                        if with_search:
                            payload["tools"] = [{"google_search": {}}]

                        status, body = self._post_json(url, payload)
                        if status == 200:
                            data = json.loads(body)
                            candidates = data.get("candidates", [])
                            if candidates and "content" in candidates[0]:
                                parts = candidates[0]["content"].get("parts", [])
                                text = "".join(p.get("text", "") for p in parts if "text" in p)
                                if text:
                                    return text, {
                                        "model": m,
                                        "grounding": candidates[0].get("groundingMetadata", {}),
                                        "search_grounded": with_search,
                                    }
                        elif status in (503, 429):
                            last_error = f"{m} (search={with_search}) HTTP {status}: {body[:160]}"
                            if with_search and status == 429:
                                # Search grounding quota exhausted for this key; skip to ungrounded immediately
                                search_quota_blocked = True
                                break
                            if retry == 0 and status == 503:
                                time.sleep(0.4)
                                continue
                            break
                        else:
                            last_error = f"{m} (search={with_search}) HTTP {status}: {body[:160]}"
                            break
                    except Exception as e:
                        last_error = e
                        break

        raise RuntimeError(f"All Gemini models failed. Last error: {last_error}")

    def _call_anthropic(self, prompt: str, system_instruction: Optional[str]) -> str:
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self.api_key or "",
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_instruction:
            payload["system"] = system_instruction

        status, body = self._post_json(url, payload, headers=headers)
        if status >= 400:
            raise RuntimeError(f"Anthropic HTTP {status}: {body[:200]}")
        return json.loads(body)["content"][0]["text"]

    def _call_openai_compatible(self, prompt: str, system_instruction: Optional[str]) -> str:
        base = self.base_url
        if not base:
            if self.provider == "deepseek":
                base = "https://api.deepseek.com/v1"
            elif self.provider == "ollama":
                base = "http://localhost:11434/v1"
            else:
                base = "https://api.openai.com/v1"

        url = f"{base.rstrip('/')}/chat/completions"
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"

        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        payload = {"model": self.model, "messages": messages}
        status, body = self._post_json(url, payload, headers=headers)
        if status >= 400:
            raise RuntimeError(f"{self.provider} HTTP {status}: {body[:200]}")
        return json.loads(body)["choices"][0]["message"]["content"]
