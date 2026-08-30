"""从 LangChain ChatModel 创建语义评估裁判。"""

from langchain_core.language_models.chat_models import BaseChatModel

from taichu.application.contracts.llm import LLMModelCatalogContract
from taichu.config import Settings
from taichu.infrastructure.evaluations.llm_judge_adapter import (
    LLMEvaluationJudgeAdapter,
)


def create_evaluation_judge(
    settings: Settings,
    llm: BaseChatModel,
    model_catalog: LLMModelCatalogContract,
    *,
    configured: bool,
) -> LLMEvaluationJudgeAdapter:
    """显式裁判模型和默认模型都复用同一产品级供应商网关。"""
    model_id = settings.evaluation_judge_model.strip()
    if not model_id:
        default = next(
            (profile for profile in model_catalog.list_models() if profile.is_default),
            None,
        )
        model_id = default.id if default is not None else ""
    known = any(profile.id == model_id for profile in model_catalog.list_models())
    return LLMEvaluationJudgeAdapter(
        llm,
        model_catalog,
        model_id=model_id,
        configured=configured and known,
    )
