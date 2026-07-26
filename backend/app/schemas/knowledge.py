from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.story_fact import LEVELS
from app.schemas.common import ORMModel

_LEVEL_PATTERN = f"^({'|'.join(LEVELS)})$"


class StoryFactCreate(BaseModel):
    """一条故事事实 + 各方对它的认知程度。

    statement 会被原样引进派生约束里，所以要平铺直叙地写成"一句话陈述"，
    而不是标题式的短语——「晴湾是被装着的」可以，「晴湾之谜」不行。
    """

    statement: str = Field(min_length=2, description="事实本身，一句话陈述")
    is_true: bool = True                       # 在故事世界里是否客观成立
    reader_level: str = Field(default="unknown", pattern=_LEVEL_PATTERN)
    # {"<character_id>": "unknown|suspects|knows|believes_false"}
    # 只登记你真正在意的角色；没登记 = 不建模，不会产生约束
    character_levels: dict[str, str] = {}
    foreshadowing_id: int | None = None


class StoryFactUpdate(BaseModel):
    statement: str | None = None
    is_true: bool | None = None
    reader_level: str | None = Field(default=None, pattern=_LEVEL_PATTERN)
    character_levels: dict[str, str] | None = None
    foreshadowing_id: int | None = None


class StoryFactOut(ORMModel):
    id: int
    project_id: int
    statement: str
    is_true: bool
    reader_level: str
    character_levels: dict[str, str]
    foreshadowing_id: int | None
    created_at: datetime
