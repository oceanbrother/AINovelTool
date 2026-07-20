# 乌鸦像写字台 · AINovelTool

**中文** | [English](README.en.md)

> 一个面向**都市幻想长篇小说**的 AI 协作助手。通过
> "设定库 → RAG 检索 → 上下文组装 → AI 生成 → 滚动摘要回写" 的闭环，解决**卡文**与
> **创作速度慢**两大痛点；并在同一套检索底座上扩展**文学引用**与**成语推荐**。
>
> 统一技术主线：**retrieval-grounded generation —— 用检索约束生成，抑制 LLM 幻觉。**

许可证：**MIT**。本项目从零自建，仅借鉴开源项目
[MuMuAINovel](https://github.com/xiamuceer-j/MuMuAINovel) 的功能思路与架构理念，**未复制其源代码**。

![乌鸦像写字台 — 写作界面](docs/img/writing-desk.png)

*夜色外框 + 稿纸编辑区 + 灵感侧栏（线索 / 破壁 / 找词 / 引经 / 伏笔）。正文由 SSE 流式生成，
角色口癖、地点、规则全部来自检索命中的设定库。*

---

## 核心数字

| 指标 | 结果 |
| --- | --- |
| 成语推荐幻觉率（A/B 对照） | **检索约束 0.0% vs 纯 LLM 20.0%** |
| 检索召回率 | **Recall@6 = 1.000**（30 例标注集） |
| RAG 上下文压缩 | **62.5%**（vs 全量塞 prompt） |
| 10 并发检索 P95 | **962→724ms**，劣化 5.8×→**3.3×**（微批处理 + LRU 缓存） |
| 检索延迟 / SSE 吞吐 | P95 180ms / 61 events/s |
| 感知等待优化 | 检索线索 ~0.8s 先亮，早于首 token 2.6~3.3s |
| 文风模仿盲评 | **7 胜 1 平 0 负**（n=8，LLM 裁判正反双序一致才计胜） |
| 仿写自检环 | 裁判反馈一轮迭代 style **2→6**；复述门 n-gram 重叠 0.0 |
| 裁判校准 | 真原文 vs 仿写盲测分辨率 **5/6**——裁判判断可信 |

## 架构

```mermaid
flowchart LR
    subgraph 检索底座["embedding(bge-m3) + pgvector"]
        S[设定库<br/>角色/世界观/伏笔]
        L[文学库<br/>素材库+金句库]
        I[成语库<br/>~1万条]
    end
    W[写作界面<br/>React + SSE] -->|场景/画面/主题| R{多源检索}
    R --> S & L & I
    R -->|top-k 相关块| C[上下文组装<br/>滚动摘要+近期正文+检索块]
    C --> G[LLM 生成<br/>OpenAI 兼容 provider]
    G -->|SSE: clues → tokens| W
    G -->|摘要回写| C
```

## 为什么是这个设计

朴素做法是把所有设定、人物、世界观一股脑塞进 prompt。对一部多人物、长连载的小说，
这会让 token 飙升、上下文被挤占、生成质量下降。

本项目用 **RAG 检索层**只取**当前场景真正相关**的设定喂给模型 —— prompt 更小、更快、
更便宜、更聚焦。同一套 `embedding + pgvector` 底座被三个检索源复用（设定 / 文学 / 成语），
即**多源混合检索**。

## 核心闭环与两种生成模式

| 模式 | 解决痛点 | 说明 |
| --- | --- | --- |
| **续写模式** | 写得慢 | 当前章节 + 检索到的设定，SSE 流式续写；检索线索先亮（~0.8s），正文随后流入 |
| **破壁模式** | 卡文 | 给定剧情状态，一次生成 N 个走向不同的分支卡，响应携带检索依据 |

配套：**伏笔管理**（埋设章/回收章全程跟踪，未回收伏笔自动进入检索，续写时被"想起"）、
**滚动摘要**（控制长篇上下文）、**文风模仿**（文风样本入库，生成时双路检索——
事实与文风分开召回，样本紧邻生成点注入，只借语感不复述内容）。

## v1.1 多源检索

- **文学引用库**：让角色像有文化的人一样引用、谈论真实文学。分两个子库——
  **金句库**（原文名句，仅公有领域作品，译文须译者也过保护期）与**素材库**（写作背景 /
  主题解读 / 内容概括等事实性知识，可含版权期内作品：事实不受版权保护，作者可引用其情节
  制造氛围，系统结构上无法输出其原文）。双重守卫：入库时强制 + 检索 SQL 兜底。
  作品按体裁/主题分类（诗歌/戏剧/散文/志怪 + 爱情/战争/现实/哲学/成长文学）。
- **成语推荐**：画面描述 → 向量召回候选 → LLM 仅从召回列表内精选并解释，
  不可能编造不存在的成语（A/B 实测 0.0% vs 20.0%）。

## 技术栈

| 层 | 选型 | 理由 |
| --- | --- | --- |
| 后端 | FastAPI | 异步、SSE 流式输出 |
| 数据库 | PostgreSQL + pgvector | 一个库承载关系数据与向量检索，免去独立向量库同步 |
| Embedding | bge-m3（本地）/ OpenAI 兼容 API | 中文语义检索优于多语 MiniLM；微批处理 + LRU 缓存解决 CPU 并发瓶颈 |
| LLM | OpenAI 兼容 provider 抽象 | 默认 DeepSeek，可切任意兼容服务 |
| 前端 | React + Vite，手写 CSS | 「乌鸦像写字台」：夜墨外框 + 冷调稿纸 + 朱砂批注红 |

## 快速开始

### 方式一：Docker（推荐）

```bash
cp backend/.env.example backend/.env   # 填入 LLM_API_KEY 等
docker compose up --build
# 数据库 schema 首次启动自动执行；API 在 http://localhost:8000/docs
```

### 方式二：本地（推荐日常开发：`.\dev.ps1` 一键三终端）

```powershell
# 手动启动 Docker Desktop 后：
.\dev.ps1   # 自动检查 Docker，分三个终端拉起 数据库/后端/前端
```

或手动逐个启动：

```bash
# 1. 起一个带 pgvector 的 Postgres（宿主机端口 5433），执行建表脚本
psql "$DATABASE_URL" -f backend/scripts/init_pgvector.sql

# 2. 后端
cd backend
python -m venv .venv && source .venv/Scripts/activate   # Windows Git Bash
pip install -r requirements.txt
cp .env.example .env                                     # 填写配置
uvicorn app.main:app --reload

# 3. 种子数据（成语 ~1 万条需先下载 chinese-xinhua 的 idiom.json）
python scripts/seed_literary.py
python scripts/import_idioms.py --source path/to/idiom.json

# 4. 前端
cd ../frontend && npm install && npm run dev   # http://localhost:5173
```

## 评测（eval harness）

所有数字可复现，详见 [backend/eval/README.md](backend/eval/README.md)。

| 指标 | 脚本 | 实测结果 |
| --- | --- | --- |
| 检索召回率 | `eval/run_retrieval_eval.py` | **Recall@6 = 1.000**（30 例标注集，均延迟 256ms）|
| Token 压缩 | `eval/run_token_eval.py` | **62.5%**（top-k=6 固定；库越大压缩率越高）|
| 生成性能 | `eval/run_perf_eval.py` | 冷查询 P95 180ms · 缓存命中 ~50ms · 首 token P50 3.1s · 61 events/s |
| 并发优化前后 | `eval/run_perf_eval.py` | 10 并发 P95 962→724ms，劣化 5.8×→3.3× |
| 成语幻觉率 A/B | `eval/run_idiom_hallucination_eval.py` | **0.0% vs 20.0%**（20 场景，真值集 = 31k 词典 ∪ 精选库）|
| 文风模仿盲评 | `eval/run_style_eval.py` | 带样本 vs 无样本 **7 胜 1 平 0 负**（n=8，裁判正反双序一致才计胜，消除位置偏差）|
| 裁判校准 | `eval/run_judge_calibration.py` | 真原文 vs 仿写盲测，裁判分辨率 **5/6**（裁判可信的前提验证）|

> 环境：Windows 11 / CPU 推理（bge-m3）/ DeepSeek deepseek-chat / pgvector HNSW。

## 数据模型（关键表）

`projects` · `characters` · `relationships` · `world_settings` · `chapters` ·
`foreshadowing` · `setting_chunks`(向量) · `rolling_summary` ·
`literary_works` · `literary_knowledge`(向量) · `idioms`(向量)

建表 SQL：[backend/scripts/init_pgvector.sql](backend/scripts/init_pgvector.sql)。

## 路线图

- [x] 核心闭环：设定库 CRUD → 检索 → 续写/破壁 → 滚动摘要
- [x] v1.1 多源检索：文学引用（素材库/金句库）+ 成语推荐
- [x] 前端「乌鸦像写字台」（React + SSE 实时渲染）
- [x] eval harness：召回率 / token 压缩 / 生成性能 / 幻觉率 A/B 全部量化
- [x] 并发瓶颈优化（微批处理 + 缓存）· 伏笔系统 · 检索线索先行
- [x] 文风模仿：样本入库 + 双路检索注入，盲评 7/8 胜出
- [x] 私有文风管线：epub 摄取（数据永不入库房）+ 仿写自检环
      （异模型裁判 + AI 味评分 + n-gram 复述门 + 反馈重写）+ 裁判校准 5/6

---

本项目用于个人学习与作品集展示，借鉴同类开源项目功能思路，核心实现独立完成。
