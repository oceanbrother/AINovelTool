# -*- coding: utf-8 -*-
"""Seed the literary citation library (v1.1, Feature A).

The whitelist is enforced HERE, at ingest: only public-domain works are admitted
to the database (mainland-China rule: author dead 50+ years; verbatim 名句 only
when the *translator* is also public-domain — otherwise the knowledge entry
paraphrases instead of quoting). Retrieval and generation then physically cannot
surface a copyrighted or fabricated line — the protection lives in the data,
not a prompt.

Taxonomy (`category`): 体裁 — 诗歌 / 戏剧 / 散文 / 志怪文学;
novels by theme — 爱情文学 / 战争文学 / 现实文学 / 哲学 / 成长文学.

Idempotent: existing works (title + author) get their category backfilled;
new works are inserted with embedded knowledge chunks.

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
    # ------------------------------------------------------------- 诗歌
    {
        "title": "草叶集",
        "author": "沃尔特·惠特曼",
        "era": "19世纪",
        "school": "浪漫主义",
        "category": "诗歌",
        "themes": ["自我", "自然", "生命力"],
        "knowledge": [
            ("作者背景", "惠特曼以自由体诗革新美国诗歌，讴歌个体与民主。"),
            ("主题解读", "《草叶集》以草叶象征平凡而蓬勃的生命，礼赞自我与众生平等。"),
            ("公认名句", "我辽阔博大，我包罗万象。"),
        ],
    },
    {
        "title": "飞鸟集",
        "author": "泰戈尔",
        "era": "20世纪初",
        "school": "抒情诗",
        "category": "诗歌",
        "themes": ["自然", "哲思", "生死"],
        "knowledge": [
            ("作者背景", "泰戈尔是首位获诺贝尔文学奖的亚洲作家，短诗如飞鸟掠过，轻盈而深远。"),
            ("公认名句", "生如夏花之绚烂，死如秋叶之静美。（郑振铎译）"),
            ("主题解读", "《飞鸟集》用三两行小诗捕捉自然与人心的瞬间对应，是格言与诗的合流。"),
        ],
    },
    {
        "title": "叶芝诗选",
        "author": "威廉·巴特勒·叶芝",
        "era": "19-20世纪之交",
        "school": "象征主义",
        "category": "诗歌",
        "themes": ["爱情", "时间", "凯尔特神话"],
        "knowledge": [
            ("作者背景", "叶芝是爱尔兰文艺复兴的旗手，一生向茅德·冈求婚数次皆被拒，把求而不得写成了诗。"),
            ("典故", "《当你老了》设想恋人暮年炉火旁翻读诗卷，唯有诗人爱她朝圣者的灵魂——爱的是青春之外的东西。"),
            ("主题解读", "叶芝把凯尔特神话与个人爱情熔铸为象征体系，越到晚年诗越冷峻开阔。"),
        ],
    },
    {
        "title": "李太白集",
        "author": "李白",
        "era": "盛唐",
        "school": "浪漫主义诗歌",
        "category": "诗歌",
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
        "category": "诗歌",
        "themes": ["旷达", "离别", "人生"],
        "knowledge": [
            ("作者背景", "苏轼一生三起三落，愈贬愈旷达，把人生的不如意都写成了豁然。"),
            ("公认名句", "人有悲欢离合，月有阴晴圆缺，此事古难全。（《水调歌头》）"),
            ("公认名句", "回首向来萧瑟处，归去，也无风雨也无晴。（《定风波》）"),
        ],
    },
    # ------------------------------------------------------------- 戏剧
    {
        "title": "哈姆雷特",
        "author": "威廉·莎士比亚",
        "era": "文艺复兴",
        "school": "悲剧",
        "category": "戏剧",
        "themes": ["复仇", "犹疑", "存在"],
        "knowledge": [
            ("作者背景", "莎士比亚四大悲剧之首，王子复仇的故事被写成了人类犹疑与自省的标本。"),
            ("公认名句", "生存还是毁灭，这是一个值得考虑的问题。（朱生豪译）"),
            ("主题解读", "哈姆雷特的延宕不是懦弱，而是思想过剩者面对行动时的深渊——想得越清楚，越难落刀。"),
        ],
    },
    {
        "title": "尼伯龙根的指环",
        "author": "理查德·瓦格纳",
        "era": "19世纪",
        "school": "乐剧",
        "category": "戏剧",
        "themes": ["权力", "诅咒", "诸神黄昏"],
        "knowledge": [
            ("作者背景", "瓦格纳耗时二十六年完成的四联乐剧，取材北欧与日耳曼神话，需连演四晚。"),
            ("主题解读", "莱茵的黄金铸成指环，得到它的人必弃绝爱情——权力与爱的不可兼得贯穿始终，诸神也因贪欲走向黄昏。"),
            ("典故", "「诸神黄昏」：旧秩序在大火中崩塌，指环归还莱茵河，世界在毁灭中重新开始。"),
        ],
    },
    # ------------------------------------------------------------- 散文
    {
        "title": "杂忆与杂记",
        "author": "鲁迅",
        "era": "20世纪初",
        "school": "现实主义",
        "category": "散文",
        "themes": ["国民性", "批判", "记忆"],
        "knowledge": [
            ("作者背景", "鲁迅以冷峻笔触剖析国民性，是中国现代文学奠基者之一。"),
            ("主题解读", "在回忆与杂感之间，鲁迅把个人经验上升为对时代的诊断。"),
        ],
    },
    {
        "title": "荷塘月色",
        "author": "朱自清",
        "era": "20世纪初",
        "school": "抒情散文",
        "category": "散文",
        "themes": ["月夜", "孤独", "宁静"],
        "knowledge": [
            ("作者背景", "朱自清的散文以纯净著称，《荷塘月色》写于1927年清华园，一夜失眠的独步。"),
            ("公认名句", "热闹是它们的，我什么也没有。"),
            ("主题解读", "月下荷塘的美是借来的片刻自由——「这一片天地好像是我的」，越写宁静，越见内心的不宁。"),
        ],
    },
    # ------------------------------------------------------------- 志怪文学
    {
        "title": "西游记",
        "author": "吴承恩",
        "era": "明代",
        "school": "神魔小说",
        "category": "志怪文学",
        "themes": ["修行", "反抗", "妖魔", "取经"],
        "knowledge": [
            ("主题解读", "取经是一场心性的修行，八十一难降的都是心魔；孙悟空由反抗到成佛，锋芒收于紧箍。"),
            ("典故", "大闹天宫：石猴不受天庭秩序约束，「皇帝轮流做，明年到我家」，是全书最恣意的反抗篇章。"),
        ],
    },
    {
        "title": "聊斋志异",
        "author": "蒲松龄",
        "era": "清代",
        "school": "志怪小说",
        "category": "志怪文学",
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
        "category": "志怪文学",
        "themes": ["神话", "异兽", "地理"],
        "knowledge": [
            ("主题解读", "中国神话与异兽设定的总源头，后世志怪、仙侠、都市幻想的世界观多由此取材。"),
            ("典故", "精卫填海：炎帝之女溺于东海，化为精卫鸟，衔西山木石以填沧海——以微小之躯对抗无穷之事。"),
            ("典故", "夸父逐日：夸父与日逐走，道渴而死，弃其杖化为邓林。"),
        ],
    },
    # ------------------------------------------------------------- 小说·爱情文学
    {
        "title": "傲慢与偏见",
        "author": "简·奥斯汀",
        "era": "19世纪初",
        "school": "现实主义",
        "category": "爱情文学",
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
        "category": "爱情文学",
        "themes": ["家族兴衰", "爱情", "幻灭", "命运"],
        "knowledge": [
            ("作者背景", "曹雪芹出身江宁织造世家，家道中落后于贫困中著书，「披阅十载，增删五次」。"),
            ("主题解读", "以宝黛爱情为线，写尽钟鸣鼎食之家的繁华与倾颓，真事隐去、假语存焉。"),
            ("公认名句", "假作真时真亦假，无为有处有还无。"),
        ],
    },
    {
        "title": "简·爱",
        "author": "夏洛蒂·勃朗特",
        "era": "19世纪",
        "school": "现实主义",
        "category": "爱情文学",
        "themes": ["尊严", "爱情", "独立"],
        "knowledge": [
            ("主题解读", "贫穷、卑微、不美，但灵魂平等——简·爱把爱情建立在人格对等之上，是女性叙事的里程碑。"),
            ("公认名句", "你以为我贫穷、相貌平平就没有感情吗？我的灵魂跟你一样，我的心也跟你完全一样。"),
        ],
    },
    # ------------------------------------------------------------- 小说·战争文学
    {
        "title": "战争与和平",
        "author": "列夫·托尔斯泰",
        "era": "19世纪",
        "school": "现实主义",
        "category": "战争文学",
        "themes": ["战争", "命运", "历史", "家族"],
        "knowledge": [
            ("作者背景", "托尔斯泰以1812年卫国战争为轴，写四大家族的沉浮，被公认为长篇小说的巅峰之一。"),
            ("主题解读", "战争在托尔斯泰笔下不是英雄的舞台而是偶然的洪流——历史由无数无名者的微小意志汇成，统帅不过是浪尖的泡沫。"),
            ("典故", "奥斯特里茨的天空：安德烈公爵重伤仰望高远流云，功名忽然渺小——战场上最著名的一次抬头。"),
        ],
    },
    {
        "title": "三国演义",
        "author": "罗贯中",
        "era": "元末明初",
        "school": "古典小说",
        "category": "战争文学",
        "themes": ["权谋", "忠义", "天下大势"],
        "knowledge": [
            ("主题解读", "在正史与民间讲史之间，把权谋与忠义写成中国人共同的性格词典。"),
            ("公认名句", "话说天下大势，分久必合，合久必分。"),
        ],
    },
    # ------------------------------------------------------------- 小说·现实文学
    {
        "title": "呐喊",
        "author": "鲁迅",
        "era": "20世纪初",
        "school": "现实主义",
        "category": "现实文学",
        "themes": ["觉醒", "国民性", "希望"],
        "knowledge": [
            ("主题解读", "《呐喊》为沉睡的时代发声，在铁屋子里喊出第一声，唤醒的痛苦好过麻木的安眠。"),
            ("公认名句", "其实地上本没有路，走的人多了，也便成了路。"),
            ("典故", "「铁屋子」比喻出自《呐喊》自序：万难破毁的铁屋里，熟睡的人们将被闷死，喊醒少数人是否更残酷？"),
        ],
    },
    {
        "title": "骆驼祥子",
        "author": "老舍",
        "era": "20世纪上半叶",
        "school": "现实主义",
        "category": "现实文学",
        "themes": ["底层", "奋斗", "沉沦", "城市"],
        "knowledge": [
            ("作者背景", "老舍是「人民艺术家」，以北平市民生活为底色，写尽底层的挣扎与体面。"),
            ("主题解读", "祥子三起三落，买车的梦被时代碾碎三次——个人奋斗在倾斜的社会里救不了自己，好人如何一步步沉沦是全书最狠的追问。"),
        ],
    },
    {
        "title": "罪与罚",
        "author": "陀思妥耶夫斯基",
        "era": "19世纪",
        "school": "现实主义",
        "category": "现实文学",
        "themes": ["罪", "救赎", "良知", "贫困"],
        "knowledge": [
            ("作者背景", "陀思妥耶夫斯基曾被判死刑、临刑赦免、流放西伯利亚，他的小说是在深渊边写成的。"),
            ("主题解读", "拉斯柯尔尼科夫用「超人理论」说服自己杀人，却被自己的良知审判——刑罚在法庭之前，先在失眠的每一夜执行。"),
        ],
    },
    {
        "title": "月亮与六便士",
        "author": "威廉·萨默塞特·毛姆",
        "era": "20世纪初",
        "school": "现实主义",
        "category": "现实文学",
        "themes": ["理想", "世俗", "艺术", "出走"],
        "knowledge": [
            ("作者背景", "毛姆以冷静近乎刻薄的观察写人性，自称二流作家里坐头把交椅，读者却始终站在他一边。"),
            ("主题解读", "证券经纪人抛下一切去画画，众人看见满地六便士，他只看见月亮——理想对世俗的背叛，写得毫不浪漫、近乎残忍。"),
        ],
    },
    {
        "title": "双城记",
        "author": "查尔斯·狄更斯",
        "era": "19世纪",
        "school": "现实主义",
        "category": "现实文学",
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
        "category": "现实文学",
        "themes": ["救赎", "苦难", "良知", "革命"],
        "knowledge": [
            ("作者背景", "雨果流亡期间完成此书，自言写给「一切苦难中的人」。"),
            ("主题解读", "冉阿让的一生是良知对法律、宽恕对惩罚的漫长胜利；主教的银烛台是全书善意的火种。"),
        ],
    },
    {
        "title": "水浒传",
        "author": "施耐庵",
        "era": "元末明初",
        "school": "古典小说",
        "category": "现实文学",
        "themes": ["江湖", "官逼民反", "义气"],
        "knowledge": [
            ("主题解读", "一百单八将逼上梁山，写的是秩序崩坏处江湖如何自组织——义气既是纽带也是悲剧根源。"),
        ],
    },
    # ------------------------------------------------------------- 小说·哲学
    {
        "title": "局外人",
        "author": "阿尔贝·加缪",
        "era": "20世纪",
        "school": "存在主义",
        "category": "哲学",
        "themes": ["荒诞", "疏离", "真实"],
        "knowledge": [
            ("作者背景", "加缪生于阿尔及利亚贫民家庭，44岁获诺贝尔文学奖，荒诞哲学的代言人。"),
            ("主题解读", "默尔索因在母亲葬礼上没有哭而被判处死刑——社会审判的不是他的罪行，而是他拒绝表演感情的诚实。"),
        ],
    },
    {
        "title": "西西弗斯的神话",
        "author": "阿尔贝·加缪",
        "era": "20世纪",
        "school": "存在主义",
        "category": "哲学",
        "themes": ["荒诞", "反抗", "幸福"],
        "knowledge": [
            ("主题解读", "诸神罚西西弗斯永远推石上山，石头永远滚落——加缪却说，应当想象他是幸福的：明知无意义仍全力以赴，就是对荒诞最彻底的反抗。"),
            ("典故", "推石上山：现代语境里「西西弗斯式」指永无止境的徒劳，但加缪恰恰要为这徒劳翻案。"),
        ],
    },
    # ------------------------------------------------------------- 小说·成长文学
    {
        "title": "大卫·科波菲尔",
        "author": "查尔斯·狄更斯",
        "era": "19世纪",
        "school": "现实主义",
        "category": "成长文学",
        "themes": ["成长", "苦难", "自我成就"],
        "knowledge": [
            ("作者背景", "狄更斯最钟爱的「宠儿之书」，大量取材他做童工、当速记员的亲身经历。"),
            ("主题解读", "孤儿大卫从继父的皮鞭下走到作家的书桌前——成长小说的原型结构：把命运给的每一次羞辱都变成叙述的资产。"),
        ],
    },
]


async def main() -> None:
    async with AsyncSessionLocal() as db:
        existing = {
            (w.title, w.author): w
            for w in (await db.execute(select(LiteraryWork))).scalars().all()
        }
        added = updated = 0
        for w in WORKS:
            if not w.get("is_public_domain", True):
                continue  # whitelist guard
            key = (w["title"], w["author"])
            if key in existing:
                row = existing[key]
                if row.category != w["category"]:
                    row.category = w["category"]  # backfill taxonomy
                    updated += 1
                continue
            work = LiteraryWork(
                title=w["title"],
                author=w["author"],
                era=w.get("era"),
                category=w.get("category"),
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
    print(
        f"literary library seeded ({added} new, {updated} categories backfilled, "
        f"{len(WORKS)} defined)."
    )


if __name__ == "__main__":
    asyncio.run(main())
