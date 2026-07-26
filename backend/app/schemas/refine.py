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


class RefinePlanRequest(BaseModel):
    fragment: str = Field(min_length=10)
    candidate: PlanCandidate           # 作者选中（可能已合并/编辑）的候选
    top_k_settings: int = Field(default=6, ge=1, le=12)


class RefinePlanResponse(BaseModel):
    plan: ScenePlan
    raw_settings: list[RetrievedChunk]


# --- ③ 校验写作 ----------------------------------------------------------------

class ConstraintCheck(BaseModel):
    text: str                          # 约束原文
    kind: str                          # "include" | "exclude"
    satisfied: bool                    # include: 是否出现；exclude: 是否成功规避
    evidence: str = ""                 # 判定依据（片段/说明）
    derived: bool = False              # 来自知识状态的自动推导，而非作者/LLM 所写


class VerifyResult(BaseModel):
    satisfied: bool                    # 全部约束达标
    checks: list[ConstraintCheck]


class RefineAttempt(BaseModel):
    attempt: int
    satisfied: bool                    # 约束是否全部达标
    checks: list[ConstraintCheck]      # 逐条约束核对
    ngram_overlap: float = 0.0         # 与文风样本的复述率（可选叠加门）
    notes: str = ""                    # 供重写的反馈


class RefineWriteRequest(BaseModel):
    chapter_id: int
    plan: ScenePlan                    # 作者编辑后的场景计划
    instruction: str | None = None
    max_attempts: int = Field(default=2, ge=1, le=4)


class RefineWriteResponse(BaseModel):
    text: str
    attempts: list[RefineAttempt]
    clues: list[RetrievedChunk] = []
