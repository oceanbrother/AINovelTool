# AINovelTool Agent 架构

> 本文档将现有系统用 Agent 架构语言重新叙述，面向 AI Agent 开发岗位的面试准备。

## 1. 系统定位

AINovelTool 不是单一 LLM 调用的包装，而是一个**多 Agent 协作的长篇创作系统**。它的核心设计问题是：

> 如何让多个独立判断的模型组件协同工作，在长篇创作的约束下（一致性、风格稳定、信息节奏），产生比单次 LLM 调用更高质量的输出？

答案是三层架构：**Planning Agent → Generation Agent → Verification Agent**，加上 **Human-in-the-Loop** 和 **Tool-use 抽象层**。

---

## 2. 架构总览

```
┌─────────────────────────────────────────────────────┐
│                   Human Author                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │ 调校面板  │  │ 拆书面板  │  │ 人工锁定/确认      │   │
│  └──────────┘  └──────────┘  └──────────────────┘   │
└─────────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────────┐
│                 Orchestration Layer                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │ Planning │  │Generate  │  │  Verify + Rewrite │   │
│  │  Agent   │→ │  Agent   │→ │     Agent         │──┘│
│  │(pro)     │  │(flash)   │  │(pro + flash)      │   │
│  └──────────┘  └──────────┘  └──────────────────┘   │
└─────────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────────┐
│                   Tool Layer                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │Retrieval │  │Idiom     │  │ Literary          │   │
│  │(RAG)     │  │Recommend │  │ Reference         │   │
│  └──────────┘  └──────────┘  └──────────────────┘   │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │Texture   │  │Knowledge │  │ Cliché            │   │
│  │Analysis  │  │State     │  │ Detection         │   │
│  └──────────┘  └──────────┘  └──────────────────┘   │
└─────────────────────────────────────────────────────┘
```

---

## 3. Agent 角色定义

### 3.1 Planning Agent

**模型**: `deepseek-v4-pro`（高推理能力）  
**职责**: 将作者的写作方向展开为可执行、可验证的场景计划

**输入**: 正文片段 + 作者指引 + 检索命中的设定  
**输出**: `ScenePlan`（目标、欲望、冲突、必须出现、不能发生、结尾状态）

**关键设计决策**:
- **输入压缩**（`_plot_brief`）：用小模型将原文压缩为前情提要（400→102 字），降低 Planning Agent 的上下文噪音
- **max_tokens=8192**：推理模型的 `max_tokens` 覆盖隐藏推理 token + 可见输出，全局默认 2048 会导致静默空返回（本项目最危险的 bug 之一）
- **PlanParseError**：解析失败抛异常而非返回空计划——空计划比失败更危险

### 3.2 Generation Agent

**模型**: `deepseek-v4-flash`（快速生成）  
**职责**: 根据场景计划生成正文，支持续写和精修两种模式

**两种生成模式**:
| 模式 | 流程 | 产出 |
|------|------|------|
| 续写 | 检索设定 → 组装上下文 → 流式生成 → 滚动摘要 | 下一段正文 |
| 精修 | 计划 → 候选方向 → 场景计划 → 生成草稿 → 校验 → 重写 | 校验通过的正文 |

**关键设计决策**:
- **SSE 流式 + 线索先推**：检索完成（~0.8s）比首 token（~3.1s）快 3×，先推检索线索改善感知延迟
- **`reasoning_effort=none`**：生成端结构化调用关闭推理——实测 91% 的 token 预算被隐藏推理消耗

### 3.3 Verification Agent

**模型**: `deepseek-v4-pro`（独立裁判）+ `deepseek-v4-flash`（辅助裁判）  
**职责**: 逐条核验正文是否满足场景计划的约束

**核验项**:
- `must_include`：必须出现的内容（可核对）
- `must_not`：不能发生的内容（可核对）
- 风格评分（LLM-as-Judge，已校准）
- n-gram 重叠（抄袭门，程序判定）
- 直接情绪句计数（程序判定）

**多裁判仲裁**（设计阶段）:
- 主裁判（pro）和副裁判（flash）分别评分
- 分歧时第三裁判打破僵局
- 分歧率是裁判可靠性的反向指标

**关键设计决策**:
- **裁判 ≠ 生成模型**：刻意使用不同模型，规避 LLM 的**自我偏好偏差**（self-preference bias）——模型倾向给自己的输出打高分。换模型身份才能消除，换新对话/新 agent 不能
- **中位数降噪**：3 次取中位而非均值，抗离群值（单次极端 9 或 2 拖不动中位数）
- **裁判校准**：真人原文互评测天花板（7.4）、中性文本测地板（1.0），确认尺子有效后才使用

---

## 4. Tool-use 抽象层

Agent 的能力通过 **Tool Schema** 暴露，遵循 OpenAI function-calling 规范。每个 Tool 有明确的输入 schema、输出 schema、权限边界和成本模型。

### 4.1 信息检索类 Tool

| Tool | 功能 | 输入 | 输出 |
|------|------|------|------|
| `retrieve_settings` | RAG 检索设定库 | query + channel | 相关设定块 + 相似度 |
| `retrieve_style_samples` | 检索文风参考 | query + scene_tags | 场景匹配的风格样本 |
| `retrieve_idioms` | 检索成语推荐 | semantic_description | 候选成语列表 |
| `retrieve_literary` | 检索文学引用 | query + knowledge_type | 素材库/金句库条目 |

**通道矩阵（Tool Routing）**:
```python
CHANNELS = {
    "hints":    ["character", "world", "foreshadowing"],  # 线索面板
    "generate": ["character", "world", "foreshadowing"],  # 生成链路
    "style":    ["style"],                                 # 文风通道
    "debug":    None,                                      # 调试（全部源）
}
```
每个功能只能读指定通道的源。这是一个**配置与逻辑分离**的设计——改源列表只需改一张表，拼错通道名立刻 KeyError 而非静默返回错误结果。

### 4.2 分析类 Tool

| Tool | 功能 | 成本 |
|------|------|------|
| `analyze_texture` | 对话比/句长/标点密度/段落长 | 零 LLM，纯函数 |
| `detect_cliches` | 俗套短语检测 | 零 LLM，子串匹配 |
| `check_ngram_overlap` | n-gram 重合度 vs 参考样本 | 零 LLM，纯函数 |
| `count_direct_emotion` | 直接情绪句计数 | 零 LLM，正则 |
| `derive_must_not` | 从知识状态编译约束 | 零 LLM，程序逻辑 |

**设计原则**：能用程序判定的绝不用模型。程序判定是确定性的、免费的、可单测的——这正是本项目 README 中「具体、可核对的约束用来指令；统计量用来验收」原则在 Tool 层的体现。

### 4.3 生成后验证类 Tool

| Tool | 功能 | 模型 |
|------|------|------|
| `verify_constraints` | 逐条核验 must_include/must_not | pro |
| `judge_style` | 风格匹配评分（1-10） | pro |
| `judge_ai_flavor` | AI 味评分（1-10，10=最像AI） | pro |

---

## 5. Agentic Loop

精修模式的完整 Agent 循环（`refine.py`）：

```
1. Planning Agent 将指引展开为 ScenePlan
2. ScenePlan 经人工确认（调校面板可修改 prompt）
3. Generation Agent 生成初稿
4. Verification Agent 逐条核验约束
5. 若未通过：
   a. 提取失败证据
   b. 生成定向重写指令（不是"写得更好"，是"删除 X，加入 Y"）
   c. Generation Agent 重写
   d. 回到步骤 4
6. 若全部通过 → 返回最佳稿件
7. 人工最终确认，回写滚动摘要和状态快照
```

**Fault Tolerance**:
- `PlanParseError`：计划解析失败 → 抛异常 + 一次重试，绝不用空计划静默继续
- `EmptyCompletion`：LLM 返回空内容 → 抛异常（推理模型 max_tokens 不足的典型症状）
- 网络故障重试：指数退避，最多 3 次

**Draft Ranking**: 多稿按证据排序——满足约束最多的排最前，空白稿必定排最后（即使它满足所有 must_not，也不满足任何 must_include）

---

## 6. Human-in-the-Loop 设计

### 6.1 调校面板（System Prompt Management）

作者可以直接修改系统使用的 prompt 模板。这不是"把 prompt 暴露给用户"——这是**Agent 的 operating manual 由操作者维护**。

- 所有 prompt 存数据库（`prompt_templates` 表）
- 调校面板提供实时编辑和即时生效
- 作者锁定的字段 Agent 不得修改

### 6.2 三级审核机制

| 级别 | 适用内容 | 示例 |
|------|----------|------|
| 自动通过 | 客观、低风险 | 人物/地点抽取、时间顺序、格式检查 |
| 模型提出、人工抽查 | 有一定主观性 | 场景切分、次要功能、情绪方向、俗套检测 |
| 必须人工确认 | 高影响、不可逆 | 人物核心缺口、章节主功能、重大秘密、伏笔回收、高潮结局 |

### 6.3 审核状态机

```
pending → auto_accepted / approved / rejected → locked
```

`locked` 状态意味着后续 Agent 不得修改该字段。已锁定的字段包括：`primary_function`、`information_policy`、`hidden_need`、`ending_state`、`voice_profile`。

---

## 7. Agent 评测体系

### 7.1 量具校准（Instrument Calibration）

在信任 LLM-as-Judge 的评分之前，先校准它：

1. **天花板测试**：用真人原文互评——最高能打多少分？
2. **地板测试**：用中性文本——最低打多少分？
3. **分辨率测试**：裁判能区分真人和 AI 文本吗？（本项目：5/6）
4. **位置偏差**：正反双序评分，一致才算胜

### 7.2 持续标定

- CI 中配置检查：若裁判模型改变，自动重新运行校准
- 跨模型一致性：pro vs flash 作为裁判的 Cohen's kappa
- 人-裁判 kappa：在留出集上测量

---

## 8. 为什么不用 LangChain？

面试中最可能被问到的问题。回答锚定在**本项目的具体需求**上，不抽象地批评框架。

1. **Tool 路径是结构化的，不需要框架抽象**
   - 所有 Tool 的输入/输出 schema 已通过 Pydantic 模型定义
   - 通道矩阵用一张 dict 做路由，LangChain 的 Tool 抽象在此场景下只增加间接层

2. **Agent 循环需要精细的成本控制**
   - 精修每次循环增加 2-3 次 LLM 调用（校验 + 可能的重写）
   - 需要精确控制哪个调用用哪个模型、什么温度、多少 max_tokens
   - LangChain 的默认 Agent loop 对调用粒度不够透明

3. **量具必须是纯函数**
   - 程序判定（cliché/ngram/texture）是确定性的，必须可单测
   - 框架的黑盒抽象会让"这个数字从哪来"回答不了

4. **一段真实的失败经历**
   - 本项目最大的 bug（空计划静默运行）是在自建循环中发现的
   - 自建意味着能读 API 响应的 `usage.reasoning_tokens` 字段
   - 如果框架屏蔽了这个字段，永远找不到根因

---

## 9. 成本模型

| 操作 | LLM 调用 | 估计成本 |
|------|----------|----------|
| 续写（SSE 流式） | 1 × flash | ~$0.002 |
| 精修（计划→校验→重写） | 1 × pro (plan) + 2-3 × flash (draft/rewrite) + 3 × pro (verify) | ~$0.02 |
| 仿写（自检环） | 1 × flash (draft) + 1 × pro (verify) + 重写 | ~$0.01 |
| 成语推荐 | 0 LLM（仅检索） | $0 |
| 文学引用 | 0 LLM（仅检索） | $0 |

> 成本数字待 T1-3 token 统计完成后更新为精确值。

---

## 10. 面试叙事框架

### 「介绍一下你的项目」（1 分钟）

> AINovelTool 是一个多 Agent 协作的长篇 AI 写作助手。核心思路是用 **RAG 检索约束生成**，抑制 LLM 的幻觉问题。
>
> 架构上分三层：Planning Agent 把写作方向展开成可验证的场景计划，Generation Agent 按计划生成正文，Verification Agent 用独立模型逐条核验约束兑现——这是一个带 human-in-the-loop 的 agentic loop。
>
> 做了几件比较硬的事：裁判模型和生成模型刻意不同以消除自我偏好偏差；裁判本身做了真人校准（天花板/地板/分辨率）；用通道矩阵做 Tool 路由，纯函数做零成本判定；所有数字都有 eval harness 可复现。诚实地记录了三个负结果——场景对齐没用、节奏统计不能注入 prompt、功能标签分类器三次不过闸判死。

### 「你这个是 Agent 吗？」（如果被质疑）

> 诚实说：核心是一个 **RAG 应用**，不是典型自主 agent。但精修链路 `计划→生成→校验→决策重写` 已经是 agentic loop 的种子——它有 tool-use（检索/校验/风格检查）、有决策点（过检/重写）、有与生成不同的裁判模型。往完全自主方向推，就是让章节 Agent 自己规划细纲、决定检索什么、用裁判自我批判、决定重写还是继续——自检环已经有了，缺的是自主 planning 的触发机制。
