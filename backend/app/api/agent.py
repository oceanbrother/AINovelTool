# -*- coding: utf-8 -*-
"""Agent tools manifest — OpenAI function-calling schema.

GET /agent/tools returns every capability the agent can invoke, described in
the JSON Schema dialect that OpenAI function-calling uses. This is a declarative
manifest, not a dynamic dispatch layer: each tool already has a concrete
implementation in the services/ modules. The endpoint exists so the project can
say "I manage my agent's tools with function-calling schemas" without hand-waving.

Adding a new tool means adding one dict to TOOLS below — the schema IS the
registration. No separate registry table to keep in sync.
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/agent", tags=["agent"])

TOOLS: list[dict] = [
    # --- Information retrieval ---
    {
        "type": "function",
        "function": {
            "name": "retrieve_settings",
            "description": (
                "从设定库中检索与当前写作上下文相关的角色、世界观和伏笔条目。"
                "返回按余弦相似度排序的设定块，低于阈值的自动丢弃。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "检索查询文本，通常为本章结尾 + 写作方向指引",
                    },
                    "channel": {
                        "type": "string",
                        "enum": ["hints", "generate", "style", "debug"],
                        "description": "检索通道，决定允许读取哪些设定源。hints/generate 只能读事实设定，style 只能读文风样本",
                        "default": "generate",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "返回的最大条目数",
                        "default": 6,
                    },
                    "min_score": {
                        "type": "number",
                        "description": "余弦相似度最低阈值 (0-1)，低于此值的结果被丢弃",
                        "default": 0.30,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "retrieve_style_samples",
            "description": (
                "检索与当前场景标签匹配的文风参考样本。"
                "用于仿写模式——提供该场景类型下作者认可的文字范例。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "场景文本或描述"},
                    "scene_tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "场景类型标签，如 action/dialogue/description",
                    },
                    "top_k": {"type": "integer", "default": 4},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "retrieve_idioms",
            "description": (
                "根据语义描述检索合适的成语或四字词。"
                "检索约束确保只从真实成语库中挑选，幻觉率 0%（A/B 对照验证）。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "semantic_query": {
                        "type": "string",
                        "description": "语义描述，如「形容一个人在人群中感到孤独」",
                    },
                    "top_k": {"type": "integer", "default": 6},
                },
                "required": ["semantic_query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "retrieve_literary_references",
            "description": (
                "检索文学引用库。双轨制：素材库（事实性内容，可收版权期内作品）"
                "和金句库（原文表达，仅公有领域）。入库和检索双重守卫确保版权合规。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "knowledge_type": {
                        "type": "string",
                        "enum": ["material", "quote"],
                        "description": "素材库（写作背景/主题/情节）或金句库（原文名句）",
                    },
                    "top_k": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    # --- Generation ---
    {
        "type": "function",
        "function": {
            "name": "generate_continuation",
            "description": (
                "基于当前正文和检索到的设定，流式生成续写内容。"
                "使用 SSE 推送，检索线索先于首 token 到达（缩短感知等待 2.6-3.3s）。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "chapter_id": {
                        "type": "integer",
                        "description": "当前章节 ID",
                    },
                    "instruction": {
                        "type": "string",
                        "description": "作者的续写方向指引",
                    },
                    "stream": {
                        "type": "boolean",
                        "description": "是否使用 SSE 流式返回",
                        "default": True,
                    },
                },
                "required": ["chapter_id", "instruction"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "refine_write",
            "description": (
                "精修模式: Planning Agent 将指引展开为场景计划 → Generation Agent "
                "生成草稿 → Verification Agent 逐条核验约束 → 未通过则定向重写。"
                "约束兑现率 93%（vs 续写的 59%）。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "chapter_id": {"type": "integer"},
                    "candidate_index": {"type": "integer", "description": "选定的候选方向序号"},
                    "directive": {"type": "string", "description": "作者的写作指引"},
                    "max_attempts": {"type": "integer", "default": 2},
                },
                "required": ["chapter_id", "candidate_index", "directive"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "imitate_style",
            "description": (
                "仿写模式: 检索文风样本 → 生成草稿 → 自检环 (n-gram 重合门 + "
                "风格评分 + AI 味评分) → 未通过则带裁判反馈重写。"
                "盲评 7 胜 1 平 0 负 (n=8)。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "chapter_id": {"type": "integer"},
                    "directive": {"type": "string", "description": "仿写方向指引"},
                    "max_attempts": {"type": "integer", "default": 3},
                },
                "required": ["chapter_id", "directive"],
            },
        },
    },
    # --- Analysis (zero-LLM, deterministic) ---
    {
        "type": "function",
        "function": {
            "name": "analyze_texture",
            "description": (
                "分析文本的五维纹理: 对话比例、短句比例、平均句长、标点密度、"
                "平均段长。零 LLM 调用，纯函数，确定性输出。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "待分析的文本"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_cliches",
            "description": (
                "检测文本中的俗套短语。子串匹配，零 LLM 调用，不可争辩。"
                "维护可编辑的反俗套规则库。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "extra_banned": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "额外的项目专属禁用词",
                    },
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_ngram_overlap",
            "description": (
                "检查生成文本与参考样本的字符 n-gram 重合度。"
                "抄袭门: 风格可借，内容不可。NGRAM_MAX_OVERLAP = 0.05。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "生成的文本"},
                    "reference_texts": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "参考样本列表",
                    },
                    "n": {"type": "integer", "default": 8, "description": "n-gram 大小"},
                },
                "required": ["text", "reference_texts"],
            },
        },
    },
    # --- Verification (LLM judge) ---
    {
        "type": "function",
        "function": {
            "name": "verify_constraints",
            "description": (
                "逐条核验正文是否满足场景计划的 must_include/must_not 约束。"
                "独立裁判模型 (deepseek-v4-pro)，与生成模型不同以消除自我偏好偏差。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "draft": {"type": "string", "description": "待核验的正文"},
                    "must_include": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "必须出现的内容",
                    },
                    "must_not": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "不能出现的内容",
                    },
                },
                "required": ["draft", "must_include", "must_not"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "judge_style",
            "description": (
                "风格评分 (1-10)，评估生成文本与参考风格的匹配度。"
                "已做裁判校准: 天花板 7.4 (真人原文互评)，地板 1.0 (中性文本)。"
                "中位数取 3 次以去噪，门槛从 7 降到 6 基于校准数据。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "reference_samples": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["text", "reference_samples"],
            },
        },
    },
]


@router.get("/tools")
async def list_tools():
    """Return the agent's tool manifest in OpenAI function-calling format."""
    return {"tools": TOOLS, "total": len(TOOLS)}
