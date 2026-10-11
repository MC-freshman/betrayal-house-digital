"""StorybookTwistsMode（剧本 67）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
)


class StorybookTwistsMode(GenericModeHandler):
    """剧本 67 从前有一次（Once Upon a Time）。

    权威原文：英雄手册 p78 / 叛徒手册 p149。
    · 叛徒入定：不能移动、攻击、使用物品，不能被攻击，属性不升不降。
    · 英雄与叛徒同房可代替攻击自动偷窃（含疯子/女孩/狗）；叛徒不阻挡离房。
    · 同房做知识检定并加上故事轨道，6+ 抽取任务（6 骰 0–12，已抽则顺延）。
    · 完成任务数达到开局英雄数，并活到故事轨道 7 → 英雄胜；否则悲伤结局。
    · 猎蛛开局；女巫（段落 7）与恶龙（段落 10）由故事召唤。
    · 猎蛛造成物理伤害前先降 1 点属性；女巫可传送并用力量或理智攻击；
      恶龙喷火；除非被斧/矛/血匕/左轮/戒指/炸药击中，否则恶龙被击败不击晕。
    已知简化：
    · 剧情转折「厄运/关键失误」需要打断他人掷骰，未建模；坍塌地板/晕眩由人类自选，
      bot 只用冗长叙述、时光飞逝、埋伏、复苏。
    · 物品牌没有神秘硬币、德鲁伊护符、骷髅钥匙、玩具猴——对应任务只用仍在牌库的替代物。
    · 「朝外窗户」房间近似为门厅/阳台/塔楼/庭院/花园/墓地。
    · 五芒星室「忽略房间文字」只记 flag（该房间本就几乎无效果）。
    · 「谁抽到了牙」简化为当前持有预兆「牙」的英雄。
    · 寻找任务 / 完成任务 / 偷窃 / 剧情转折共用引擎的「每回合一次剧本行动」槽。
    · 女巫每回合固定传送到最近英雄（原文可选传送或正常移动）。
    · 告警口径（2026-09-16）：试玩诊断在 33 局里报出的 16 例
      `steal_from_traitor(出现N/未用)` 是**指标假警报**，不是缺陷。诊断器把
      `available_actions` 的输出一律记成 offered，而本剧本的偷窃是"合法却常常
      无用"：入定的叛徒身上只挂着可交易的普通物件（钟/兔脚/戒指…），英雄已抽到的
      任务缺的却是别的东西（疯子/女孩/瓶子/面具/骷髅…）。逐回合实测 seed251/3p：
      与叛徒同房时 offered=[obtain_quest, steal_from_traitor]，按声明顺序取
      obtain——因为手上没有"叛徒恰好持有其缺牌"的未完成任务，`bot_action_blocked`
      不会挡它。**这正是正确打法**（原版也不会为了偷一件与任务无关的钟而放弃抽
      任务）。真需要偷的时候（缺牌正攥在叛徒手上）`bot_action_blocked` 会挡掉
      obtain，steal 自然落到 `max()` 手里。
    · 平衡观察（2026-09-16，11 种子 × 3/4/5 人 = 33 局 bot 对局）：叛徒胜 33。
      英雄胜线是结构性吃力，不是 bot 漏做——叛徒每回合推故事轨 1 格（约 7 回合
      翻完），英雄要在此之前完成"开局人数"个任务（3/4/5 人局即 2/3/4 个），每个
      任务都得先同房知识检定抽到、再凑齐限定物件/房间。33 局里 `obtain_quest` 与
      `complete_quest` 都在真实使用、任务链走得通，只是赶不上故事的进度。按项目
      惯例（只修 bug、不修平衡）接受为"难而非坏"。
    """

    mode = "storybook_twists"
    SPIDER = "story_spider"
    WITCH = "story_witch"
    DRAGON = "story_dragon"
    COMPANIONS = ("omen_madman", "omen_girl", "omen_dog")
    SPIDER_ROOMS = ("entrance_hall", "balcony", "tower", "patio", "garden", "graveyard")
    STUN_WEAPONS = {
        "item_axe", "omen_spear", "item_blood_dagger", "item_revolver",
        "omen_ring", "item_dynamite",
    }
    TWISTS = (
        "lengthy_narration",
        "time_flies",
        "evil_luck",
        "critical_lapse",
        "revival",
        "ambush",
        "collapsing_floor",
        "daze",
    )
    TWIST_LABELS = {
        "lengthy_narration": "冗长叙述（下次不推进故事）",
        "time_flies": "时光飞逝（立刻推进一格故事）",
        "evil_luck": "厄运（重掷你刚才的骰，未建模）",
        "critical_lapse": "关键失误（逼英雄重掷，未建模）",
        "revival": "复苏（解除一只怪物的昏迷）",
        "ambush": "埋伏（把一只怪物移到任意房间）",
        "collapsing_floor": "塌陷地板（把一名英雄送到下一层）",
        "daze": "晕眩（英雄下回合不能既移动又攻击）",
    }
    QUEST_NAMES = {
        0: "驱魔放逐",
        1: "交叉手指",
        2: "解药",
        3: "力量试炼",
        4: "抹去五芒星",
        5: "驱魔",
        6: "落难少女",
        7: "安息",
        8: "求问亡者",
        9: "高贵受苦",
        10: "古人之路",
        11: "拥抱命运",
        12: "打破蛊惑",
    }
    # 任务 → "让它可以完成"所需先备的物件 / 同伴（`bot_goal_rooms` 用）。
    QUEST_ITEM_CHOICES = {
        0: ("item_bell", "omen_book", "item_candle"),
        1: ("item_lucky_stone", "item_rabbit_foot"),
        7: ("omen_skull",),
        8: ("omen_spirit_board",),
        10: ("item_amulet_of_the_ages", "item_healing_salve"),
        11: ("item_bottle",),
        12: ("omen_mask",),
    }
    QUEST_COMPANION = {2: "omen_bite", 5: "omen_madman", 6: "omen_girl"}

    def setup(self, engine, haunt, room_key):
        flags = engine._haunt_flags()
        heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        flags["initial_hero_count"] = len(heroes)
        flags["obtained_quests"] = []
        flags["completed_quests"] = []
        flags["used_twists"] = []
        flags["body_tokens"] = 0
        flags["skip_next_advance"] = False
        flags["story_ended"] = False
        flags["dazed"] = []
        flags["pentagram_erased"] = False
        engine._set_haunt_track_value("quests", 0)
        engine._set_haunt_track_value("story", 0)
        engine._haunt_tracks()["quests"]["target"] = max(1, len(heroes))

        engine.state.monsters = [
            m for m in engine.state.monsters
            if getattr(m, "template_id", "") in {self.SPIDER, self.WITCH, self.DRAGON}
        ]
        if engine._monster_by_template(self.SPIDER) is None:
            spawn = self._first_room(engine, self.SPIDER_ROOMS) or room_key
            engine._spawn_single_haunt_monster(
                {"template_id": self.SPIDER, "name": "猎蛛", "speed": 4, "might": 5, "sanity": 3},
                spawn,
            )
        engine._log("故事开始了。猎蛛已经循着气味进了这栋房子。")

    def on_turn_start(self, engine, player):
        flags = engine._haunt_flags()
        dazed = [int(x) for x in (flags.get("dazed") or [])]
        if player.id in dazed:
            flags["dazed"] = [x for x in dazed if x != player.id]
            flags["dazed_now"] = player.id
        else:
            flags.pop("dazed_now", None)
        if player.role != "traitor" or player.dead:
            return
        player.steps_remaining = 0
        player.attack_used = True
        player.item_used = True
        twos = sum(1 for _ in range(2) if engine.rng.choice((0, 1, 2)) == 2)
        if twos:
            flags["body_tokens"] = int(flags.get("body_tokens") or 0) + twos
            engine._log(f"故事里又多了 {twos} 处转折（尸体令牌 {flags['body_tokens']}）。")
        if getattr(player, "control", "") == "bot":
            self._bot_auto_twist(engine, player)
        self._advance_story(engine)

    def on_player_moved(self, engine, player):
        if engine._haunt_flags().get("dazed_now") == player.id:
            player.attack_used = True

    def on_attack_resolved(self, engine, attacker, target, attacker_won):
        if engine._haunt_flags().get("dazed_now") == getattr(attacker, "id", None):
            attacker.steps_remaining = 0
        if not attacker_won or getattr(attacker, "role", "") != "hero":
            return
        if getattr(target, "template_id", "") != self.SPIDER:
            return
        if getattr(engine, "_last_attack_attr", "might") != "might":
            return
        obtained = [int(x) for x in (engine._haunt_flags().get("obtained_quests") or [])]
        completed = [int(x) for x in (engine._haunt_flags().get("completed_quests") or [])]
        if 3 in obtained and 3 not in completed:
            self._complete_quest(engine, attacker, 3)

    def available_actions(self, engine, player):
        actions = super().available_actions(engine, player)
        result = []
        for action in actions:
            aid = getattr(action, "id", "")
            if aid == "obtain_quest" and not self._can_obtain(engine, player):
                continue
            if aid == "complete_quest" and not self._completable_quests(engine, player):
                continue
            if aid == "steal_from_traitor" and not self._can_steal_traitor(engine, player):
                continue
            if aid == "plot_twist" and not self._can_twist(engine, player):
                continue
            result.append(action)
        return result

    def perform_action(self, engine, player, action_id, data):
        if action_id == "obtain_quest":
            return self._obtain_quest(engine, player)
        if action_id == "complete_quest":
            return self._try_complete(engine, player)
        if action_id == "steal_from_traitor":
            return self._steal_traitor(engine, player)
        if action_id == "plot_twist":
            return self._do_twist(engine, player, data)
        return super().perform_action(engine, player, action_id, data)

    def attack_allowed(self, engine, attacker, target):
        if getattr(target, "role", "") == "traitor":
            return False
        if getattr(attacker, "role", "") == "traitor":
            return False
        return True

    def counts_as_movement_obstacle(self, engine, mover, occupant):
        return getattr(occupant, "role", "") != "traitor"

    def item_use_blocked(self, engine, player, card_id):
        return getattr(player, "role", "") == "traitor"

    def can_discover_rooms(self, engine, player):
        return getattr(player, "role", "") != "traitor"

    def physical_damage_reduction(self, engine, player, amount, source, damage_type):
        if getattr(player, "role", "") == "traitor":
            return amount
        return 0

    def on_monster_defeated(self, engine, monster, amount):
        if getattr(monster, "template_id", "") != self.DRAGON:
            return False
        weapon = getattr(engine, "_last_attack_weapon_id", "") or ""
        if weapon in self.STUN_WEAPONS:
            return False
        engine._log("鳞片挡下了这一击——没有合适的武器，恶龙没有被击晕。")
        return True

    def on_monster_turn_start(self, engine, monster):
        if getattr(monster, "template_id", "") != self.WITCH:
            return False
        heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        if not heroes:
            return True
        heroes.sort(key=lambda p: (engine._path_length(monster.room_key, p.room_key), p.id))
        target = heroes[0]
        monster.room_key = target.room_key
        engine._log(f"{monster.name} 瞬间出现在 {engine.state.board[monster.room_key].name}。")
        self._witch_attack(engine, monster)
        return True

    def on_monster_turn_attack(self, engine, monster):
        tid = getattr(monster, "template_id", "")
        if tid == self.WITCH:
            return self._witch_attack(engine, monster)
        if tid == self.DRAGON:
            return self._dragon_breath(engine, monster)
        return False

    def on_monster_attack(self, engine, monster, target, amount):
        if getattr(monster, "template_id", "") != self.SPIDER:
            return False
        if amount <= 0:
            return False
        stat = self._venom_stat(engine, target)
        engine._log(f"猎蛛的毒牙先削弱了 {target.name} 的{stat}。")
        engine._apply_stat_loss(target, stat, 1)
        engine._deal_damage(target, "physical", amount, source=monster.name)
        return True

    def bot_action_blocked(self, engine, player, action_id):
        """#67：英雄要的东西正攥在叛徒手上时，这一回合别抽新任务，改成先偷。

        三项英雄行动的 bot 打分完全相同（标签都不含打分器的加分词），`max()`
        取 rule_data 声明靠前者——"有任务能立刻完成 → 先完成"由声明顺序表达；
        但"该不该偷"是**条件性**的，静态顺序表达不了（把 steal 提到 obtain
        前面会让英雄一直偷、永不抽任务，任务链直接断掉）。

        `bot_goal_rooms` / `_quest_prep_goals` 会把缺物件的英雄一路引到持有者
        房里，而持有者常常正是入定的叛徒——他开局就拿着瓶子、幸运石、兔子脚、
        头骨、通灵板、钟、蜡烛、面具这些任务要用的东西（实测 seed3/3p、
        seed101/3p、seed251/3p）。人已经站到他面前却还在抽牌，任务就永远卡在
        "缺少物件"上——这是英雄 0/33 胜的一处成因。
        """
        if action_id != "obtain_quest":
            return False
        flags = engine._haunt_flags()
        obtained = [int(x) for x in (flags.get("obtained_quests") or [])]
        completed = {int(x) for x in (flags.get("completed_quests") or [])}
        traitor = self._traitor(engine)
        if traitor is None:
            return False
        for qid in obtained:
            if qid in completed:
                continue
            if any(card in traitor.items for card in self._missing_quest_cards(player, qid)):
                return True
        return False

    def _missing_quest_cards(self, player, qid):
        """该任务还缺、而玩家手上没有的关键牌（物件候选 + 伙伴）。

        物件类任务是"多选一"（如任务 0 只要钟/书/蜡烛任一），所以只有玩家
        一个候选都没拿到时才算缺；伙伴类任务要求伙伴在**自己**身上。
        """
        cards = []
        choices = self.QUEST_ITEM_CHOICES.get(qid)
        if choices and not any(c in player.items for c in choices):
            cards.extend(choices)
        companion = self.QUEST_COMPANION.get(qid)
        if companion and companion not in player.items:
            cards.append(companion)
        return cards

    def bot_goal_rooms(self, engine, player):
        """把英雄推向"让已抽到的任务变得可完成"的地点。

        ## 旧实现的死锁（实测英雄 0/33 胜、`complete_quest` 从不出现）
        `_quest_ready` 判定的是"英雄**此刻就站在**目标房/满足条件"，
        于是对**还没到位**的英雄永远返回 False → `_completable_quests`
        恒空 → `bot_goal_rooms` 恒把英雄派去叛徒房抽任务 → 抽到也不走。
        现在改为遍历"已抽未完成"的任务：先取所需物件，再进目标房。
        """
        if player.dead or player.role == "traitor":
            return []
        flags = engine._haunt_flags()
        obtained = [int(x) for x in (flags.get("obtained_quests") or [])]
        completed = {int(x) for x in (flags.get("completed_quests") or [])}
        goals = []
        for qid in obtained:
            if qid in completed:
                continue
            goals.extend(self._quest_prep_goals(engine, player, qid))
        if not goals:
            traitor = self._traitor(engine)
            if traitor is not None:
                goals.append(f"__room__{traitor.room_key}")
        return goals

    def _quest_prep_goals(self, engine, player, qid):
        goals = []
        needed = self.QUEST_ITEM_CHOICES.get(qid)
        if needed and not any(card in player.items for card in needed):
            where = self._find_card(engine, needed)
            # 缺少关键物件：先去把物件拿到手（在房间地上就过去捡，在别人手里
            # 就过去会合）。物件还在牌堆里则本任务暂时无解，退回目标房碰运气。
            if where is not None:
                return [f"__room__{where}"]
        companion = self.QUEST_COMPANION.get(qid)
        if companion:
            holder = self._holder(engine, companion)
            if holder is not None and holder.id != player.id:
                goals.append(f"__room__{holder.room_key}")
        goals.extend(self._quest_rooms(engine, qid, player))
        return goals

    def _find_card(self, engine, card_ids):
        for card_id in card_ids:
            for room_key, cards in engine.state.room_items.items():
                if card_id in cards:
                    return room_key
            holder = self._holder(engine, card_id)
            if holder is not None:
                return holder.room_key
        return None

    def progress_summary(self, engine, viewer):
        flags = engine._haunt_flags()
        needed = int(flags.get("initial_hero_count") or 1)
        obtained = [int(x) for x in (flags.get("obtained_quests") or [])]
        completed = [int(x) for x in (flags.get("completed_quests") or [])]
        names = [self.QUEST_NAMES.get(q, str(q)) for q in obtained if q not in completed]
        lines = [
            f"故事进度 {engine._haunt_track_value('story')}/7",
            f"已完成任务 {len(completed)}/{needed}",
            f"剧情转折令牌 {int(flags.get('body_tokens') or 0)}",
        ]
        if names:
            lines.append("进行中：" + "、".join(names))
        return lines

    def check_victory(self, engine):
        flags = engine._haunt_flags()
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "最后一名英雄倒下了。故事以悲剧收场。")
            return True
        if engine.state.winner:
            return True
        if flags.get("story_ended"):
            needed = max(1, int(flags.get("initial_hero_count") or 1))
            done = len(flags.get("completed_quests") or [])
            if done >= needed:
                engine._set_winner("heroes", "……从此他们过上了幸福的生活。完。")
            else:
                engine._set_winner("traitor", "任务未完，故事却已结束——悲伤的结局。")
            return True
        if not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            return True
        return False

    # ------------------------------------------------------------- 故事

    def _advance_story(self, engine):
        flags = engine._haunt_flags()
        if flags.get("story_ended"):
            return
        if flags.get("skip_next_advance"):
            flags["skip_next_advance"] = False
            engine._log("冗长的叙述拖住了时间，故事这一回没有往前翻。")
            return
        value = engine._advance_haunt_track("story", 1)
        if value >= 7:
            flags["story_ended"] = True
            engine._log("故事翻到了最后一页。")
            engine.check_victory()
            return
        section = value + len(engine.state.players)
        self._read_section(engine, section)

    def _read_section(self, engine, section):
        flags = engine._haunt_flags()
        if section == 5 or section == 11:
            flags["body_tokens"] = int(flags.get("body_tokens") or 0) + 1
            engine._log(f"故事第 {section} 段：一枚尸体令牌落入叙事者手中。")
        elif section == 7:
            self._spawn_named(engine, self.WITCH, "女巫", 3, 4, 5, self._any_room(engine))
            engine._log("故事第 7 段：不耐烦的女巫走进了房子。")
        elif section == 8:
            spider = engine._monster_by_template(self.SPIDER)
            if spider is not None:
                spider.speed = int(getattr(spider, "speed", 4)) + 1
                engine._log(f"故事第 8 段：猎蛛感到主人靠近，速度变为 {spider.speed}。")
        elif section == 10:
            traitor = self._traitor(engine)
            room = traitor.room_key if traitor is not None else next(iter(engine.state.board))
            self._spawn_named(engine, self.DRAGON, "恶龙", 5, 7, 4, room)
            engine._log("故事第 10 段：恶龙咆哮着飞进叙事者所在的房间。")
        else:
            engine._log(f"故事第 {section} 段被读了出来。")

    def _spawn_named(self, engine, template_id, name, speed, might, sanity, room_key):
        if engine._monster_by_template(template_id) is not None:
            return
        engine._spawn_single_haunt_monster(
            {"template_id": template_id, "name": name, "speed": speed, "might": might, "sanity": sanity},
            room_key,
        )

    # ------------------------------------------------------------- 任务

    def _can_obtain(self, engine, player):
        if player.role != "hero" or player.dead:
            return False
        traitor = self._traitor(engine)
        return traitor is not None and traitor.room_key == player.room_key and not traitor.dead

    def _obtain_quest(self, engine, player):
        if not self._can_obtain(engine, player):
            return False
        story = engine._haunt_track_value("story")
        dice = max(1, min(8, engine._effective_stat(player, "knowledge") + engine._check_bonus(player, "knowledge")))
        roll = engine.roll_dice(dice, "寻找关键情节")
        engine._log(f"{player.name} 翻查故事（{roll}+{story}）。")
        if roll + story < 6:
            engine._log("这一页还没有露出破绽。")
            return True
        qid = self._draw_quest(engine)
        if qid is None:
            engine._log("所有任务都已经找到了。")
            return True
        engine._log(f"找到了任务：{self.QUEST_NAMES[qid]}。")
        return True

    def _draw_quest(self, engine):
        flags = engine._haunt_flags()
        obtained = [int(x) for x in (flags.get("obtained_quests") or [])]
        if len(obtained) >= 13:
            return None
        start = sum(engine.rng.choice((0, 1, 2)) for _ in range(6))
        for offset in range(13):
            qid = (start + offset) % 13
            if qid not in obtained:
                obtained.append(qid)
                flags["obtained_quests"] = obtained
                return qid
        return None

    def _completable_quests(self, engine, player):
        if player.role != "hero" or player.dead:
            return []
        flags = engine._haunt_flags()
        obtained = [int(x) for x in (flags.get("obtained_quests") or [])]
        completed = set(int(x) for x in (flags.get("completed_quests") or []))
        return [qid for qid in obtained if qid not in completed and self._quest_ready(engine, player, qid)]

    def _try_complete(self, engine, player):
        ready = self._completable_quests(engine, player)
        if not ready:
            return False
        if len(ready) == 1 or getattr(player, "control", "") == "bot":
            qid = ready[0]
        else:
            labels = [self.QUEST_NAMES.get(q, str(q)) for q in ready]
            idx = engine.prompter.choose_from_list("完成任务", "要完成哪一个？", labels)
            if idx is None:
                return False
            qid = ready[idx]
        return self._complete_quest(engine, player, qid)

    def _complete_quest(self, engine, player, qid):
        flags = engine._haunt_flags()
        completed = [int(x) for x in (flags.get("completed_quests") or [])]
        if qid in completed:
            return False
        checks = {2: ("knowledge", 4), 4: ("sanity", 5), 5: ("sanity", 5), 6: ("knowledge", 5), 12: ("knowledge", 6)}
        if qid in checks:
            stat, target = checks[qid]
            if not self._stat_ok(engine, player, stat, target):
                engine._log(f"任务「{self.QUEST_NAMES.get(qid, qid)}」的检定失败了。")
                return True
        if qid == 0:
            engine._increase_stat(player, "sanity", 1)
        elif qid == 1:
            engine._draw_item(player)
        elif qid == 2:
            bitten = self._holder(engine, "omen_bite")
            if bitten is not None:
                self._restore_physical(engine, bitten)
        elif qid == 3:
            engine._increase_stat(player, "might", 1)
        elif qid == 4:
            flags["pentagram_erased"] = True
        elif qid == 5:
            mad = self._holder(engine, "omen_madman")
            if mad is not None:
                engine._increase_stat(mad, "sanity", 1)
        elif qid == 6:
            girl_holder = self._holder(engine, "omen_girl")
            if girl_holder is not None:
                engine._discard_card_from_player(girl_holder, "omen_girl", return_to_room=False)
                engine._log(f"{girl_holder.name} 把女孩留在了门厅，没有失去属性。")
        elif qid == 7:
            engine._discard_card_from_player(player, "omen_skull", return_to_room=False)
            engine._increase_stat(player, "knowledge", 1)
        elif qid == 8:
            extra = self._draw_quest(engine)
            if extra is not None:
                engine._log(f"灵应板又翻出了任务：{self.QUEST_NAMES[extra]}。")
        elif qid == 9:
            physical = engine.roll_dice(2, "高贵受苦·肉体")
            mental = engine.roll_dice(1, "高贵受苦·精神")
            engine._deal_damage(player, "physical", physical, source="高贵受苦")
            if not player.dead:
                engine._deal_damage(player, "mental", mental, source="高贵受苦")
            if player.dead:
                engine._log("这份苦没有人能活着受完。")
                return True
        elif qid == 10:
            stats = ("speed", "might", "sanity", "knowledge")
            best = max(stats, key=lambda s: engine._effective_stat(player, s))
            engine._increase_stat(player, best, 1)
        elif qid == 12:
            spider = engine._monster_by_template(self.SPIDER)
            if spider is not None:
                engine._kill_monster(spider, killer=player)
                engine._log("猎蛛逃出了这栋房子。")
        completed.append(qid)
        flags["completed_quests"] = completed
        engine._set_haunt_track_value("quests", len(completed))
        engine._log(f"{player.name} 完成了任务「{self.QUEST_NAMES.get(qid, qid)}」（{len(completed)}/{flags.get('initial_hero_count')}）。")
        if qid == 11:
            engine._discard_card_from_player(player, "item_bottle", return_to_room=False)
            engine._log(f"{player.name} 喝下了瓶子。故事被往前翻了一页。")
            self._advance_story(engine)
        return True

    def _quest_ready(self, engine, player, qid):
        room = engine.state.board.get(player.room_key)
        tid = room.template_id if room is not None else ""
        witch = engine._monster_by_template(self.WITCH)
        spider = engine._monster_by_template(self.SPIDER)
        traitor = self._traitor(engine)
        if qid == 0:
            return witch is not None and player.room_key == witch.room_key and self._room_has_all(
                engine, player.room_key, ("item_bell", "omen_book", "item_candle")
            )
        if qid == 1:
            return traitor is not None and player.room_key == traitor.room_key and (
                "item_lucky_stone" in player.items or "item_rabbit_foot" in player.items
            )
        if qid == 2:
            bitten = self._holder(engine, "omen_bite")
            return (
                bitten is not None
                and bitten.room_key == player.room_key
                and tid in {"research_laboratory", "operating_laboratory"}
            )
        if qid == 3:
            return False
        if qid == 4:
            return tid == "pentagram_chamber"
        if qid == 5:
            mad = self._holder(engine, "omen_madman")
            return mad is not None and mad.room_key == player.room_key and tid == "chapel"
        if qid == 6:
            girl = self._holder(engine, "omen_girl")
            return girl is not None and girl.room_key == player.room_key and tid == "entrance_hall"
        if qid == 7:
            return "omen_skull" in player.items and tid in {"crypt", "graveyard"}
        if qid == 8:
            return traitor is not None and player.room_key == traitor.room_key and "omen_spirit_board" in player.items
        if qid == 9:
            return tid == "bloody_room"
        if qid == 10:
            return tid == "garden" and (
                "item_amulet_of_the_ages" in player.items or "item_healing_salve" in player.items
            )
        if qid == 11:
            return "item_bottle" in player.items
        if qid == 12:
            return (
                spider is not None
                and player.room_key == spider.room_key
                and "omen_mask" in player.items
            )
        return False

    def _quest_rooms(self, engine, qid, player):
        mapping = {
            0: [self.WITCH],
            1: [],
            2: ["research_laboratory", "operating_laboratory"],
            4: ["pentagram_chamber"],
            5: ["chapel"],
            6: ["entrance_hall"],
            7: ["crypt", "graveyard"],
            8: [],
            9: ["bloody_room"],
            10: ["garden"],
            12: [self.SPIDER],
        }
        rooms = mapping.get(qid, [])
        goals = []
        traitor = self._traitor(engine)
        if qid in {1, 8} and traitor is not None:
            goals.append(f"__room__{traitor.room_key}")
        for item in rooms:
            if item in {self.WITCH, self.SPIDER}:
                mon = engine._monster_by_template(item)
                if mon is not None:
                    goals.append(f"__room__{mon.room_key}")
            else:
                goals.append(item)
        return goals

    def _stat_ok(self, engine, player, stat, target):
        dice = max(1, min(8, engine._effective_stat(player, stat) + engine._check_bonus(player, stat)))
        return engine.roll_dice(dice, f"任务检定·{stat}") >= target

    def _room_has_all(self, engine, room_key, card_ids):
        present = set(engine.state.room_items.get(room_key, []))
        for p in engine.state.players:
            if p.room_key == room_key and not p.dead:
                present.update(p.items)
        return all(cid in present for cid in card_ids)

    def _pay_cards_in_room(self, engine, room_key, card_ids):
        return

    def _restore_physical(self, engine, player):
        face = engine.catalog.characters.get(player.character_id)
        if face is None:
            return
        for stat in ("speed", "might"):
            initial = face.stats.get(stat)
            track = engine._stat_track(player, stat)
            if track and initial is not None:
                idx = min(range(len(track)), key=lambda i: abs(track[i] - initial))
                if player.stat_positions.get(stat, 0) < idx:
                    player.stat_positions[stat] = idx
                    player.stats[stat] = track[idx]
                    engine._log(f"{player.name} 的{stat}恢复到初始值 {track[idx]}。")

    # ------------------------------------------------------------- 偷窃 / 转折

    def _can_steal_traitor(self, engine, player):
        if player.role != "hero" or player.dead or getattr(player, "attack_used", False):
            return False
        traitor = self._traitor(engine)
        return traitor is not None and traitor.room_key == player.room_key and bool(self._stealable(engine, traitor))

    def _stealable(self, engine, traitor):
        out = []
        for card_id in traitor.items:
            card = engine.catalog.cards.get(card_id)
            if card is None:
                continue
            if (card.tradeable or card_id in self.COMPANIONS) and engine.item_action_available(card_id):
                out.append(card_id)
        return out

    def _steal_traitor(self, engine, player):
        if not self._can_steal_traitor(engine, player):
            return False
        traitor = self._traitor(engine)
        candidates = self._stealable(engine, traitor)
        if getattr(player, "control", "") == "bot" or len(candidates) == 1:
            flags = engine._haunt_flags()
            completed = {int(qid) for qid in flags.get("completed_quests", [])}
            needed = {card for qid in flags.get("obtained_quests", [])
                      if int(qid) not in completed
                      for card in self._missing_quest_cards(player, int(qid))}
            steal_id = next((card for card in candidates if card in needed), candidates[0])
        else:
            names = [engine.catalog.cards[c].name for c in candidates]
            idx = engine.prompter.choose_from_list("偷窃", "要偷哪一件？", names)
            if idx is None:
                return False
            steal_id = candidates[idx]
        traitor.items.remove(steal_id)
        player.items.append(steal_id)
        engine._mark_item_action(steal_id, "steal")
        if steal_id in getattr(traitor, "companions", []):
            traitor.companions.remove(steal_id)
        if "companion" in engine.catalog.cards[steal_id].tags and steal_id not in player.companions:
            player.companions.append(steal_id)
        player.attack_used = True
        engine._log(f"{player.name} 从入定的 {traitor.name} 身上拿走了 {engine.catalog.cards[steal_id].name}。")
        return True

    def _can_twist(self, engine, player):
        if player.role != "traitor" or player.dead:
            return False
        flags = engine._haunt_flags()
        if int(flags.get("body_tokens") or 0) < 1:
            return False
        used = set(flags.get("used_twists") or [])
        return any(t not in used and t not in {"evil_luck", "critical_lapse"} for t in self.TWISTS)

    def _do_twist(self, engine, player, data):
        if not self._can_twist(engine, player):
            return False
        flags = engine._haunt_flags()
        used = list(flags.get("used_twists") or [])
        remaining = [t for t in self.TWISTS if t not in used and t not in {"evil_luck", "critical_lapse"}]
        remaining = [t for t in remaining if self._twist_possible(engine, t)]
        if not remaining:
            return False
        if getattr(player, "control", "") == "bot":
            choice = remaining[0]
        else:
            labels = [self.TWIST_LABELS[t] for t in remaining]
            idx = engine.prompter.choose_from_list("剧情转折", "要用哪一种？", labels)
            if idx is None:
                return False
            choice = remaining[idx]
        return self._resolve_twist(engine, player, choice)

    def _twist_possible(self, engine, twist):
        if twist == "revival":
            return any(m.stunned_turns > 0 for m in engine.state.monsters)
        if twist == "ambush":
            return bool(engine.state.monsters) and bool(engine.state.board)
        if twist == "collapsing_floor":
            return any(p.role == "hero" and not p.dead for p in engine.state.players)
        if twist == "daze":
            return any(p.role == "hero" and not p.dead for p in engine.state.players)
        return True

    def _resolve_twist(self, engine, player, twist):
        flags = engine._haunt_flags()
        flags["body_tokens"] = int(flags.get("body_tokens") or 0) - 1
        used = list(flags.get("used_twists") or [])
        used.append(twist)
        flags["used_twists"] = used
        if twist == "lengthy_narration":
            flags["skip_next_advance"] = True
            engine._log("叙事变得冗长——下一次故事不会往前翻。")
        elif twist == "time_flies":
            engine._log("时光飞逝。")
            self._advance_story(engine)
        elif twist == "revival":
            stunned = [m for m in engine.state.monsters if m.stunned_turns > 0]
            if stunned:
                stunned[0].stunned_turns = 0
                engine._log(f"{stunned[0].name} 被故事唤醒了。")
        elif twist == "ambush":
            monster = engine._monster_by_template(self.SPIDER) or (engine.state.monsters[0] if engine.state.monsters else None)
            hero = next((p for p in engine.state.players if p.role == "hero" and not p.dead), None)
            if monster is not None and hero is not None:
                monster.room_key = hero.room_key
                engine._log(f"{monster.name} 被埋伏到了 {hero.name} 所在的房间。")
        elif twist == "collapsing_floor":
            hero = next((p for p in engine.state.players if p.role == "hero" and not p.dead), None)
            if hero is not None:
                here = engine.state.board.get(hero.room_key)
                if here is not None:
                    below = [k for k, r in engine.state.board.items() if r.floor == here.floor - 1]
                    if below:
                        hero.room_key = sorted(below)[0]
                        engine._log(f"{hero.name} 从塌陷的地板掉到了 {engine.state.board[hero.room_key].name}。")
        elif twist == "daze":
            hero = next((p for p in engine.state.players if p.role == "hero" and not p.dead), None)
            if hero is not None:
                dazed = [int(x) for x in (flags.get("dazed") or [])]
                dazed.append(hero.id)
                flags["dazed"] = dazed
                engine._log(f"{hero.name} 被故事弄得晕头转向。")
        return True

    def _bot_auto_twist(self, engine, player):
        flags = engine._haunt_flags()
        if int(flags.get("body_tokens") or 0) < 1:
            return
        used = set(flags.get("used_twists") or [])
        needed = max(1, int(flags.get("initial_hero_count") or 1))
        done = len(flags.get("completed_quests") or [])
        order = []
        if done >= needed and "lengthy_narration" not in used:
            order.append("lengthy_narration")
        elif done < needed and "time_flies" not in used:
            order.append("time_flies")
        if "ambush" not in used:
            order.append("ambush")
        if "revival" not in used:
            order.append("revival")
        for twist in order:
            if int(flags.get("body_tokens") or 0) < 1:
                return
            if not self._twist_possible(engine, twist):
                continue
            self._resolve_twist(engine, player, twist)
            return

    # ------------------------------------------------------------- 怪物

    def _witch_attack(self, engine, monster):
        heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead and p.room_key == monster.room_key]
        if not heroes:
            return True
        target = min(heroes, key=lambda p: (min(p.stats.get("might", 9), p.stats.get("sanity", 9)), p.id))
        attr = "sanity" if target.stats.get("sanity", 9) <= target.stats.get("might", 9) else "might"
        monster_roll = engine._roll_monster_attack(monster, attr)
        hero_roll = engine._roll_attack(target, attr)
        engine._log(f"{monster.name} 以{attr}攻击 {engine._player_label(target)}：{monster_roll} 对 {hero_roll}。")
        if monster_roll > hero_roll:
            dtype = "mental" if attr == "sanity" else "physical"
            engine._deal_damage(target, dtype, monster_roll - hero_roll, source=monster.name)
        elif monster_roll < hero_roll:
            engine._stun_monster(monster, 1)
        else:
            engine._log("平手。")
        return True

    def _dragon_breath(self, engine, monster):
        occupants = [
            p for p in engine.state.players
            if not p.dead and p.room_key == monster.room_key and p.role != "traitor"
        ]
        others = [m for m in engine.state.monsters if m is not monster and m.room_key == monster.room_key]
        if not occupants and not others:
            return True
        dragon_roll = engine._roll_monster_attack(monster, "might")
        engine._log(f"{monster.name} 喷出火焰（{dragon_roll}）。")
        for hero in occupants:
            speed_roll = engine._roll_attack(hero, "speed")
            if speed_roll < dragon_roll:
                engine._deal_damage(hero, "physical", dragon_roll - speed_roll, source="龙焰")
            else:
                engine._log(f"{hero.name} 躲开了龙焰。")
        for other in others:
            speed_roll = engine.roll_dice(max(1, int(getattr(other, "speed", 1))), "躲避龙焰")
            if speed_roll < dragon_roll:
                engine._stun_monster(other, 1)
        return True

    def _venom_stat(self, engine, target):
        order = ("might", "speed", "sanity", "knowledge")
        living = [s for s in order if target.stats.get(s, 0) > 0]
        if not living:
            return "might"
        return min(living, key=lambda s: target.stats.get(s, 0))

    def _traitor(self, engine):
        return next((p for p in engine.state.players if p.role == "traitor" and not p.dead), None)

    def _holder(self, engine, card_id):
        return next((p for p in engine.state.players if card_id in p.items and not p.dead), None)

    def _first_room(self, engine, template_ids):
        for tid in template_ids:
            key = next((k for k, r in engine.state.board.items() if r.template_id == tid), None)
            if key:
                return key
        return None

    def _any_room(self, engine):
        traitor = self._traitor(engine)
        if traitor is not None:
            return traitor.room_key
        return next(iter(engine.state.board))
