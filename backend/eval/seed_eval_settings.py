# -*- coding: utf-8 -*-
"""Seed a richer 龙城 setting library into a project (via the running API, so
chunks are embedded and indexed exactly like production writes).

Idempotent: skips characters/world entries whose name/title already exists.

    python eval/seed_eval_settings.py --project-id 5
"""
from __future__ import annotations

import argparse

import httpx

CHARACTERS = [
    {
        "name": "陆沉",
        "persona": {"性格": "外冷内热", "能力": "言灵S级", "口癖": "……麻烦。"},
        "summary": "白天是大学讲师，夜里是龙城隐秘秩序的守夜人。",
    },
    {
        "name": "苏离",
        "persona": {"性格": "毒舌但重情", "能力": "操控火焰"},
        "summary": "地下情报贩子，龙城酒吧老板娘，消息网遍布黑白两道。",
    },
    {
        "name": "老周",
        "persona": {"性格": "温和固执", "能力": "言灵A级·封缄", "身份": "陆沉的导师"},
        "summary": "前守夜人档案官，陆沉的授业导师，十年前在一次镇物押运任务中失踪。",
    },
    {
        "name": "白鸦",
        "persona": {"性格": "阴郁寡言", "能力": "影子操控", "阵营": "黑市"},
        "summary": "黑市雇佣的影子杀手，能潜入任何有阴影的地方，只在新月之夜接单。",
    },
    {
        "name": "林小满",
        "persona": {"性格": "怯懦但善良", "能力": "灵视（天生看得见超自然）"},
        "summary": "普通大学生，陆沉课上的学生，天生灵视却不知其来历，屡次被卷入异常事件。",
    },
    {
        "name": "秦九",
        "persona": {"性格": "铁面无私", "能力": "言灵A级·锁链", "身份": "裁决庭执行官"},
        "summary": "夜幕裁决庭的首席执行官，负责缉拿违反夜幕协定的异能者，与陆沉互相看不顺眼。",
    },
    {
        "name": "温姮",
        "persona": {"性格": "慵懒神秘", "能力": "触物读忆"},
        "summary": "雾巷古董店的老板娘，触碰物品即可读取其承载的记忆，收费高昂且从不赊账。",
    },
    {
        "name": "阿灰",
        "persona": {"性格": "贪吃话痨", "能力": "化形为猫", "种类": "妖"},
        "summary": "以灰猫形态穿行龙城的信使妖，替各方势力传递不能留下痕迹的口信。",
    },
]

WORLD = [
    {
        "category": "规则",
        "title": "夜幕协定",
        "content": "超自然存在不得在凡人面前显露力量，违者由守夜人裁决。",
    },
    {
        "category": "地点",
        "title": "沉沙湾旧码头",
        "content": "废弃的集装箱码头，超自然黑市每逢新月在此开市。",
    },
    {
        "category": "力量体系",
        "title": "言灵等级",
        "content": "言灵能力从E级到S级共六档，等级越高，言出法随的范围越广，代价也越重。",
    },
    {
        "category": "势力",
        "title": "夜幕裁决庭",
        "content": "执行夜幕协定的机构，有权缉拿、审判、封印违规异能者，执行官皆佩戴黑曜石徽记。",
    },
    {
        "category": "规则",
        "title": "灰市通行证",
        "content": "进入黑市交易必须持有灰市通行证，一枚刻着乌鸦的骨牌，转让即失效。",
    },
    {
        "category": "地点",
        "title": "雾巷",
        "content": "只在雨夜出现的隐藏街区，入口在城南旧书店的后门，巷内店铺不受夜幕协定约束。",
    },
    {
        "category": "规则",
        "title": "镇物",
        "content": "封印着异常存在的古物，一旦破损封印松动，需守夜人重新加固或移交裁决庭。",
    },
    {
        "category": "规则",
        "title": "血月之夜",
        "content": "每逢血月，全城异能者的力量暴涨且难以自控，守夜人全员戒备，裁决庭宵禁。",
    },
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--project-id", type=int, required=True)
    args = ap.parse_args()

    with httpx.Client(base_url=args.base_url, timeout=120) as client:
        have_chars = {
            c["name"]
            for c in client.get(f"/projects/{args.project_id}/characters").json()
        }
        have_world = {
            w["title"] for w in client.get(f"/projects/{args.project_id}/world").json()
        }
        added = 0
        for ch in CHARACTERS:
            if ch["name"] in have_chars:
                continue
            client.post(f"/projects/{args.project_id}/characters", json=ch).raise_for_status()
            added += 1
        for w in WORLD:
            if w["title"] in have_world:
                continue
            client.post(f"/projects/{args.project_id}/world", json=w).raise_for_status()
            added += 1
    print(f"seeded {added} new settings "
          f"({len(CHARACTERS)} characters / {len(WORLD)} world total defined).")


if __name__ == "__main__":
    main()
