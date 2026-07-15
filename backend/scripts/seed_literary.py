# -*- coding: utf-8 -*-
"""Seed the literary citation library (v1.1, Feature A).

The whitelist is enforced HERE, at ingest: only public-domain works are admitted
to the database. Retrieval and generation then physically cannot surface a
copyrighted or fabricated work — the protection lives in the data, not a prompt.

Idempotent: works already present (title + author) are skipped.

    python scripts/seed_literary.py
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.embedding import embed_texts
from app.db import AsyncSessionLocal
from app.models.literary import LiteraryKnowledge, LiteraryWork

# Public-domain works only (authors long deceased). Curate freely.
WORKS = [
    {
        "title": "草叶集",
        "author": "沃尔特·惠特曼",
        "era": "19世纪",
        "school": "浪漫主义",
        "themes": ["自我", "自然", "生命力"],
        "knowledge": [
            ("作者背景", "惠特曼以自由体诗革新美国诗歌，讴歌个体与民主。"),
            ("主题解读", "《草叶集》以草叶象征平凡而蓬勃的生命，礼赞自我与众生平等。"),
            ("公认名句", "我辽阔博大，我包罗万象。"),
        ],
    },
    {
        "title": "杂忆与杂记",
        "author": "鲁迅",
        "era": "20世纪初",
        "school": "现实主义",
        "themes": ["国民性", "批判", "记忆"],
        "knowledge": [
            ("作者背景", "鲁迅以冷峻笔触剖析国民性，是中国现代文学奠基者之一。"),
            ("主题解读", "在回忆与杂感之间，鲁迅把个人经验上升为对时代的诊断。"),
        ],
    },
    {
        "title": "呐喊",
        "author": "鲁迅",
        "era": "20世纪初",
        "school": "现实主义",
        "themes": ["觉醒", "国民性", "希望"],
        "knowledge": [
            ("主题解读", "《呐喊》为沉睡的时代发声，在铁屋子里喊出第一声，唤醒的痛苦好过麻木的安眠。"),
            ("公认名句", "其实地上本没有路，走的人多了，也便成了路。"),
            ("典故", "「铁屋子」比喻出自《呐喊》自序：万难破毁的铁屋里，熟睡的人们将被闷死，喊醒少数人是否更残酷？"),
        ],
    },
    {
        "title": "傲慢与偏见",
        "author": "简·奥斯汀",
        "era": "19世纪初",
        "school": "现实主义",
        "themes": ["爱情", "婚姻", "阶层", "偏见"],
        "knowledge": [
            ("作者背景", "奥斯汀终身未婚，深居英国乡间，却以细腻的反讽写透了婚恋与人性——爱情可以靠观察与想象抵达。"),
            ("主题解读", "傲慢让别人无法来爱我，偏见让我无法去爱别人；达西与伊丽莎白的和解是两次自我修正的相遇。"),
            ("公认名句", "凡是有钱的单身汉，总想娶位太太，这已经成了一条举世公认的真理。"),
        ],
    },
    {
        "title": "红楼梦",
        "author": "曹雪芹",
        "era": "清代",
        "school": "古典小说",
        "themes": ["家族兴衰", "爱情", "幻灭", "命运"],
        "knowledge": [
            ("作者背景", "曹雪芹出身江宁织造世家，家道中落后于贫困中著书，「披阅十载，增删五次」。"),
            ("主题解读", "以宝黛爱情为线，写尽钟鸣鼎食之家的繁华与倾颓，真事隐去、假语存焉。"),
            ("公认名句", "假作真时真亦假，无为有处有还无。"),
        ],
    },
    {
        "title": "三国演义",
        "author": "罗贯中",
        "era": "元末明初",
        "school": "古典小说",
        "themes": ["权谋", "忠义", "天下大势"],
        "knowledge": [
            ("主题解读", "在正史与民间讲史之间，把权谋与忠义写成中国人共同的性格词典。"),
            ("公认名句", "话说天下大势，分久必合，合久必分。"),
        ],
    },
    {
        "title": "西游记",
        "author": "吴承恩",
        "era": "明代",
        "school": "神魔小说",
        "themes": ["修行", "反抗", "妖魔", "取经"],
        "knowledge": [
            ("主题解读", "取经是一场心性的修行，八十一难降的都是心魔；孙悟空由反抗到成佛，锋芒收于紧箍。"),
            ("典故", "大闹天宫：石猴不受天庭秩序约束，「皇帝轮流做，明年到我家」，是全书最恣意的反抗篇章。"),
        ],
    },
    {
        "title": "水浒传",
        "author": "施耐庵",
        "era": "元末明初",
        "school": "古典小说",
        "themes": ["江湖", "官逼民反", "义气"],
        "knowledge": [
            ("主题解读", "一百单八将逼上梁山，写的是秩序崩坏处江湖如何自组织——义气既是纽带也是悲剧根源。"),
        ],
    },
    {
        "title": "聊斋志异",
        "author": "蒲松龄",
        "era": "清代",
        "school": "志怪小说",
        "themes": ["鬼狐", "人妖之恋", "讽喻"],
        "knowledge": [
            ("作者背景", "蒲松龄屡试不第，设茶棚收集四方异闻，穷四十年写成孤愤之书。"),
            ("主题解读", "借鬼狐写人间，妖有情而人无情；超自然是照见世情的镜子——都市怪谈的古典源头。"),
            ("公认评价", "郭沫若题联评价：写鬼写妖高人一等，刺贪刺虐入骨三分。"),
        ],
    },
    {
        "title": "山海经",
        "author": "先秦佚名",
        "era": "先秦",
        "school": "上古志怪",
        "themes": ["神话", "异兽", "地理"],
        "knowledge": [
            ("主题解读", "中国神话与异兽设定的总源头，后世志怪、仙侠、都市幻想的世界观多由此取材。"),
            ("典故", "精卫填海：炎帝之女溺于东海，化为精卫鸟，衔西山木石以填沧海——以微小之躯对抗无穷之事。"),
            ("典故", "夸父逐日：夸父与日逐走，道渴而死，弃其杖化为邓林。"),
        ],
    },
    {
        "title": "双城记",
        "author": "查尔斯·狄更斯",
        "era": "19世纪",
        "school": "现实主义",
        "themes": ["革命", "牺牲", "救赎"],
        "knowledge": [
            ("作者背景", "狄更斯以连载小说为生民立传，善写大时代里小人物的挣扎与光辉。"),
            ("公认名句", "这是最好的时代，这是最坏的时代。"),
        ],
    },
    {
        "title": "悲惨世界",
        "author": "维克多·雨果",
        "era": "19世纪",
        "school": "浪漫主义",
        "themes": ["救赎", "苦难", "良知", "革命"],
        "knowledge": [
            ("作者背景", "雨果流亡期间完成此书，自言写给「一切苦难中的人」。"),
            ("主题解读", "冉阿让的一生是良知对法律、宽恕对惩罚的漫长胜利；主教的银烛台是全书善意的火种。"),
        ],
    },
    {
        "title": "简·爱",
        "author": "夏洛蒂·勃朗特",
        "era": "19世纪",
        "school": "现实主义",
        "themes": ["尊严", "爱情", "独立"],
        "knowledge": [
            ("主题解读", "贫穷、卑微、不美，但灵魂平等——简·爱把爱情建立在人格对等之上，是女性叙事的里程碑。"),
            ("公认名句", "你以为我贫穷、相貌平平就没有感情吗？我的灵魂跟你一样，我的心也跟你完全一样。"),
        ],
    },
    {
        "title": "李太白集",
        "author": "李白",
        "era": "盛唐",
        "school": "浪漫主义诗歌",
        "themes": ["豪放", "饮酒", "求仙", "友情"],
        "knowledge": [
            ("作者背景", "李白仗剑去国、辞亲远游，诗风豪放飘逸，人称谪仙人。"),
            ("公认名句", "天生我材必有用，千金散尽还复来。（《将进酒》）"),
            ("公认名句", "抽刀断水水更流，举杯消愁愁更愁。（《宣州谢朓楼饯别校书叔云》）"),
        ],
    },
    {
        "title": "东坡乐府",
        "author": "苏轼",
        "era": "北宋",
        "school": "豪放词",
        "themes": ["旷达", "离别", "人生"],
        "knowledge": [
            ("作者背景", "苏轼一生三起三落，愈贬愈旷达，把人生的不如意都写成了豁然。"),
            ("公认名句", "人有悲欢离合，月有阴晴圆缺，此事古难全。（《水调歌头》）"),
            ("公认名句", "回首向来萧瑟处，归去，也无风雨也无晴。（《定风波》）"),
        ],
    },
]


async def main() -> None:
    async with AsyncSessionLocal() as db:
        existing = {
            (title, author)
            for title, author in (
                await db.execute(select(LiteraryWork.title, LiteraryWork.author))
            ).all()
        }
        added = 0
        for w in WORKS:
            if not w.get("is_public_domain", True):
                continue  # whitelist guard
            if (w["title"], w["author"]) in existing:
                continue
            work = LiteraryWork(
                title=w["title"],
                author=w["author"],
                era=w.get("era"),
                school=w.get("school"),
                themes=w.get("themes", []),
                is_public_domain=True,
            )
            db.add(work)
            await db.flush()

            texts = [content for _kind, content in w["knowledge"]]
            vectors = await embed_texts(texts)
            for (kind, content), vec in zip(w["knowledge"], vectors):
                db.add(
                    LiteraryKnowledge(
                        work_id=work.id,
                        knowledge_type=kind,
                        content=content,
                        embedding=vec,
                    )
                )
            added += 1
        await db.commit()
    print(f"literary library seeded ({added} new works, {len(WORKS)} defined).")


if __name__ == "__main__":
    asyncio.run(main())
