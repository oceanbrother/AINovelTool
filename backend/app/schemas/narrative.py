from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel
from app.schemas.refine import ScenePlan

# ScenePlan fields the author may freeze. Restricted to the decision-bearing
# ones: locking `grounded` or `scene_tag` would freeze derived data rather than
# a judgement, and `derived_must_not` is program output that must stay live so
# it tracks the knowledge table.
LOCKABLE_FIELDS = (
    "goal", "desire", "conflict", "info_shift",
    "emotion_curve", "must_include", "must_not", "end_state",
    "subtext", "register_pattern", "register_plan",
)


class NarrativeUnitCreate(BaseModel):
    """并入正文那一刻记录的一个场景。

    order_index 由服务端算（同章最大值 +1），不让前端猜——并发并入时前端猜的序号会撞。
    """

    chapter_id: int
    text: str = Field(min_length=1)
    plan_id: int | None = None      # 有计划来源时关联，并把计划推进为 accepted


class NarrativeUnitOut(ORMModel):
    id: int
    chapter_id: int | None
    level: str
    order_index: int
    text: str
    surface_summary: str | None
    scene_tag: str | None
    created_at: datetime


class NarrativePlanOut(ORMModel):
    id: int
    chapter_id: int | None
    unit_id: int | None
    fragment: str | None
    plan: ScenePlan
    locked_fields: list[str]
    review_status: str
    generation_status: str
    created_at: datetime
    updated_at: datetime


class NarrativePlanUpdate(BaseModel):
    """作者对已存计划的修改。

    plan 整体替换而非逐字段 patch —— 前端本来就是把整份计划拿去编辑再交回来的，
    逐字段合并只会在两边各留一套合并逻辑。
    """

    plan: ScenePlan | None = None
    locked_fields: list[str] | None = None
    review_status: str | None = Field(default=None, pattern="^(pending|approved|rejected)$")
    generation_status: str | None = Field(
        default=None, pattern="^(planned|written|accepted)$"
    )
    unit_id: int | None = None
