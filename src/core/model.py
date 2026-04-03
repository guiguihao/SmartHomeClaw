"""
模型适配层 - 支持任何 OpenAI 协议兼容的模型
"""
from __future__ import annotations

import os
from typing import AsyncIterator, Optional
from dataclasses import dataclass, field

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam


@dataclass
class ModelConfig:
    """单个模型的配置信息"""
    name: str                    # 模型名称，如 gpt-4o
    provider: str                # 供应商名，如 openai / deepseek
    base_url: str                # API Base URL
    api_key: str                 # API Key


class ModelClient:
    """
    统一的 LLM 客户端，封装 OpenAI 协议调用。
    支持动态切换模型，兼容 OpenAI / DeepSeek / Claude / Ollama 等任意兼容服务。
    """

    def __init__(self, config: ModelConfig):
        self._config = config
        self._client = self._build_client(config)

    def _build_client(self, config: ModelConfig) -> AsyncOpenAI:
        """根据配置构建 OpenAI 异步客户端"""
        return AsyncOpenAI(
            api_key=config.api_key or "sk-placeholder",  # Ollama 等本地模型不校验
            base_url=config.base_url,
        )

    def switch_model(self, config: ModelConfig):
        """运行时切换模型配置"""
        self._config = config
        self._client = self._build_client(config)

    @property
    def current_model(self) -> str:
        return self._config.name

    @property
    def current_provider(self) -> str:
        return self._config.provider

    async def chat(
        self,
        messages: list[ChatCompletionMessageParam],
        tools: Optional[list[dict]] = None,
        temperature: float = 0.7,
    ) -> dict:
        """
        普通对话调用（非流式），返回完整响应。
        支持 function calling / tool use。
        """
        kwargs = dict(
            model=self._config.name,
            messages=messages,
            temperature=temperature,
        )
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = await self._client.chat.completions.create(**kwargs)
        return response.choices[0].message

    async def stream_chat(
        self,
        messages: list[ChatCompletionMessageParam],
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        """
        流式对话调用，逐 token 输出文本内容。
        注意：流式模式下不支持工具调用。
        """
        async with self._client.chat.completions.stream(
            model=self._config.name,
            messages=messages,
            temperature=temperature,
        ) as stream:
            async for text in stream.text_stream:
                yield text


def load_model_from_config(cfg: dict) -> ModelClient:
    """
    从 agent.yaml 的 model 配置段中，解析并构建 ModelClient。

    cfg 示例:
        default: "deepseek-chat"
        providers:
          - name: deepseek
            base_url: "https://api.deepseek.com/v1"
            api_key_env: "DEEPSEEK_API_KEY"
            models: ["deepseek-chat"]
    """
    default_model = cfg.get("default", "gpt-4o")
    providers = cfg.get("providers", [])

    # 找到包含默认模型的 provider
    matched: Optional[dict] = None
    for provider in providers:
        if default_model in provider.get("models", []):
            matched = provider
            break

    if not matched:
        # 使用第一个 provider 作为后备
        matched = providers[0] if providers else {
            "name": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_key_env": "OPENAI_API_KEY",
        }

    api_key = os.environ.get(matched.get("api_key_env", "OPENAI_API_KEY"), "")

    model_cfg = ModelConfig(
        name=default_model,
        provider=matched["name"],
        base_url=matched["base_url"],
        api_key=api_key,
    )
    return ModelClient(model_cfg)
