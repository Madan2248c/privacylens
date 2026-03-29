"""PrivacyLens — transparent PII masking for LLM clients."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from privacylens.core.models import Config, EntitySpan


def shield(client: object, **kwargs: object) -> object:
    """Wrap an LLM client with PII masking.

    Auto-detects the client type and returns the appropriate adapter.
    Supported clients: openai.OpenAI, openai.AsyncOpenAI,
    anthropic.Anthropic, anthropic.AsyncAnthropic,
    langchain_core.language_models.BaseChatModel.

    Args:
        client: An LLM client instance.
        **kwargs: Optional configuration keyword arguments passed to load_config().

    Returns:
        A privacy-protected wrapper around the client.

    Raises:
        TypeError: If the client type is not supported.
    """
    from privacylens.adapters.anthropic import AnthropicAdapter
    from privacylens.adapters.langchain import LangChainCallbackHandler
    from privacylens.adapters.openai import OpenAIAdapter
    from privacylens.core.config import load_config
    from privacylens.core.pipeline import Pipeline

    config = load_config(**kwargs)
    pipeline = Pipeline(config)

    try:
        import openai

        if isinstance(client, (openai.OpenAI, openai.AsyncOpenAI)):
            return OpenAIAdapter(client, pipeline)
    except ImportError:
        pass

    try:
        import anthropic

        if isinstance(client, (anthropic.Anthropic, anthropic.AsyncAnthropic)):
            return AnthropicAdapter(client, pipeline)
    except ImportError:
        pass

    try:
        from langchain_core.language_models import BaseChatModel

        if isinstance(client, BaseChatModel):
            return LangChainCallbackHandler(pipeline)
    except ImportError:
        pass

    try:
        from strands.models import Model as StrandsModel

        from privacylens.adapters.strands import StrandsModelWrapper

        if isinstance(client, StrandsModel):
            return StrandsModelWrapper(client, pipeline)
    except ImportError:
        pass

    raise TypeError(
        f"Unsupported client type: {type(client).__name__}. "
        "Supported: openai.OpenAI, openai.AsyncOpenAI, anthropic.Anthropic, "
        "anthropic.AsyncAnthropic, langchain_core.language_models.BaseChatModel"
    )


def inspect(text: str, config: Config | None = None) -> list[EntitySpan]:
    """Return what would be masked without performing masking.

    Runs the Analyzer pipeline only — no vault writes, no tokenization.

    Args:
        text: The input text to inspect.
        config: Optional Config object. Uses defaults if None.

    Returns:
        A list of EntitySpan objects representing detected entities.
    """
    from privacylens.core.analyzer import Analyzer
    from privacylens.core.config import load_config
    from privacylens.core.pipeline import _build_detectors

    cfg = config if config is not None else load_config()
    analyzer = Analyzer(_build_detectors(cfg), cfg)
    return analyzer.analyze(text)


__all__ = ["shield", "inspect"]
