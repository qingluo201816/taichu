"""LLM 工厂：统一创建和切换不同提供商的 LLM 实例。"""

from langchain_openai import ChatOpenAI

from taichu.config import settings


def get_llm(provider: str | None = None) -> ChatOpenAI:
    """根据 provider 返回对应的 LLM 实例。

    未来扩展：新增 provider 只需在此函数加一个分支。
    """
    provider = provider or settings.llm_provider

    if provider == "deepseek":
        return ChatOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_api_base,
            model=settings.deepseek_model,
        )

    # 未来扩展：
    # if provider == "openai":
    #     return ChatOpenAI(model="gpt-4o")
    # if provider == "anthropic":
    #     return ChatAnthropic(model="claude-sonnet-4-6")

    raise ValueError(f"Unknown LLM provider: {provider}")


def list_providers() -> list[str]:
    """返回支持的模型提供商列表。"""
    return ["deepseek"]
