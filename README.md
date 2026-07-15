# AI 小说协作助手 · AINovelTool

> 一个面向**都市幻想长篇小说**的 AI 协作助手。通过
> "设定库 → RAG 检索 → 上下文组装 → AI 生成 → 滚动摘要回写" 的闭环，解决**卡文**与
> **创作速度慢**两大痛点；并在同一套检索底座上扩展**文学引用**与**成语推荐**。
>
> 统一技术主线：**retrieval-grounded generation —— 用检索约束生成，抑制 LLM 幻觉。**

许可证：**MIT**。本项目从零自建，仅借鉴开源项目
[MuMuAINovel](https://github.com/xiamuceer-j/MuMuAINovel) 的功能思路与架构理念，**未复制其源代码**。

---

## 为什么是这个设计

朴素做法是把所有设定、人物、世界观一股脑塞进 prompt。对一部多人物、长连载的小说，
这会让 token 飙升、上下文被挤占、生成质量下降。

本项目用 **RAG 检索层**只取**当前场景真正相关**的设定喂给模型 —— prompt 更小、更快、
更便宜、更聚焦。同一套 `embedding + pgvector` 底座被三个检索源复用（设定 / 文学 / 成语），
即**多源混合检索**。

## 核心闭环与两种生成模式

```
设定库 → 向量检索(RAG) → 上下文组装 → AI 生成 → 滚动摘要回写
```

| 模式 | 解决痛点 | 说明 |
| --- | --- | --- |
| **续写模式** | 写得慢 | 基于当前章节 + 自动检索到的相关设定，SSE 流式续写下一段 |
| **破壁模式** | 卡文 | 给定剧情状态，一次生成 N 个走向不同的后续分支 |

## v1.1 多源检索亮点

- **文学引用库（Feature A）**：让角色像有文化的人一样**引用、谈论真实文学**。分为两个子库：
  **金句库**（原文名句，仅公有领域作品，且译文须译者也过保护期）与**素材库**（写作背景 /
  主题解读 / 内容概括等事实性知识，可含版权期内作品——事实不受版权保护，作者可引用其
  情节制造氛围，系统结构上无法输出其原文）。双重守卫：入库时强制 + 检索时兜底，从源头
  杜绝侵权与幻觉。作品另按体裁/主题分类（诗歌/戏剧/散文/志怪 + 爱情/战争/现实/哲学/成长文学）。
- **成语推荐（Feature B）**：输入画面描述，**向量召回候选成语**，再由 LLM 从**召回列表内**
  精选并解释 —— LLM 不能凭空编造不存在的成语。

## 技术栈

| 层 | 选型 | 理由 |
| --- | --- | --- |
| 后端 | FastAPI | 异步、生成用 **SSE 流式输出** |
| 数据库 | PostgreSQL + pgvector | 一个库同时承载关系数据与向量检索，省去独立向量库的同步 |
| Embedding | bge-m3 / bge-small-zh | 中文小说语义检索效果优于多语 MiniLM（可切换 local / API 后端）|
| LLM | OpenAI 兼容接口 + provider 抽象层 | 可换模型 |
| 前端 | React（从简，后置）| 当前可直接用 Swagger UI 操作全部接口 |

## 快速开始

### 方式一：Docker（推荐）

```bash
cp backend/.env.example backend/.env   # 填入 LLM_API_KEY 等
docker compose up --build
# 数据库 schema 首次启动自动执行；API 在 http://localhost:8000/docs
```

### 方式二：本地

```bash
# 1. 起一个带 pgvector 的 Postgres，并执行建表脚本
psql "$DATABASE_URL" -f backend/scripts/init_pgvector.sql

# 2. 安装依赖并启动
cd backend
python -m venv .venv && source .venv/Scripts/activate   # Windows Git Bash
pip install -r requirements.txt
cp .env.example .env                                     # 填写配置
uvicorn app.main:app --reload

# 3. （可选）灌入 v1.1 示例数据
python scripts/seed_idioms.py
python scripts/seed_literary.py
```

## 评测（eval harness）

项目自带可复现的小型评测，用数据说话而非只调 API。详见
[backend/eval/README.md](backend/eval/README.md)。

| 指标 | 脚本 | 实测结果 |
| --- | --- | --- |
| 检索召回率 Recall@k / 平均块数 / 延迟 | `eval/run_retrieval_eval.py` | **Recall@6 = 1.000**（30 例标注集，16 项设定库，均延迟 256ms）|
| Token/字数：全量塞 vs RAG 选择 | `eval/run_token_eval.py` | **上下文压缩 62.5%**（top-k 固定为 6；库越大压缩率越高）|
| 生成性能：TTFT / 流式吞吐 / 并发 | `eval/run_perf_eval.py` | 检索 P95 161ms · SSE 首 token P50 3.1s · 61 events/s |
| 成语幻觉率（推荐词条不在权威词表的比例）| `eval/run_idiom_hallucination_eval.py` | **检索约束 0.0% vs 纯 LLM baseline 20.0%**（20 场景，成语库 ~1 万条，真值集 31k 词典 ∪ 库）|

> 测试环境：Windows 11 / CPU 推理（bge-m3 本地）/ DeepSeek deepseek-chat / pgvector HNSW。
> 标注集：[eval/datasets/retrieval_recall.v1.json](backend/eval/datasets/retrieval_recall.v1.json)，
> 设定库种子：[eval/seed_eval_settings.py](backend/eval/seed_eval_settings.py)，可一键复现。

## 目录结构

```
AINovelTool/
├── backend/
│   ├── app/
│   │   ├── api/         # 路由：projects / characters / world / chapters / retrieve / generate / literary / idioms
│   │   ├── models/      # SQLAlchemy 模型（含 pgvector 向量列）
│   │   ├── schemas/     # Pydantic 请求/响应模型
│   │   ├── services/    # 业务逻辑：retrieval / indexing / generation / summary / literary / idiom
│   │   ├── core/        # 配置、LLM provider 抽象、embedding 抽象
│   │   ├── db.py
│   │   └── main.py
│   ├── scripts/         # init_pgvector.sql + 种子数据
│   ├── eval/            # eval harness + 标注数据
│   └── requirements.txt
├── frontend/            # 乌鸦像写字台 React 前端（Vite + SSE）
├── docker-compose.yml   # postgres(pgvector) + api
├── LICENSE              # MIT
└── README.md
```

## 数据模型（关键表）

`projects` · `characters` · `relationships` · `world_settings` · `chapters` ·
`foreshadowing` · `setting_chunks`(向量) · `rolling_summary` ·
`literary_works` · `literary_knowledge`(向量) · `idioms`(向量)

详见 [backend/scripts/init_pgvector.sql](backend/scripts/init_pgvector.sql)。

## 路线图

- [x] 设定库 CRUD + 建表
- [x] embedding + pgvector 检索 + eval harness 骨架
- [x] 生成（续写 + 破壁）+ 滚动摘要
- [x] v1.1：文学引用库 + 成语推荐（复用检索底座）
- [x] 薄前端（React + SSE 实时渲染，见 frontend/）
- [x] 标注评测集（30 例）+ 召回率 / token 压缩 / 生成性能实测数字
- [x] 成语库扩至 ~1 万条（chinese-xinhua, MIT）、文学库 15 部公有领域作品
- [x] 幻觉拦截率 A/B：检索约束 0.0% vs 纯 LLM baseline 20.0%

---

本项目用于个人学习与作品集展示，借鉴同类开源项目功能思路，核心实现独立完成。
