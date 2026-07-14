"""外部搜索与来源读取的应用层模型。"""

from pydantic import BaseModel, ConfigDict, Field


class ExternalResearchModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ExternalSearchResult(ExternalResearchModel):
    title: str = Field(min_length=1)
    url: str = Field(min_length=8)
    domain: str = Field(min_length=1)
    snippet: str = ""
    published_at: str | None = None


class ExternalDocument(ExternalResearchModel):
    url: str = Field(min_length=8)
    final_url: str = Field(min_length=8)
    title: str = ""
    content: str
