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

    default 支持两种格式：
      1. "{provider}/{model}"  —— 明确指定供应商（斜杠前是 provider name，其余是传给 API 的模型名）
         示例：nvidia/openai/gpt-oss-120b  →  provider=nvidia, model=openai/gpt-oss-120b
      2. "{model}"             —— 纯模型名，在所有 provider 的 models 列表中自动搜索
         示例：deepseek-chat

    cfg 示例:
        default: "nvidia/openai/gpt-oss-120b"
        providers:
          - name: nvidia
            base_url: "https://integrate.api.nvidia.com/v1"
            api_key_env: "NVIDIA_API_KEY"
            models: ["openai/gpt-oss-120b"]
    """
    default_val = cfg.get("default", "gpt-4o")
    providers = cfg.get("providers", [])

    # 支持 provider/model 格式或纯模型名
    if "/" in default_val:
        target_provider, target_model = default_val.split("/", 1)
    else:
        target_provider, target_model = None, default_val

    # 找到匹配的 provider
    matched: Optional[dict] = None
    for provider in providers:
        if target_provider:
            if provider.get("name") == target_provider:
                matched = provider
                break
        elif target_model in provider.get("models", []):
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
        name=target_model,
        provider=matched["name"],
        base_url=matched["base_url"],
        api_key=api_key,
    )
    return ModelClient(model_cfg)
