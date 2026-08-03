# -*- coding: utf-8 -*-
"""精修模式 (refine) — 多候选 → 场景计划 → 校验写作 → 重写。

The three payload families mirror the three human-in-the-loop stages:

  candidates  N divergent next-arc options + program-side repetition flags
  plan        the chosen candidate expanded into an editable ScenePlan
  write       the plan-conditioned generation loop, verified against the plan's
              must_include / must_not constraints

ScenePlan is the load-bearing primitive: its must_include / must_not / end_state
are *objectively checkable* (present or not), which is what lets the write loop
gate on a program check instead of a noisy 1-10 judge.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.retrieval import RetrievedChunk


# --- ① 候选 --------------------------------------------------------------------

class PlanCandidate(BaseModel):
    """一条候选走向 —— 必须在 6 个维度上与其它候选拉开实质差异。"""

    summary: str                       # 一句话走向
    conflict_source: str = ""          # 冲突来源
    agency: str = ""                   # 主角主动 / 被动
    reveal_order: str = ""             # 信息揭示顺序
    emotion_arc: str = ""              # 情绪走势
    turn: str = ""                     # 转折机制
    open_question: str = ""            # 结尾留下的问题
    refs: list[int] = []               # 引用的设定编号（对候选检索命中，接地用）
    grounded: list[str] = []           # refs 对应的设定原文，供作者核对
    # --- 程序侧评分（非 LLM 打分）---
    repetition: float = 0.0            # 与已有章节的最大相似度（embedding）
    repetition_flag: bool = False      # 是否疑似重复既有桥段


class RefineCandidatesRequest(BaseModel):
    fragment: str = Field(min_length=10, description="正文片段（当前稿纸结尾）")
    num_candidates: int = Field(default=4, ge=3, le=5)
    top_k_settings: int = Field(default=6, ge=1, le=12)


class RefineCandidatesResponse(BaseModel):
    candidates: list[PlanCandidate]
    raw_settings: list[RetrievedChunk]   # 接地依据（可折叠 debug 视图）


# --- ② 场景计划 ----------------------------------------------------------------

class SubtextPlan(BaseModel):
    """情感潜台词 —— 人物真正感受到什么，以及如何掩饰。

    解决"模型直接宣布情绪"的问题：不是告诉模型"不要写孤独"，
    而是给它一个替代方案——用行为、物件和停顿来泄露情绪。
    设计文档见 docs/style-modeling-and-human-in-the-loop.md §2.2。
    """

    surface_event: str = ""            # 表面发生什么
    hidden_need: str = ""              # 人物真正渴望什么
    denied_emotion: str = ""           # 人物不愿承认什么
    masking_behavior: str = ""         # 用什么行为掩饰
    rupture_moment: str = ""           # 哪个瞬间让伪装短暂破裂
    emotional_residue: str = ""        # 场景结束后留下什么情绪
    emotion_explicitness: float = 0.3  # 直接点破情绪的容许度 (0=全靠行为泄露, 1=可以明说)


class ScenePlan(BaseModel):
    """场景计划 —— 结构化、可校验的中间层。约束"这场要完成什么"，不写台词动作。"""

    goal: str = ""                     # 本场目标
    desire: str = ""                   # 角色欲望
    conflict: str = ""                 # 冲突
    info_shift: str = ""               # 信息变化
    emotion_curve: str = ""            # 情绪曲线
    must_include: list[str] = []       # 必须出现（客观可校验）
    must_not: list[str] = []           # 不能发生（客观可校验）
    # 由知识状态程序推导的禁令（services/knowledge.py），与上面作者/LLM 写的分开存：
    # 前端能标明出处，作者编辑计划时也不会把连续性规则误删。校验时两者合并核对。
    derived_must_not: list[str] = []
    end_state: str = ""                # 结尾状态（为下一场留口子）
    scene_tag: str = ""                # 场景标签（scene.classify_text，零 LLM）
    grounded: list[str] = []           # 接地设定原文
    subtext: SubtextPlan | None = None # 情感潜台词（T2-1：供声音实现阶段使用）
    register_plan: list[dict] = []      # 语域转调计划（T2-2）：有序阶段，每阶段含 register 标签和 paragraphs 数量
    register_pattern: str = ""          # 使用的转调模式名（如 fantasy_fall / delayed_grief / comic_mask / comedy_to_suspense）


class RefinePlanRequest(BaseModel):
    fragment: str = Field(min_length=10)
    candidate: PlanCandidate           # 作者选中（可能已合并/编辑）的候选
    top_k_settings: int = Field(default=6, ge=1, le=12)
    chapter_id: int | None = None
    # 重新生成时带上上一版 plan_id：其中被作者锁定的字段会原样继承，
    # 不受新一次生成影响——"保护已做的判断"落到实处
    previous_plan_id: int | None = None


class RefinePlanResponse(BaseModel):
    plan: ScenePlan
    raw_settings: list[RetrievedChunk]
    plan_id: int | None = None         # 已落库的计划 id，供锁定/修改/回溯


# --- ③ 校验写作 ----------------------------------------------------------------

class ConstraintCheck(BaseModel):
    text: str                          # 约束原文
    kind: str                          # "include" | "exclude"
    satisfied: bool                    # include: 是否出现；exclude: 是否成功规避
    evidence: str = ""                 # 判定依据（片段/说明）
    # 约束来源：author=作者/LLM 写的 · knowledge=知识状态推导 · program=纯程序检测
    # （套话、直接情绪句——这类不问模型，程序数得出来，也就没有裁判方差）
    source: str = "author"


class VerifyResult(BaseModel):
    satisfied: bool                    # 全部约束达标
    checks: list[ConstraintCheck]


class RefineAttempt(BaseModel):
    attempt: int
    satisfied: bool                    # 约束是否全部达标
    checks: list[ConstraintCheck]      # 逐条约束核对
    ngram_overlap: float = 0.0         # 与文风样本的复述率（可选叠加门）
    notes: str = ""                    # 供重写的反馈
    # 稿件本体。此前只发分数卡不发正文，于是一份 0 字的稿子在界面上和评测里
    # 都长得像"一份没达标的稿子"——空稿因此隐形了整整一轮实验。
    # 作者要审的是文字，不是比率；评测要留证的也是文字。
    text: str = ""


class RefineWriteRequest(BaseModel):
    chapter_id: int
    plan: ScenePlan                    # 作者编辑后的场景计划
    instruction: str | None = None
    max_attempts: int = Field(default=2, ge=1, le=4)
    # 两阶段：先写对（朴素、不给文风样本），再换讲法（不改事件与信息边界）。
    # 声音实现后会复核约束——若达成数下降则保留内容草稿。
    two_stage: bool = False


class RefineWriteResponse(BaseModel):
    text: str
    attempts: list[RefineAttempt]
    clues: list[RetrievedChunk] = []
