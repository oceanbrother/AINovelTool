# 叙事功能建模设计

> 状态：设计草案  
> 适用项目：AINovelTool  
> 目标版本：MVP → v1.1  
> 技术栈：FastAPI、SQLAlchemy、PostgreSQL、JSONB、pgvector

## 1. 背景

长篇作品的生成难点不只是上下文长度不足，也不只是向量检索不保留顺序。更根本的问题是：普通 RAG 通常只能回答“哪些文本与当前内容相似”，却无法回答：

- 当前章节为什么需要这个场景；
- 这个场景应该改变人物、关系或读者认知中的哪一部分；
- 哪些信息现在可以公开，哪些必须继续隐藏；
- 当前情绪和冲突应该上升、维持还是回落；
- 这个场景正在铺垫什么，未来又应在哪里回收。

因此，AINovelTool 需要在语义检索之外建立一套显式的叙事功能模型。

本设计的核心定义是：

```text
叙事功能 = 在特定前置条件下，通过一组叙事操作，产生预期状态变化
```

形式化表示：

```text
State_before + Narrative_operations → State_after
```

叙事功能不是“校园”“战斗”“暗恋”等题材标签，也不只是“人物描写”“环境描写”等文本类型。它描述的是一段文字在整部作品中承担的任务。

---

## 2. 设计目标

### 2.1 核心目标

1. 将原作拆解为可查询的叙事单元。
2. 区分“写了什么”和“为什么这样写”。
3. 显式记录人物、关系、知识、情绪和叙事压力的变化。
4. 保留场景顺序、因果、铺垫和回收关系。
5. 支持按照叙事功能检索参考场景，而不只按文本语义检索。
6. 在生成前创建叙事任务卡，在生成后验证功能是否完成。
7. 为长篇节奏规划、连续性检查和自动评测提供结构化数据。

### 2.2 非目标

MVP 阶段暂不尝试：

- 完全自动理解作品中的所有深层主题；
- 用一套固定标签覆盖所有文学类型；
- 仅凭单次模型调用完成完美标注；
- 用叙事功能模型替代事实记忆、人物设定或正文 Embedding；
- 直接复现特定作品的原文措辞。

叙事功能模型是现有 RAG、故事状态和生成服务之上的控制层。

---

## 3. 核心概念

## 3.1 叙事单元

作品应按照不同粒度拆分为四层叙事单元。

| 层级 | 典型长度 | 主要职责 |
|---|---:|---|
| Beat / 叙事节拍 | 1～5 句 | 一次反应、发现、情绪变化或微型反转 |
| Scene / 场景 | 500～3000 字 | 完成一个局部目标和状态变化 |
| Chapter / 章节 | 3000～10000 字 | 推进一组人物、关系、信息和冲突 |
| Arc / 阶段或卷 | 数章至一卷 | 完成人物弧线或主要矛盾阶段 |

各层级通过 `parent_id` 建立父子关系，通过顺序边建立前后关系。

示例：

```text
Arc：主人公从怀疑现实到主动调查
└── Chapter：第一次获得无法忽略的异常证据
    └── Scene：全班同学否认昨天发生过某件事
        ├── Beat：主人公提出问题
        ├── Beat：同学表现困惑
        └── Beat：主人公发现照片也被修改
```

## 3.2 表层内容与叙事功能

每个叙事单元同时保存两种摘要。

### 表层摘要

描述这段文字发生了什么：

```text
少年在学校晚会后台幻想自己被神秘组织接走。
```

### 功能摘要

描述作者为什么安排这段文字：

```text
在超自然尚未得到确认时，通过公开场合中的边缘位置和身份翻转幻想，
暴露主人公渴望被看见的心理缺口，并为后续神秘邀请增加情感意义。
```

两者分别生成向量：

- `semantic_embedding`：支持内容和事实相关检索；
- `function_embedding`：支持叙事功能类比检索。

## 3.3 叙事功能与实现手法

叙事功能和实现手法必须分开。

例如，功能都是“暴露人物孤独”，但可以采用不同手法：

- 放学后没有人来接；
- 群聊中的发言无人回应；
- 集体照中人物站在边缘；
- 生病后只收到系统通知；
- 主角熟悉所有人，却没人记得他的生日；
- 主角幻想在众人面前被隆重选中。

对应结构：

```json
{
  "function": "expose_character_lack",
  "technique": "contrast_public_fantasy_with_social_invisibility"
}
```

这样可以避免模型把“孤独”机械地等同于夕阳、天台、耳机等固定意象。

---

## 4. 状态模型

系统至少维护五条状态轴。

## 4.1 世界事实状态

记录客观世界中成立的事实：

- 某个秘密是否真实；
- 某项规则是否存在；
- 某个事件是否已经发生；
- 某个地点、物品或能力处于什么状态。

## 4.2 人物知识状态

分别记录每个角色知道、怀疑和误解的内容：

```json
{
  "character_id": "character_001",
  "knows": ["学校监控在凌晨会中断"],
  "suspects": ["老师可能隐瞒了某件事"],
  "believes_false": ["异常只与自己有关"]
}
```

## 4.3 读者知识状态

读者状态必须与人物状态分开：

- 读者已经知道但主角不知道什么；
- 读者怀疑但尚未确认什么；
- 作者正在引导读者形成什么错误判断。

示例：

```json
{
  "objective_truth": 1.0,
  "reader_certainty": 0.55,
  "protagonist_certainty": 0.25,
  "classmates_certainty": 0.0
}
```

## 4.4 人物心理状态

MVP 可使用 `0.0～1.0` 的归一化数值记录：

- 归属感；
- 自尊；
- 信任；
- 恐惧；
- 孤独；
- 行动意愿；
- 对现实的确信程度；
- 对目标的执着程度。

数值不是心理学测量结果，而是用于比较相邻场景的变化方向。

## 4.5 叙事压力状态

记录当前文本对读者施加的压力：

- 悬念强度；
- 外部威胁；
- 关系冲突；
- 情绪强度；
- 信息密度；
- 行动速度；
- 未闭合问题数量。

---

## 5. 叙事功能标签体系

MVP 使用少量稳定标签。每个叙事单元设置一个主功能，最多设置三个次功能。

## 5.1 人物功能

| 标签 | 含义 |
|---|---|
| `introduce_character` | 引入人物及其初始定位 |
| `expose_character_lack` | 暴露人物缺口 |
| `show_compensatory_behavior` | 展示人物的心理补偿行为 |
| `reveal_hidden_desire` | 暴露隐藏欲望 |
| `test_character_value` | 考验人物价值观 |
| `increase_character_agency` | 提高人物主动性 |
| `force_character_choice` | 迫使人物做出选择 |
| `show_consequence` | 展示选择或行为的后果 |

## 5.2 关系功能

| 标签 | 含义 |
|---|---|
| `establish_relationship` | 建立关系 |
| `increase_intimacy` | 提高亲密度 |
| `create_misunderstanding` | 制造误解 |
| `shift_power_balance` | 改变关系中的权力平衡 |
| `expose_relationship_asymmetry` | 暴露双方投入或认知不对等 |
| `break_trust` | 破坏信任 |
| `repair_trust` | 修复信任 |
| `separate_characters` | 使人物分离 |

## 5.3 信息功能

| 标签 | 含义 |
|---|---|
| `plant_question` | 向读者提出问题 |
| `provide_clue` | 提供线索 |
| `misdirect_reader` | 引导错误判断 |
| `confirm_hypothesis` | 确认已有假设 |
| `reframe_previous_event` | 重新解释旧事件 |
| `reveal_secret` | 揭示秘密 |
| `withhold_answer` | 延迟答案 |
| `create_information_asymmetry` | 制造人物与读者之间的信息差 |

## 5.4 冲突功能

| 标签 | 含义 |
|---|---|
| `introduce_threat` | 引入威胁 |
| `escalate_conflict` | 升级冲突 |
| `delay_confrontation` | 延迟正面对抗 |
| `force_confrontation` | 迫使双方对抗 |
| `temporary_resolution` | 暂时解决冲突 |
| `reverse_advantage` | 逆转优势 |
| `show_cost` | 展示代价 |

## 5.5 节奏功能

| 标签 | 含义 |
|---|---|
| `establish_normalcy` | 建立日常基线 |
| `release_tension` | 释放压力 |
| `build_tension` | 提高压力 |
| `false_relief` | 制造虚假安全感 |
| `prepare_climax` | 为高潮蓄力 |
| `deliver_climax` | 兑现高潮 |
| `aftermath` | 展示高潮后果 |
| `transition` | 完成时空或任务过渡 |

## 5.6 长篇结构功能

| 标签 | 含义 |
|---|---|
| `setup` | 建立铺垫 |
| `reinforce_setup` | 强化已有铺垫 |
| `partial_payoff` | 部分回收 |
| `payoff` | 完整回收 |
| `open_loop` | 打开叙事问题 |
| `advance_loop` | 推进未闭合问题 |
| `close_loop` | 关闭叙事问题 |
| `seed_future_arc` | 为未来阶段埋下种子 |

---

## 6. 单元数据结构

推荐的完整叙事单元结构：

```json
{
  "unit_id": "scene_001_03",
  "parent_id": "chapter_001",
  "level": "scene",
  "chapter_index": 1,
  "scene_index": 3,

  "surface_summary": "少年在学校晚会后台幻想被神秘组织接走",
  "function_summary": "暴露主人公渴望被看见的心理缺口，并为身份翻转做铺垫",

  "primary_function": "expose_character_lack",
  "secondary_functions": [
    "show_compensatory_behavior",
    "setup",
    "build_reader_empathy"
  ],

  "techniques": [
    "place_character_at_social_margin",
    "expand_compensatory_fantasy",
    "return_to_mundane_reality"
  ],

  "preconditions": {
    "protagonist_status": "socially_invisible",
    "supernatural_certainty_for_character": 0.0,
    "supernatural_certainty_for_reader": 0.05,
    "relationship_to_love_interest": "distant",
    "protagonist_agency": 0.2
  },

  "operations": [
    "展示公开活动中的边缘位置",
    "让人物想象身份翻转",
    "让幻想核心落在被特定人物看见",
    "用琐碎现实打断幻想"
  ],

  "state_delta": {
    "reader_empathy": 0.25,
    "protagonist_self_awareness": 0.05,
    "mystery_tension": 0.1,
    "external_conflict": 0.0
  },

  "reader_effect": [
    "觉得人物的幻想有些滑稽",
    "意识到人物其实很孤独",
    "期待幻想以某种方式成真"
  ],

  "information_policy": {
    "revealed": [
      "主角希望自己拥有隐藏身份"
    ],
    "withheld": [
      "超自然世界是否真实",
      "主角是否真的特殊"
    ],
    "forbidden": [
      "直接证明神秘组织存在"
    ]
  },

  "setup_ids": [],
  "payoff_target_ids": ["scene_004_02"],

  "pacing": {
    "intensity_start": 0.15,
    "intensity_peak": 0.35,
    "intensity_end": 0.12,
    "information_gain": 0.12
  }
}
```

`build_reader_empathy` 可先作为效果标签而不是核心功能枚举，后续根据标注数据决定是否升级为正式标签。

---

## 7. 原作分析流程

原作分析采用两遍标注，避免把“发生了什么”和“为什么这样写”混在一起。

## 7.1 第一遍：事实抽取

第一遍只提取相对客观的信息：

- 出场人物；
- 地点和时间；
- 可观察事件；
- 人物行为；
- 新增事实；
- 人物知识变化；
- 关系变化；
- 场景前后状态。

输出示例：

```json
{
  "characters": ["主角", "同学", "老师"],
  "events": [
    "主角独自待在晚会边缘",
    "主角幻想自己被神秘组织接走",
    "现实中没有人注意他"
  ],
  "knowledge_changes": [],
  "relationship_changes": [],
  "confirmed_supernatural_event": false
}
```

## 7.2 第二遍：功能推断

第二遍基于事实结果回答：

1. 作者为什么需要这一场？
2. 删除这一场后，后续哪些情节仍能发生，但情感效果会下降？
3. 这一场主要改变人物、关系、信息还是读者预期？
4. 这一场为哪个后续事件建立了前置条件？
5. 为什么它必须出现在当前位置？
6. 哪些信息被有意隐瞒？

第二遍输出功能摘要、标签、状态增量、信息策略和结构边。

## 7.3 人工校正

MVP 阶段应允许用户修改：

- 主功能和次功能；
- 铺垫与回收关系；
- 状态增量；
- 信息公开范围；
- 场景边界。

模型标注是候选结果，不应直接视为事实。

---

## 8. 长篇功能曲线

以“普通高中生活逐渐显得不真实”为例：

| 章节 | 主要叙事功能 | 异常强度 | 信息上限 |
|---|---|---:|---|
| 第 1 章 | 建立日常，暴露人物缺口 | 0.05 | 只能出现可忽略的违和感 |
| 第 2 章 | 植入第一次异常 | 0.15 | 异常可解释为记错 |
| 第 3 章 | 让周围人否认异常 | 0.25 | 主角开始自我怀疑 |
| 第 4 章 | 重复异常并形成规律 | 0.40 | 可以提出假设，不能确认 |
| 第 5 章 | 让异常影响人物关系 | 0.50 | 证明异常具有现实后果 |
| 第 6 章 | 提供不完整证据 | 0.65 | 排除纯粹幻觉 |
| 第 7 章 | 主角主动测试现实 | 0.75 | 主角获得行动能力 |
| 第 8 章 | 建立暂时成立的错误解释 | 0.55 | 制造虚假答案 |
| 第 9 章 | 重新解释旧事件 | 0.85 | 真相开始合拢 |
| 第 10 章 | 确认世界机制 | 1.00 | 揭晓真相并引入代价 |

功能曲线重点控制：

- 异常的确认速度；
- 主角主动性的变化；
- 读者和主角之间的信息差；
- 每章的信息增量；
- 高压与缓冲场景的交替；
- 铺垫、强化、部分回收和完整回收的间距。

---

## 9. 功能感知检索

## 9.1 查询条件

生成场景前，检索请求不应只有自然语言关键词，还应包含：

```json
{
  "story_position": 0.1,
  "primary_function": "expose_character_lack",
  "required_preconditions": {
    "protagonist_status": "socially_invisible",
    "supernatural_certainty_for_reader_max": 0.1
  },
  "target_pacing": {
    "intensity": 0.2,
    "information_gain": 0.1
  },
  "forbidden_functions": [
    "confirm_hypothesis",
    "reveal_secret"
  ]
}
```

## 9.2 综合评分

建议初始评分：

```text
score =
0.30 × narrative_function_match
+ 0.20 × precondition_compatibility
+ 0.15 × story_position_match
+ 0.15 × pacing_match
+ 0.10 × semantic_similarity
+ 0.10 × relationship_pattern_match
```

该权重作为初始值，后续通过评测数据调整。

## 9.3 序列扩展

命中场景后，不只返回该场景，还应扩展：

```text
前一个场景
+ 当前场景
+ 后一个场景
+ 对应的铺垫场景
+ 对应的部分回收或完整回收场景
```

这样模型才能理解一个叙事功能如何被准备、执行并产生后果。

---

## 10. 生成流程

完整生成流程：

```text
全局故事规划
→ 确定当前章节功能
→ 读取章节前状态
→ 创建场景叙事任务卡
→ 按功能和前置状态检索参考
→ 将参考抽象为手法卡
→ 生成正文
→ 反向提取实际叙事功能
→ 比较目标与实际状态变化
→ 必要时定向重写
→ 保存正文和新状态快照
```

## 10.1 叙事任务卡

```json
{
  "scene_goal": "让读者理解主角渴望被看见",
  "primary_function": "expose_character_lack",

  "required_preconditions": [
    "主角在集体活动中处于边缘",
    "存在一名主角在意但无法接近的人"
  ],

  "required_operations": [
    "先展示现实中的被忽略",
    "触发一段身份翻转幻想",
    "让幻想核心是被特定人物看见",
    "用琐碎现实打断幻想"
  ],

  "target_deltas": {
    "reader_empathy": 0.2,
    "mystery_tension": 0.05,
    "protagonist_agency": 0.0
  },

  "must_not": [
    "直接说明主角非常孤独",
    "确认超自然世界存在",
    "让主角采取重大行动",
    "复用参考作品中的专有设定或标志性情节"
  ],

  "ending_state": {
    "character": "仍然被动",
    "reader": "期待他的幻想以某种形式成真"
  }
}
```

## 10.2 手法卡

参考文本不直接进入最终提示词，而是先抽象为不包含专有表达的手法卡：

```json
{
  "function": "expose_character_lack",
  "technique_sequence": [
    "将人物放在热闹场景的边缘",
    "让人物想象一次公开身份翻转",
    "使幻想真正满足的是情感需要而非力量需要",
    "用现实中的琐碎任务打断幻想"
  ],
  "avoid_copying": [
    "原作人物",
    "原作机构",
    "原作交通工具",
    "原作标志性比喻",
    "原作句式"
  ]
}
```

---

## 11. 生成后验证

生成后使用独立调用重新抽取实际功能：

```json
{
  "detected_primary_function": "plant_question",
  "detected_secondary_functions": [
    "confirm_hypothesis"
  ],
  "actual_state_delta": {
    "reader_empathy": 0.08,
    "mystery_tension": 0.35
  },
  "violations": [
    "过早确认超自然存在"
  ]
}
```

与任务卡比较后输出：

```json
{
  "primary_function_score": 0.62,
  "state_delta_accuracy": 0.41,
  "information_policy_score": 0.25,
  "pacing_match": 0.70,
  "needs_rewrite": true,
  "rewrite_instruction": "删除客观超自然证据，将异常改为可以被现实解释的偶然。"
}
```

重写指令应针对功能偏差，不应只使用“更有文采”“更自然”等模糊要求。

---

## 12. PostgreSQL 数据模型

MVP 使用 PostgreSQL、JSONB 和 pgvector，无需立即引入图数据库。

## 12.1 `narrative_units`

```sql
CREATE TABLE narrative_units (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    parent_id UUID REFERENCES narrative_units(id) ON DELETE CASCADE,
    level VARCHAR(16) NOT NULL,
    chapter_index INTEGER,
    scene_index INTEGER,
    beat_index INTEGER,
    original_text TEXT,
    surface_summary TEXT NOT NULL,
    function_summary TEXT NOT NULL,
    primary_function VARCHAR(64) NOT NULL,
    secondary_functions JSONB NOT NULL DEFAULT '[]'::jsonb,
    techniques JSONB NOT NULL DEFAULT '[]'::jsonb,
    preconditions JSONB NOT NULL DEFAULT '{}'::jsonb,
    operations JSONB NOT NULL DEFAULT '[]'::jsonb,
    reader_effect JSONB NOT NULL DEFAULT '[]'::jsonb,
    information_policy JSONB NOT NULL DEFAULT '{}'::jsonb,
    pacing JSONB NOT NULL DEFAULT '{}'::jsonb,
    semantic_embedding vector(1024),
    function_embedding vector(1024),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

向量维度必须与实际 Embedding 模型一致，`1024` 仅为示例。

## 12.2 `narrative_edges`

```sql
CREATE TABLE narrative_edges (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    source_unit_id UUID NOT NULL REFERENCES narrative_units(id) ON DELETE CASCADE,
    target_unit_id UUID NOT NULL REFERENCES narrative_units(id) ON DELETE CASCADE,
    edge_type VARCHAR(32) NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_unit_id, target_unit_id, edge_type)
);
```

`edge_type` 初始支持：

```text
next
causes
contrasts
mirrors
setup_for
payoff_of
reinforces
```

## 12.3 `story_state_snapshots`

```sql
CREATE TABLE story_state_snapshots (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    unit_id UUID NOT NULL REFERENCES narrative_units(id) ON DELETE CASCADE,
    state_before JSONB NOT NULL,
    state_after JSONB NOT NULL,
    state_delta JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (unit_id)
);
```

## 12.4 `narrative_plans`

```sql
CREATE TABLE narrative_plans (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    parent_plan_id UUID REFERENCES narrative_plans(id) ON DELETE CASCADE,
    unit_level VARCHAR(16) NOT NULL,
    unit_index INTEGER,
    scene_goal TEXT NOT NULL,
    target_functions JSONB NOT NULL,
    required_preconditions JSONB NOT NULL DEFAULT '{}'::jsonb,
    required_operations JSONB NOT NULL DEFAULT '[]'::jsonb,
    target_deltas JSONB NOT NULL DEFAULT '{}'::jsonb,
    information_policy JSONB NOT NULL DEFAULT '{}'::jsonb,
    pacing_target JSONB NOT NULL DEFAULT '{}'::jsonb,
    constraints JSONB NOT NULL DEFAULT '[]'::jsonb,
    generation_status VARCHAR(24) NOT NULL DEFAULT 'planned',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## 13. API 草案

```text
POST   /api/projects/{project_id}/narrative/analyze
GET    /api/projects/{project_id}/narrative/units
GET    /api/projects/{project_id}/narrative/units/{unit_id}
PATCH  /api/projects/{project_id}/narrative/units/{unit_id}

POST   /api/projects/{project_id}/narrative/retrieve
POST   /api/projects/{project_id}/narrative/plans
GET    /api/projects/{project_id}/narrative/plans
PATCH  /api/projects/{project_id}/narrative/plans/{plan_id}

POST   /api/projects/{project_id}/narrative/generate
POST   /api/projects/{project_id}/narrative/evaluate
POST   /api/projects/{project_id}/narrative/rewrite
```

---

## 14. 评测指标

## 14.1 单场景指标

- 主功能识别一致率；
- 次功能覆盖率；
- 前置条件满足率；
- 目标状态变化准确率；
- 信息策略违规率；
- 节奏目标偏差；
- 禁止元素命中率；
- 参考文本表达重合风险。

## 14.2 章节级指标

- 场景功能是否重复；
- 信息增量是否过高或过低；
- 紧张度曲线是否符合计划；
- 人物主动性变化是否合理；
- 场景之间是否存在因果断裂；
- 章节结尾是否完成目标功能。

## 14.3 长篇指标

- 铺垫回收率；
- 平均铺垫距离；
- 提前揭晓率；
- 未闭合叙事问题数量；
- 人物知识越界次数；
- 人物状态突变次数；
- 高强度场景连续密度；
- 功能类型多样性；
- 规划功能与实际功能的一致率。

---

## 15. MVP 实施顺序

### 阶段一：结构与人工标注

1. 增加四张核心表。
2. 实现 Scene 和 Chapter 两级叙事单元。
3. 提供主功能、次功能和状态变化的人工编辑接口。
4. 保存顺序、铺垫和回收边。

### 阶段二：自动分析

1. 实现事实抽取调用。
2. 实现功能推断调用。
3. 为表层摘要和功能摘要分别生成 Embedding。
4. 提供人工校正后的重新索引。

### 阶段三：功能检索与任务卡

1. 实现综合评分检索。
2. 实现相邻场景和结构边扩展。
3. 根据章节计划创建叙事任务卡。
4. 将命中参考抽象为手法卡。

### 阶段四：生成后验证

1. 反向识别生成文本的实际功能。
2. 比较目标状态变化与实际状态变化。
3. 检查信息策略和禁止条件。
4. 根据偏差生成定向重写指令。

### 阶段五：长篇评测

1. 绘制章节异常强度、冲突强度和信息增量曲线。
2. 检测连续高强度、连续低信息和功能重复。
3. 检测铺垫未回收与回收缺少铺垫。
4. 建立作品级叙事功能评测集。

---

## 16. 设计原则总结

叙事功能建模必须持续回答四个问题：

1. 这一段开始前，故事处于什么状态？
2. 作者通过什么叙事操作改变了状态？
3. 这一段结束后，谁的什么状态发生了变化？
4. 为什么这个变化必须现在发生，而不能提前或推后？

仅标记“校园日常”“暗恋”“幻想”“悬疑”仍然只是内容分类。

真正可用于长篇生成的表示应当是：

> 在长篇的当前位置，为了让未来事件产生预期的情感效果，需要先改变读者对人物的理解，但暂时不能改变人物对世界真相的认知。

语义检索负责寻找“像什么”，叙事功能模型负责决定“为什么现在这样写”，故事状态负责约束“写完以后发生了什么变化”。三者组合后，才能形成面向长篇作品的可控生成系统。
