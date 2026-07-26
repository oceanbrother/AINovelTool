# 原创风味建模与人机协作设计

> 状态：设计草案  
> 适用项目：AINovelTool  
> 前置文档：[叙事功能建模设计](./narrative-function-modeling.md)  
> 目标：在叙事功能正确的基础上，建立稳定、原创、有辨识度的叙述声音，并明确大模型与人工作者的职责边界

## 1. 背景

叙事功能建模可以帮助系统回答：

- 一个场景为什么存在；
- 它应当改变人物、关系、信息或读者预期中的什么；
- 哪些信息现在可以公开；
- 哪些信息必须继续隐藏；
- 当前场景与前后章节如何连接。

但即使叙事功能完全正确，大模型生成的正文仍可能出现以下问题：

- 每个场景都能完成任务，但文字缺少稳定声音；
- 人物情绪被直接解释，缺少潜台词；
- 幽默、抒情、日常和悬疑之间缺少自然转调；
- 语言过于工整，像一篇完成度不错但没有作者性的范文；
- 大量使用通用青春意象和高频套话；
- 能生成“像小说”的文字，却无法形成某部新作品独有的阅读体验。

原因在于：

```text
叙事功能解决“为什么写”
情感潜台词解决“人物真正感受到什么”
话语策略解决“叙述者如何把它说出来”
```

因此，完整系统不应是：

```text
叙事功能 → 生成正文
```

而应扩展为：

```text
叙事功能
→ 情感潜台词
→ 话语策略
→ 内容草稿
→ 声音实现
→ 功能评审
→ 风格评审
→ 人工确认
```

本文不以复刻任何在世作者的独特文风为目标，而是将用户喜欢的阅读体验拆解为非专属、可泛化的风格维度，最终形成项目自己的原创声音。

---

## 2. 三层创作控制模型

## 2.1 叙事功能层

叙事功能层回答：

- 这一场为什么存在？
- 场景开始前是什么状态？
- 场景结束后什么发生了变化？
- 它为未来哪个事件建立前置条件？
- 哪些信息必须继续隐瞒？

示例：

```json
{
  "primary_function": "expose_character_lack",
  "secondary_functions": [
    "show_compensatory_behavior",
    "setup"
  ],
  "target_deltas": {
    "reader_empathy": "+1",
    "mystery_tension": "+1",
    "protagonist_agency": "0"
  }
}
```

## 2.2 情感潜台词层

情感潜台词层回答：

- 表面发生的是什么？
- 人物真正渴望什么？
- 人物不愿承认什么？
- 人物使用什么行为掩饰？
- 哪个瞬间让伪装短暂破裂？
- 场景结束后留下什么情绪残留？

示例：

```json
{
  "surface_event": "主人公参加普通校园活动",
  "declared_desire": "尽快离开无聊的活动",
  "hidden_need": "希望有人公开选择自己",
  "denied_emotion": "害怕自己无足轻重",
  "masking_behavior": "用玩笑和无所谓掩饰",
  "rupture_moment": "有人准确叫出他的名字",
  "emotional_residue": "事情结束后仍不敢相信",
  "emotion_explicitness": 0.25
}
```

## 2.3 话语策略层

话语策略层回答：

- 叙述者离人物有多近？
- 叙述者是在同情、调侃还是冷眼观察？
- 文字从日常、幽默、抒情还是宏大想象开始？
- 不同语域按照什么顺序切换？
- 情绪在哪里抬高，在哪里落回现实？
- 最后一句采用抬高、停顿、反转还是冷落地？

示例：

```json
{
  "narrator_distance": 0.35,
  "narrator_empathy": 0.85,
  "narrator_irony": 0.60,
  "colloquial_ratio": 0.55,
  "lyrical_ratio": 0.25,
  "expository_ratio": 0.20,
  "ending_mode": "quiet_drop"
}
```

---

## 3. 原创风味的关键维度

## 3.1 叙述者的同情与调侃

一种有活力的青春叙事声音，往往不是单纯同情人物，也不是单纯嘲笑人物，而是同时保持：

```text
叙述者知道人物的幻想有些幼稚
+ 叙述者理解人物为什么需要这种幻想
```

建议拆成两个独立维度：

```json
{
  "narrator_irony": 0.65,
  "narrator_empathy": 0.85
}
```

常见失败：

- 只有调侃：人物沦为段子；
- 只有同情：文字变成伤感独白；
- 两者都弱：人物只是剧情执行工具；
- 调侃和同情同时过高：叙述者频繁替人物解释，显得过度用力。

目标不是固定数值，而是形成项目稳定的叙述者立场。

## 3.2 宏大想象与琐碎现实的碰撞

阅读体验常来自两套尺度之间的冲突：

```text
现实：
考试、跑腿、旧电脑、同学关系、家庭琐事

幻想：
隐藏身份、神秘召唤、宏大使命、公开的身份翻转

落地：
仍然要回家、收拾东西、完成值日、面对普通人的评价
```

关键不是三个元素同时出现，而是按照一定顺序发生：

```text
现实压低人物
→ 幻想将人物抬到极高处
→ 琐碎细节把人物重新拉回现实
```

这是一种语域转调模式，应当单独建模，不能只存成一个风格向量。

## 3.3 延迟承认情绪

人物面对失落时，可以先：

- 说笑；
- 转移话题；
- 计算实际得失；
- 打游戏；
- 假装无所谓；
- 产生夸张幻想；
- 关注一个与情绪无关的小物件。

真正的情绪在后面才泄露。

如果任务卡只写“表现人物孤独”，模型容易直接生成：

```text
他忽然感到自己很孤独。
```

功能上正确，阅读体验却很薄。

更合适的控制方式：

```json
{
  "surface_emotion": "不在乎",
  "hidden_emotion": "害怕自己不值得被选择",
  "masking_behavior": "开玩笑并计算实际得失",
  "rupture_moment": "听到有人明确表达在乎",
  "direct_emotion_sentences_max": 1
}
```

## 3.4 表层欲望与深层需要

人物的表层欲望可能是：

```text
我想成为特殊的人。
```

深层需要可能是：

```text
我想让某个人终于注意到我。
我想证明以前被忽略并不是因为我没有价值。
我想有人明确地选择我。
```

任务卡应当记录：

```json
{
  "declared_desire": "离开平凡生活",
  "hidden_need": "被明确选择",
  "desired_witness": "他在意但无法接近的人",
  "emotional_proof": "对方在身份变化后重新评价他"
}
```

当写作模型掌握深层需要后，动作、幻想、对白和细节才会围绕同一个情感核心组织起来。

---

## 4. 语域转调模型

所谓“作品的味道”往往不在某一种固定语言里，而在不同语言状态如何切换。

## 4.1 轻松掩饰型

```text
现实困境
→ 人物开玩笑
→ 叙述者继续调侃
→ 出现一个无法被玩笑消化的事实
→ 短句收尾
```

适用功能：

- `expose_character_lack`
- `reveal_hidden_desire`
- `show_consequence`

## 4.2 幻想坠落型

```text
琐碎现实
→ 触发宏大幻想
→ 幻想不断扩张
→ 人物获得想象中的注视
→ 琐碎任务突然打断
```

适用功能：

- `show_compensatory_behavior`
- `setup`
- `expose_character_lack`

## 4.3 延迟悲伤型

```text
别人说出重要信息
→ 人物先关注无关细节
→ 人物继续表现正常
→ 人物离开公共场合
→ 情绪才真正出现
```

适用功能：

- `reveal_hidden_desire`
- `break_trust`
- `show_consequence`
- `payoff`

## 4.4 喜剧转悬念型

```text
人物互相挤兑
→ 对话保持生活化
→ 某人无意说出不该知道的信息
→ 主角短暂迟疑
→ 对话继续，但读者已经警觉
```

适用功能：

- `plant_question`
- `provide_clue`
- `create_information_asymmetry`
- `build_tension`

## 4.5 数据结构

```json
{
  "pattern_id": "fantasy_fall_001",
  "name": "幻想坠落型",
  "register_sequence": [
    "mundane",
    "comic",
    "grand_imagination",
    "emotional_exposure",
    "mundane_undercut"
  ],
  "preferred_scene_functions": [
    "expose_character_lack",
    "show_compensatory_behavior",
    "setup"
  ],
  "constraints": {
    "confirm_supernatural": false,
    "direct_emotion_sentences_max": 1
  }
}
```

---

## 5. 声音配置

在现有叙事任务卡中增加 `voice_profile`、`emotional_subtext`、`register_plan` 和 `prose_constraints`。

```json
{
  "voice_profile": {
    "narrator_distance": 0.35,
    "narrator_empathy": 0.85,
    "narrator_irony": 0.60,
    "emotion_explicitness": 0.25,
    "colloquial_ratio": 0.55,
    "lyrical_ratio": 0.25,
    "expository_ratio": 0.20
  },

  "emotional_subtext": {
    "surface_event": "主人公参加普通校园活动",
    "hidden_need": "希望有人公开选择自己",
    "denied_emotion": "害怕自己无足轻重",
    "mask": "用玩笑和无所谓掩饰",
    "rupture": "有人准确叫出他的名字",
    "residue": "事情结束后仍不敢相信"
  },

  "register_plan": [
    {
      "stage": "mundane",
      "paragraphs": 2
    },
    {
      "stage": "comic",
      "paragraphs": 1
    },
    {
      "stage": "grand_imagination",
      "paragraphs": 3
    },
    {
      "stage": "mundane_undercut",
      "paragraphs": 1
    }
  ],

  "prose_constraints": {
    "direct_emotion_sentences_max": 1,
    "abstract_summary_density_max": 0.15,
    "concrete_detail_density_min": 0.50,
    "paragraph_ending_mode": "quiet_drop"
  }
}
```

数值用于控制相对倾向，不应被理解为客观文学测量。

---

## 6. 句间关系建模

大模型很容易学到以下内容元素：

- 校园；
- 夕阳；
- 漂亮女孩；
- 游戏；
- 自嘲；
- 神秘邀请。

但这些内容同时出现，不等于产生稳定风味。

系统还需要抽取：

```text
上一句完成了什么
→ 下一句为什么转向
→ 情绪在哪一句被抬高
→ 又在哪一句被压回现实
```

每个段落可以增加 `discourse_moves`：

```json
[
  {
    "sequence": 1,
    "text_role": "establish_mundane_fact"
  },
  {
    "sequence": 2,
    "text_role": "add_self_deprecating_interpretation"
  },
  {
    "sequence": 3,
    "text_role": "expand_imagination"
  },
  {
    "sequence": 4,
    "text_role": "reveal_hidden_need_indirectly"
  },
  {
    "sequence": 5,
    "text_role": "undercut_with_mundane_detail"
  }
]
```

这类结构比单纯统计平均句长、形容词数量或关键词频率更接近真实的叙述声音。

---

## 7. 两阶段生成

不要让一次模型调用同时完成情节、人物、节奏和语言风格。

## 7.1 第一阶段：内容草稿

目标：

- 完成场景事件；
- 满足前置条件；
- 实现状态变化；
- 遵守信息边界；
- 保证人物行动和前后连续性。

要求语言保持朴素，不追求最终文风。

建议输出：

```json
{
  "scene_events": [],
  "character_actions": [],
  "dialogue_intents": [],
  "state_delta": {},
  "ending_state": {},
  "plain_draft": ""
}
```

## 7.2 第二阶段：声音实现

输入：

- 内容草稿；
- 情感潜台词；
- 声音配置；
- 语域转调计划；
- 禁止条件；
- 项目原创基准样本。

要求：

- 不改变事件顺序；
- 不增加新设定；
- 不改变信息公开范围；
- 将直接情绪解释改成行为和细节；
- 加入指定的语域转调；
- 让幽默承担掩饰情绪的功能；
- 避免直接命名隐藏情绪。

第二阶段不是普通“润色”，而是依据话语策略重新叙述。

---

## 8. 原创声音基准

模型可以分析叙述特征，但无法替作者决定新作品独有的声音。

人工应先创作或确认一批原创基准样本：

1. 一个校园日常场景；
2. 一段人物独处；
3. 一次轻松对话；
4. 一次异常出现；
5. 一次情感破裂；
6. 一个章节结尾。

每类约 500～1500 字即可。

这些样本构成项目的“声音宪法”，用于：

- 提取声音配置；
- 建立场景类型与声音模式的对应关系；
- 进行生成结果比较；
- 检查不同章节中的声音漂移；
- 避免直接依赖受版权保护作品的原文表达。

---

## 9. 反俗套机制

模型为了寻找青春、伤感或命运感，容易反复使用通用表达。

项目应维护可编辑的反俗套规则：

```json
{
  "banned_cliches": [
    "命运的齿轮",
    "世界突然安静",
    "影子拉得很长",
    "心里某处柔软的地方"
  ],
  "max_generic_metaphors_per_scene": 1,
  "require_character_specific_metaphor": true
}
```

人物专属比喻应来自人物经验。

例如，一个长期修理电器的人，更可能通过线路、信号、接触不良和断电理解关系与记忆；而不是无论什么情绪都使用风、海、星光和夕阳。

反俗套模块不应机械删除所有常见表达，而应检测：

- 单场景密度；
- 相邻章节重复；
- 是否与人物经验有关；
- 是否承担叙事功能；
- 是否可以被更具体的动作或物件替代。

---

## 10. 风格评审

风格评审不应只回答“像不像某部作品”，否则模型会通过专有名词、校园意象和流行文化引用投机。

建议评估：

```json
{
  "narrator_empathy": 0.78,
  "narrator_irony": 0.31,
  "emotion_explicitness": 0.72,
  "register_transition_quality": 0.44,
  "hidden_need_clarity": 0.61,
  "mundane_grand_contrast": 0.55,
  "character_specificity": 0.48,
  "generic_youth_imagery_rate": 0.67
}
```

评审结果应转化为定向修改：

```text
当前文本直接解释人物孤独的句子过多。
保留事件不变，删除情绪结论。
增加一个人物用玩笑掩饰失落的动作。
将宏大想象后的结尾改为琐碎现实打断。
```

---

## 11. 完整架构

```text
Narrative Planner
决定这场为什么存在
        ↓
Emotional Subtext Planner
决定人物真正想要什么、如何掩饰
        ↓
Register Planner
安排日常、幽默、抒情、幻想和悬疑的转调
        ↓
Content Writer
生成事件完整的朴素版本
        ↓
Voice Renderer
按照原创声音配置重新叙述
        ↓
Narrative Critic
检查功能和状态变化
        ↓
Style Critic
检查声音、潜台词、转调和俗套
        ↓
Originality Guard
检查与参考材料的表达重合
        ↓
Human Review
确认方向、关键情绪和不可逆事件
```

---

# 第二部分：大模型与人工作者的职责边界

## 12. 总体原则

这套系统中，大模型最擅长：

```text
批量提取
+ 生成候选
+ 执行明确修改
+ 检查明显偏差
```

人工最应该负责：

```text
决定作品想表达什么
+ 选择哪一种可能性
+ 决定什么时候揭晓
+ 确认不可逆的故事变化
+ 建立原创叙述声音
```

可以概括为：

> 大模型负责扩展搜索空间，人工负责收缩、定向和最终取舍。

---

## 13. 大模型比较擅长的部分

| 环节 | 擅长度 | 说明 |
|---|---:|---|
| 文本切分 | 高 | 能按人物、地点、时间和目标变化切分场景 |
| 事实抽取 | 高 | 谁在场、做了什么、知道什么，通常较稳定 |
| 表层摘要 | 高 | 概括场景事件是成熟能力 |
| 功能候选生成 | 中高 | 能提出多个可能的叙事功能 |
| 标签初标 | 中高 | 在固定标签体系内分类效果较好 |
| 相似功能检索 | 高 | 功能摘要配合结构化过滤适合机器处理 |
| 任务卡展开 | 高 | 能把抽象目标展开成多个可选场景方案 |
| 局部场景生成 | 高 | 单场景人物、动作、对白和氛围控制较强 |
| 显式连续性检查 | 高 | 擅长检查人名、地点、道具、时间和事实冲突 |
| 俗套检测 | 中高 | 能识别常见套话、直接抒情和重复意象 |
| 多版本比较 | 中高 | 在明确指标下能比较候选稿 |
| 定向重写 | 高 | 问题足够具体时，修改能力通常很好 |

## 13.1 事实抽取

事实信息相对客观，适合批量自动处理。

```json
{
  "characters_present": ["主角", "同桌", "班主任"],
  "events": [
    "主角收到陌生短信",
    "同桌否认看见短信",
    "短信随后消失"
  ],
  "knowledge_changes": {
    "主角": ["知道异常可能修改证据"],
    "同桌": []
  }
}
```

每条事实都应保留原文来源：

```json
{
  "claim": "短信随后消失",
  "source_unit_id": "scene_003_02",
  "source_span": {
    "start": 428,
    "end": 501
  },
  "confidence": 0.94
}
```

## 13.2 功能候选

同一个场景可能同时承担：

- 提供线索；
- 提高不安感；
- 暴露主角缺乏信任对象；
- 制造人物与读者的信息差；
- 为下一次异常做铺垫。

模型适合快速提出候选：

```json
{
  "function_candidates": [
    {
      "function": "provide_clue",
      "confidence": 0.82,
      "reason": "短信消失证明异常会修改证据"
    },
    {
      "function": "expose_relationship_asymmetry",
      "confidence": 0.61,
      "reason": "主角向同桌求证，但没有得到信任"
    },
    {
      "function": "confirm_hypothesis",
      "confidence": 0.47,
      "reason": "主角可能因此确认异常真实"
    }
  ]
}
```

模型负责扩展解释空间，人工选择作品真正需要的主功能。

## 13.3 定向重写

模糊要求：

```text
这一段不够有感觉，重新写得更好。
```

模型只能随机调整语言。

明确要求：

```text
保留事件不变。
删除直接说明主角孤独的句子。
让他用一个不合时宜的玩笑掩饰失落。
不要证明短信来自超自然力量。
结尾回到值日生催他关窗的日常动作。
```

后者属于模型的优势区，因为目标、边界和修改范围明确。

## 13.4 持续检查

适合自动检查：

- 人物是否知道不该知道的信息；
- 某个物品是否已经损坏；
- 两个事件的日期是否冲突；
- 最近三章是否连续使用同一种结尾；
- 是否连续多场都在提高紧张度；
- 某个伏笔是否长期没有推进；
- 某种意象是否重复过密；
- 人物是否突然变得主动、亲密或强大。

---

## 14. 最好由人工干预的部分

| 环节 | 人工必要性 | 原因 |
|---|---:|---|
| 确定作品核心命题 | 极高 | 没有唯一正确答案 |
| 选择人物真正的心理缺口 | 极高 | 决定整部作品的情感方向 |
| 确定场景主功能 | 高 | 同一场景存在多种合理解释 |
| 决定信息何时揭晓 | 极高 | 是长篇节奏最重要的权力 |
| 决定伏笔是否回收 | 极高 | 涉及作品结构和主题 |
| 选择不可逆剧情 | 极高 | 会改变大量后续内容 |
| 定义原创叙述声音 | 极高 | 模型倾向平均化和套话化 |
| 判断情绪是否过度解释 | 高 | 需要整体阅读体验 |
| 关键场景定稿 | 极高 | 高潮、告别、背叛等不能只看指标 |
| 判断作品整体效果 | 只能人工 | 无法被稳定量化 |

## 14.1 人物核心缺口

假设主人公总幻想被神秘组织选中，可能有多种解释：

- 想证明自己并不平庸；
- 想逃离家庭；
- 想让喜欢的人后悔忽视自己；
- 想有人无条件选择自己；
- 害怕承担普通人生的责任；
- 用英雄幻想逃避失败。

这些解释都合理，但会生成完全不同的小说。

人工必须决定：

```text
他到底想被谁认可？
为什么一定是这个人？
如果永远得不到，他会变成什么？
```

这属于作品的价值判断，不能交给统计概率。

## 14.2 场景主功能

“主角收到异常短信”，模型可能判断：

```text
主要功能：提供超自然线索
```

作者真正的目的可能是：

```text
主要功能：测试主角是否愿意相信自己
次要功能：暴露他与同桌之间缺乏信任
信息功能：只增加疑问，不提供可靠证据
```

主功能一旦判断错误，后续正文即使完整，也会把重点写偏。

建议：

1. 模型提供三个功能候选；
2. 每个候选给出依据；
3. 人工选择主功能；
4. 选定后锁定；
5. 写作模型不得自行修改。

## 14.3 信息释放时机

大模型倾向尽快回答问题，因为回答会让当前场景显得完整。长篇则需要有意识地不回答。

```text
允许读者发现异常
≠ 允许读者理解异常
≠ 允许主角确认异常
≠ 允许揭示异常来源
```

示例：

| 信息阶段 | 人工确定的位置 |
|---|---|
| 异常首次出现 | 第 2 章 |
| 排除记忆错误 | 第 5 章 |
| 证明异常有客观影响 | 第 7 章 |
| 提出错误解释 | 第 9 章 |
| 推翻错误解释 | 第 13 章 |
| 确认真相的一部分 | 第 16 章 |

节点确定后，模型可以负责填充场景；节点本身应由作者控制。

## 14.4 状态数值校准

让模型自由判断：

```json
{
  "reader_empathy": 0.73,
  "mystery_tension": 0.62
}
```

这些小数看似精确，通常只是有理由的猜测。

MVP 更适合使用离散变化：

```json
{
  "reader_empathy": "+1",
  "mystery_tension": "+2",
  "protagonist_agency": "0",
  "relationship_trust": "-1"
}
```

或者：

```text
明显下降
小幅下降
不变
小幅上升
明显上升
```

人工负责校准关键节点，机器负责检查相邻场景是否符合方向。

## 14.5 关键场景与结尾

以下场景应优先人工定稿：

- 人物首次做出不可逆选择；
- 重大秘密揭晓；
- 人物死亡；
- 背叛与和解；
- 关系确定或破裂；
- 阶段高潮；
- 全书结局；
- 章节最后一个情绪落点。

模型经常在本应结束时继续：

- 解释悬念；
- 总结情绪；
- 补一句哲理；
- 再增加一次反转。

作者应掌握“停在哪里”的权力。

---

## 15. 大模型容易误判的部分

## 15.1 把结果误认为功能

场景中出现人物哭泣，模型可能标记：

```text
功能：表现悲伤
```

但哭泣只是结果，真正功能可能是：

- 让人物第一次停止伪装；
- 让另一个人物发现其弱点；
- 回收此前一直没有说出口的情绪；
- 迫使人物接受一段关系已经结束。

分析时应继续追问：

> 悲伤被表现出来以后，故事发生了什么不可逆变化？

## 15.2 过度主题化

模型容易把普通细节都解释成主题象征。

系统需要允许：

```json
{
  "narrative_significance": "low",
  "role": "environmental_detail"
}
```

不是每个物件都有深层含义，也不是每句话都必须推进主题。

## 15.3 误认为复杂一定更好

模型容易同时加入：

```text
建立人物
+ 推进关系
+ 提供线索
+ 埋设伏笔
+ 升级冲突
+ 暗示主题
+ 制造反转
```

结果每个场景都很用力，长篇失去呼吸。

人工应限制：

- 一个主功能；
- 最多三个次功能；
- 日常缓冲场景可以只有一个功能；
- 允许只用于陪伴、休息和展示生活的场景存在。

## 15.4 无法可靠判断何时停笔

模型倾向于完成和闭合，而长篇经常需要停在：

- 情绪刚刚出现但尚未解释时；
- 人物意识到问题但尚未行动时；
- 线索被看见但尚未理解时；
- 对话结束而潜台词仍未解决时。

章节结尾和关键场景落点应进入人工审核。

---

## 16. 推荐的人机协作流程

```text
人工
确定卷级目标、人物缺口和核心秘密
    ↓
模型
拆解已有材料，提出章节功能候选
    ↓
人工
确认章节主功能和信息释放节点
    ↓
模型
生成多个场景计划
    ↓
人工
选择计划，锁定不可逆事件
    ↓
模型
生成多个正文版本
    ↓
模型
检查连续性、功能偏差、声音漂移和套话
    ↓
人工
选择版本，处理关键情绪与结尾
    ↓
模型
执行定向修改
    ↓
人工
最终确认，并更新长篇规划
```

---

## 17. 三级审核机制

## 17.1 自动通过

适合客观、低风险内容：

- 人物和地点抽取；
- 时间顺序；
- 显式事件；
- 相邻场景关系；
- 拼写和格式；
- 明确设定冲突；
- Embedding 生成；
- 候选召回。

## 17.2 模型提出、人工抽查

适合有一定主观性的内容：

- 场景切分；
- 次要叙事功能；
- 情绪变化方向；
- 叙述语域；
- 俗套检测；
- 节奏异常；
- 相似场景排名；
- 状态变化幅度。

## 17.3 必须人工确认

适合高影响、不可逆内容：

- 人物核心缺口；
- 章节主功能；
- 重大秘密；
- 伏笔与回收位置；
- 人物死亡、背叛和关系确定；
- 真相揭晓；
- 高潮解决方式；
- 作品结局；
- 原创叙述声音。

---

## 18. 审核数据结构

模型推断不应直接成为已确认事实。

```json
{
  "value": "expose_character_lack",
  "source": "llm_analysis",
  "confidence": 0.78,
  "review_status": "pending",
  "reviewed_by": null,
  "alternatives": [
    "plant_question",
    "show_compensatory_behavior"
  ]
}
```

审核状态：

| 状态 | 含义 |
|---|---|
| `pending` | 等待审核 |
| `auto_accepted` | 符合低风险自动接受规则 |
| `approved` | 人工确认 |
| `rejected` | 人工否决 |
| `locked` | 已锁定，后续生成器不得修改 |

以下字段应支持 `locked`：

- `primary_function`
- `information_policy`
- `hidden_need`
- `payoff_target`
- `irreversible_event`
- `ending_state`
- `voice_profile`

---

## 19. 数据库建议

在叙事功能模型基础上增加以下表。

## 19.1 `voice_profiles`

```sql
CREATE TABLE voice_profiles (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name VARCHAR(128) NOT NULL,
    description TEXT,
    narrator_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    register_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    prose_constraints JSONB NOT NULL DEFAULT '{}'::jsonb,
    cliche_rules JSONB NOT NULL DEFAULT '{}'::jsonb,
    review_status VARCHAR(24) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

## 19.2 `register_patterns`

```sql
CREATE TABLE register_patterns (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name VARCHAR(128) NOT NULL,
    register_sequence JSONB NOT NULL,
    preferred_functions JSONB NOT NULL DEFAULT '[]'::jsonb,
    constraints JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

## 19.3 `style_reference_samples`

仅保存用户拥有权利或自行创作的原创基准样本。

```sql
CREATE TABLE style_reference_samples (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    voice_profile_id UUID REFERENCES voice_profiles(id) ON DELETE SET NULL,
    scene_type VARCHAR(64),
    content TEXT NOT NULL,
    feature_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_type VARCHAR(32) NOT NULL DEFAULT 'user_original',
    approved BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

## 19.4 `generation_reviews`

```sql
CREATE TABLE generation_reviews (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    narrative_unit_id UUID REFERENCES narrative_units(id) ON DELETE CASCADE,
    review_type VARCHAR(32) NOT NULL,
    scores JSONB NOT NULL DEFAULT '{}'::jsonb,
    violations JSONB NOT NULL DEFAULT '[]'::jsonb,
    suggestions JSONB NOT NULL DEFAULT '[]'::jsonb,
    review_status VARCHAR(24) NOT NULL DEFAULT 'pending',
    reviewed_by VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## 20. API 草案

```text
POST   /api/projects/{project_id}/voice-profiles
GET    /api/projects/{project_id}/voice-profiles
PATCH  /api/projects/{project_id}/voice-profiles/{profile_id}

POST   /api/projects/{project_id}/register-patterns
GET    /api/projects/{project_id}/register-patterns

POST   /api/projects/{project_id}/style-samples
GET    /api/projects/{project_id}/style-samples
PATCH  /api/projects/{project_id}/style-samples/{sample_id}/approve

POST   /api/projects/{project_id}/generation/content-draft
POST   /api/projects/{project_id}/generation/render-voice
POST   /api/projects/{project_id}/generation/review-style
POST   /api/projects/{project_id}/generation/rewrite

GET    /api/projects/{project_id}/reviews
PATCH  /api/projects/{project_id}/reviews/{review_id}
POST   /api/projects/{project_id}/reviews/{review_id}/lock
```

---

## 21. 最经济的人工投入

人工不需要逐句修改，也不需要审核每个 JSON 字段。精力应集中在三个位置。

## 21.1 写作前

确认：

- 这一场为什么存在；
- 人物真正需要什么；
- 哪些信息不能泄露；
- 这一场是否包含不可逆变化。

## 21.2 写作后

判断：

- 情感是否可信；
- 人物是否在解释自己；
- 叙述者立场是否稳定；
- 语域转调是否自然；
- 结尾是否应该停在这里。

## 21.3 每 3～5 章

检查：

- 节奏曲线；
- 人物弧线；
- 伏笔距离；
- 信息释放速度；
- 声音漂移；
- 场景功能重复；
- 高强度场景密度。

可将大部分分析、检索、候选生成和检查交给模型，把人工投入集中在方向决策、关键情绪和不可逆事件上。

---

## 22. MVP 实施顺序

### 阶段一：声音配置

1. 增加 `voice_profiles`。
2. 增加情感潜台词字段。
3. 在叙事任务卡中加入声音配置。
4. 允许人工锁定核心字段。

### 阶段二：语域转调

1. 增加 `register_patterns`。
2. 实现四种基础转调模式。
3. 为场景计划指定转调模式。
4. 检查实际段落是否符合计划顺序。

### 阶段三：两阶段生成

1. 分离内容草稿与声音实现。
2. 声音实现阶段禁止修改事实和信息边界。
3. 保存两个版本以便对照。
4. 支持局部定向重写。

### 阶段四：原创基准与风格评审

1. 增加原创样本库。
2. 提取样本的声音特征。
3. 实现风格评审指标。
4. 增加反俗套规则。
5. 增加原创性重合检查。

### 阶段五：人机审核工作流

1. 增加审核状态。
2. 建立自动通过、人工抽查和强制确认规则。
3. 支持关键字段锁定。
4. 支持每 3～5 章生成一次长篇审核报告。

---

## 23. 总结

叙事功能正确，只能保证小说“写得通”。

要形成稳定的原创风味，还需要：

```text
人物不能直接承认自己的深层需要
+ 叙述者同时保持适度调侃与真实共情
+ 日常、幽默、抒情和悬疑按照计划转调
+ 宏大想象最终接受琐碎现实的校正
+ 情绪通过行为、物件和停顿泄露
+ 项目拥有自己的原创声音基准
```

大模型适合：

```text
提取、扩展、生成候选、检查和执行定向修改
```

人工作者必须掌握：

```text
作品命题、人物缺口、主功能、信息时机、
不可逆事件、关键情绪、章节落点和最终声音
```

理想的人机关系不是让模型替作者做决定，而是让模型降低分析和试错成本，使作者可以把精力集中在真正不可替代的判断上。
