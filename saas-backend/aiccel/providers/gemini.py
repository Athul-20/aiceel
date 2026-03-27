# aiccel/providers/gemini.py
"""
Gemini Provider Implementation
==============================
"""

import asyncio
import time
from typing import Optional, Union

import orjson
import requests
from aiohttp import ClientResponseError, ClientSession, ClientTimeout

from ..exceptions import ProviderException
from .base import LLMProvider


class GeminiProvider(LLMProvider):
    """
    Google Gemini LLM Provider.

    Supports Gemini 2.0, Gemini 1.5 Pro/Flash and other Google AI models.
    """

    ENV_KEY_PREFIX = "GOOGLE"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-2.5-flash",
        embedding_provider: Optional[LLMProvider] = None,
        verbose: bool = False,
        log_file: Optional[str] = None,
        structured_logging: bool = False
    ):
        super().__init__(
            api_key=api_key,
            model=model,
            verbose=verbose,
            log_file=log_file,
            structured_logging=structured_logging
        )
        self.embedding_provider = embedding_provider
        self.http_session = None

    async def __aenter__(self):
        self.http_session = ClientSession(timeout=ClientTimeout(total=30))
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.http_session:
            await self.http_session.close()

    def _generate_impl(self, prompt: str, **kwargs) -> str:
        return self.chat([{"role": "user", "content": prompt}], **kwargs)

    async def _generate_async_impl(self, prompt: str, **kwargs) -> str:
        return await self.chat_async([{"role": "user", "content": prompt}], **kwargs)

    def _chat_impl(self, messages: list[dict[str, str]], **kwargs) -> str:
        trace_id = self.logger.trace_start("gemini_chat", {"message_count": len(messages)})
        url = f"https://generativelanguage.googleapis.com/v1/models/{self.model}:generateContent?key={self.api_key}"

        contents = []
        for msg in messages:
            role = "user" if msg["role"].lower() == "user" else "model"
            contents.append({
                "role": role,
                "parts": [{"text": msg["content"]}]
            })

        data = {
            "contents": contents,
            "generationConfig": {
                "temperature": kwargs.get("temperature", self.temperature),
                "maxOutputTokens": kwargs.get("max_tokens", 2048),
            }
        }

        max_retries = 3
        backoff_factor = 2

        for attempt in range(max_retries + 1):
            try:
                session = self._get_sync_session()
                response = session.post(url, json=data, timeout=self.timeout)

                if response.status_code == 429:
                    if attempt < max_retries:
                        sleep_time = backoff_factor ** attempt
                        self.logger.warning(f"Gemini API rate limit exceeded (429). Retrying in {sleep_time}s...")
                        time.sleep(sleep_time)
                        continue
                    else:
                        response.raise_for_status()

                response.raise_for_status()
                response_json = orjson.loads(response.content)

                if not response_json.get("candidates") or not response_json["candidates"][0].get("content"):
                    raise ProviderException(
                        "Invalid response format",
                        context={"provider": "Gemini", "model": self.model}
                    )

                result = response_json["candidates"][0]["content"]["parts"][0]["text"]
                self.logger.trace_end(trace_id, {"response": result[:100]})
                return result
            except Exception as e:
                # If it was a 429 that we didn't catch above
                if isinstance(e, requests.exceptions.HTTPError) and e.response.status_code == 429:
                     if attempt < max_retries:
                        sleep_time = backoff_factor ** attempt
                        self.logger.warning(f"Gemini API rate limit exceeded (429). Retrying in {sleep_time}s...")
                        time.sleep(sleep_time)
                        continue

                self.logger.trace_error(trace_id, e, "Gemini chat failed")
                raise

    async def _chat_async_impl(self, messages: list[dict[str, str]], **kwargs) -> str:
        trace_id = self.logger.trace_start("gemini_chat_async", {"message_count": len(messages)})
        url = f"https://generativelanguage.googleapis.com/v1/models/{self.model}:generateContent?key={self.api_key}"

        contents = []
        for msg in messages:
            role = "user" if msg["role"].lower() == "user" else "model"
            contents.append({
                "role": role,
                "parts": [{"text": msg["content"]}]
            })

        data = {
            "contents": contents,
            "generationConfig": {
                "temperature": kwargs.get("temperature", self.temperature),
                "maxOutputTokens": kwargs.get("max_tokens", 2048),
            }
        }

        session = self.http_session or ClientSession(timeout=ClientTimeout(total=self.timeout))
        close_session = self.http_session is None

        max_retries = 3
        backoff_factor = 2

        try:
            for attempt in range(max_retries + 1):
                try:
                    async with session.post(url, json=data) as response:
                        if response.status == 429:
                            if attempt < max_retries:
                                sleep_time = backoff_factor ** attempt
                                self.logger.warning(f"Gemini API rate limit exceeded (429). Retrying in {sleep_time}s...")
                                await asyncio.sleep(sleep_time)
                                continue
                            else:
                                response.raise_for_status()

                        response.raise_for_status()
                        response_json = await response.json()

                        if not response_json.get("candidates") or not response_json["candidates"][0].get("content"):
                            raise ProviderException(
                                "Invalid response format",
                                context={"provider": "Gemini", "model": self.model}
                            )

                        result = response_json["candidates"][0]["content"]["parts"][0]["text"]
                        self.logger.trace_end(trace_id, {"response": result[:100]})
                        return result
                except Exception as e:
                    if isinstance(e, ClientResponseError) and e.status == 429:
                        if attempt < max_retries:
                            sleep_time = backoff_factor ** attempt
                            self.logger.warning(f"Gemini API rate limit exceeded (429). Retrying in {sleep_time}s...")
                            await asyncio.sleep(sleep_time)
                            continue

                    if attempt == max_retries:
                         self.logger.trace_error(trace_id, e, "Gemini async chat failed")
                         raise

                    self.logger.trace_error(trace_id, e, "Gemini async chat failed")
                    raise
        finally:
            if close_session:
                await session.close()

    def _embed_impl(self, text: Union[str, list[str]]) -> list[float]:
        if not self.embedding_provider:
            raise ValueError("No embedding provider specified")
        return self.embedding_provider.embed(text)

    async def _embed_async_impl(self, text: Union[str, list[str]]) -> list[float]:
        if not self.embedding_provider:
            raise ValueError("No embedding provider specified")
        return await self.embedding_provider.embed_async(text)
