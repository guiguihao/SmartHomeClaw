"""
Model Adaptation Layer - Supports any OpenAI protocol compatible models / 
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
    """Configuration for a single model / 单个模型的配置信息"""
    name: str                    # Model name, e.g., gpt-4o / 模型名称，如 gpt-4o
    provider: str                # Provider name, e.g., openai / deepseek / 供应商名，如 openai / deepseek
    base_url: str                # API Base URL
    api_key: str                 # API Key


class ModelClient:
    """
    Unified LLM Client, wrapping OpenAI protocol calls. / 统一的 LLM 客户端，封装 OpenAI 协议调用。
    Supports dynamic switching, compatible with OpenAI / DeepSeek / Claude / Ollama, etc. / 
    支持动态切换模型，兼容 OpenAI / DeepSeek / Claude / Ollama 等任意兼容服务。
    """

    def __init__(self, config: ModelConfig):
        self._config = config
        self._client = self._build_client(config)

    def _build_client(self, config: ModelConfig) -> AsyncOpenAI:
        """Build OpenAI async client from config / 根据配置构建 OpenAI 异步客户端"""
        return AsyncOpenAI(
            api_key=config.api_key or "sk-placeholder",  # Placeholder for local models like Ollama / Ollama 等本地模型不校验
            base_url=config.base_url,
        )

    def switch_model(self, config: ModelConfig):
        """Switch model configuration at runtime / 运行时切换模型配置"""
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
        Normal chat call (non-streaming), returns full response. / 普通对话调用（非流式），返回完整响应。
        Supports function calling / tool use. / 支持 function calling / tool use。
        """
        kwargs = dict(
            model=self._config.name,
            messages=messages,
            temperature=temperature,
        )
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        # [DEBUG] Print full context / 打印发送给模型的完整上下文
        import json
        import logging
        _logger = logging.getLogger(__name__)

        def _sanitize(obj):
            """Helper to make OpenAI objects serializable / 辅助函数：使对象可序列化"""
            if isinstance(obj, list):
                return [_sanitize(i) for i in obj]
            if isinstance(obj, dict):
                return {k: _sanitize(v) for k, v in obj.items()}
            if hasattr(obj, "model_dump"): # Pydantic v2 (OpenAI SDK > 1.0)
                return _sanitize(obj.model_dump())
            if hasattr(obj, "to_dict"): # Legacy or other formats
                return _sanitize(obj.to_dict())
            return str(obj)

        _logger.debug("="*40 + " [LLM REQUEST START] " + "="*40)
        _logger.debug(f"Model: {self._config.name} / Provider: {self._config.provider}")
        _logger.debug(f"Messages:\n{json.dumps(_sanitize(messages), indent=2, ensure_ascii=False)}")
        if tools:
            _logger.debug(f"Tools Count: {len(tools)}")
        _logger.debug("="*40 + " [LLM REQUEST END]   " + "="*40)

        response = await self._client.chat.completions.create(**kwargs)
        return response.choices[0].message

    async def stream_chat(
        self,
        messages: list[ChatCompletionMessageParam],
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        """
        Streaming chat call, yields text tokens sequentially. / 流式对话调用，逐 token 输出文本内容。
        Note: Tool calling is not supported in streaming mode. / 注意：流式模式下不支持工具调用。
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
    Parse and build ModelClient from the model section of agent.yaml. / 
    从 agent.yaml 的 model 配置段中，解析并构建 ModelClient。

    'default' supports two formats: / default 支持两种格式：
      1. "{provider}/{model}"  —— Explicitly specify provider (slash prefix is provider name). / 明确指定供应商
         Example: nvidia/openai/gpt-oss-120b  →  provider=nvidia, model=openai/gpt-oss-120b
      2. "{model}"             —— Pure model name, auto-search across all providers. / 纯模型名，自动在所有 provider 中搜索
         Example: deepseek-chat

    cfg Example:
        default: "nvidia/openai/gpt-oss-120b"
        providers:
          - name: nvidia
            base_url: "https://integrate.api.nvidia.com/v1"
            api_key_env: "NVIDIA_API_KEY"
            models: ["openai/gpt-oss-120b"]
    """
    default_val = cfg.get("default", "gpt-4o")
    providers = cfg.get("providers", [])

    # Support provider/model format or pure model name / 支持 provider/model 格式或纯模型名
    if "/" in default_val:
        target_provider, target_model = default_val.split("/", 1)
    else:
        target_provider, target_model = None, default_val

    # Find matching provider / 找到匹配的 provider
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
        # Fallback to the first provider / 使用第一个 provider 作为后备
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
