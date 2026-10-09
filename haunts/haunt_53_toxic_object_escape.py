"""ToxicObjectEscapeMode（剧本 53）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
)


class ToxicObjectEscapeMode(GenericModeHandler):
    """剧本 53 死亡恶臭（Reeking of Death）。

    权威原文：英雄手册 p64 / 叛徒手册 p135。
    · 死亡之物：狗携带（Speed 6 Might 4）；可被偷/掉落。
    · 毒云：有物之房间放 token；进入掷骰（2 无/1 -1 物理/0 -1 物理-1 精神）；
      回合结束在有物或毒云房间 -1 全属性。
    · 逃跑：清障碍（力量 4+，人数次）→ 解锁（知识 5+）→ 逃离（2 格移动）。
    · 净化：在熔炉房/地下湖开始回合持物。
    · 英雄胜：半数逃出 或 净化+半数存活；叛徒胜：英雄全灭。
    · 简化：狗掉落物品（2+ 物理伤害）未建模；毒云逐回合扩展未建模。
    """

    mode = "toxic_object_escape"

    def setup(self, engine, haunt, room_key):
        flags = engine._haunt_flags()
        flags["object_cleansed"] = False
        flags["door_unlocked"] = False
        flags["escaped"] = []
        # p64：障碍计数目标是"作祟开始时的英雄数"。原实现用 rule_data 的
        # `player_count`，把叛徒也算了进去 ⇒ 每局多要一次力量 4+，障碍几乎永远
        # 清不完（18 局探针 14 局卡在 0-3 / 4-6，`unlock_door` 出现 2-21 次却一次
        # 都没轮到——`clear_barricade` 因为"进度未满"一直存在且排在前）。
        heroes = sum(1 for p in engine.state.players if p.role == "hero")
        track = engine._haunt_tracks().setdefault(
            "barricade_tokens", {"label": "已清除障碍", "target": heroes, "value": 0}
        )
        track["target"] = heroes
        # p64：逃出线的目标是 ceil(作祟开始时英雄数/2)（"at least half of the
        # heroes escape"），与 check_victory 的 need 保持一致；rule_data 里的
        # `half_players_ceil` 按"全体玩家"算，3 人局会多要 1 人。
        escape_need = -(-heroes // 2)
        engine._haunt_tracks().setdefault(
            "escaped_count", {"label": "已逃出英雄", "target": escape_need, "value": 0}
        )["target"] = escape_need
        # p135：死亡之物开局**在叛徒手里**（"The object given to you by the dog …
        # is initially in your possession"）。旧实现把 holder 写成"怪物 id 的数字
        # 后缀"（mon_1 → 玩家 1），与阵营无关，等于随机挂在某个玩家身上。
        holder = next(
            (p.id for p in engine.state.players if p.role == "traitor"), None
        )
        engine.spawn_token(
            "deathly_object", label="死亡之物", role="carried", holder=holder
        )
        engine._log("狗把死亡之物叼给了叛徒——恶臭开始在宅子里弥漫！")

    def _object_token(self, engine):
        return next(
            (t for t in engine.state.tokens if t.kind == "deathly_object"), None
        )

    def on_player_died(self, engine, player):
        """p135：死亡之物可以掉落——携带者倒下时它留在原地等人捡。"""
        token = self._object_token(engine)
        if token is None or token.holder != player.id:
            return
        token.holder = None
        token.room_key = player.room_key
        engine._log(
            f"死亡之物从{engine._player_label(player)}手中滚落，掉在"
            f"{engine.state.board[player.room_key].name if player.room_key in engine.state.board else '地上'}。"
        )

    def on_turn_start(self, engine, player):
        flags = engine._haunt_flags()
        if player.dead or player.role == "traitor":
            return
        # 毒云伤害：回合结束在有物或毒云房间
        obj_room = self._object_room(engine)
        poison_rooms = {
            t.room_key for t in engine.state.tokens if t.kind == "poison_cloud"
        }
        if obj_room and (player.room_key == obj_room or player.room_key in poison_rooms):
            for stat in ("speed", "might", "sanity", "knowledge"):
                engine._apply_stat_loss(player, stat, 1)
            engine._log(f"{player.name} 在毒气中失去了 1 点全属性。")
            engine.check_victory()

    def on_enter_room(self, engine, player, room):
        if player.dead or player.role == "traitor":
            return
        # p135：死亡之物"may be dropped, traded, or stolen like a regular item"——
        # 它掉在房间里时（携带者倒下），走进来的英雄顺手捡起。这是净化线在
        # "叛徒持有"口径下唯一的入口（旧实现只有 id 恰好等于狗 id 后缀的那名
        # 玩家能净化，与阵营无关）。
        if not engine.tokens_held_by(player.id, "deathly_object"):
            dropped = next(
                (
                    t
                    for t in engine.tokens_in_room(room.key, "deathly_object")
                    if t.holder is None
                ),
                None,
            )
            if dropped is not None:
                dropped.holder = player.id
                dropped.room_key = ""
                engine._log(f"{player.name} 捡起了死亡之物——它冷得像块墓碑。")
        obj_room = self._object_room(engine)
        poison_rooms = [t.room_key for t in engine.state.tokens if t.kind == "poison_cloud"]
        if room.key == obj_room or room.key in poison_rooms:
            roll = engine.roll_dice(1, "毒云")
            if roll == 0:
                engine._apply_stat_loss(player, "might", 1)
                engine._apply_stat_loss(player, "sanity", 1)
                engine._log(f"{player.name} 吸入毒气（-1 物理 -1 精神）。")
            elif roll == 1:
                engine._apply_stat_loss(player, "might", 1)
                engine._log(f"{player.name} 吸入毒气（-1 物理）。")
            else:
                engine._log(f"{player.name} 屏住了呼吸。")
            engine.check_victory()

    def _object_room(self, engine):
        for t in engine.state.tokens:
            if t.kind == "deathly_object":
                if t.holder is not None:
                    p = next((p for p in engine.state.players if p.id == t.holder), None)
                    return p.room_key if p else None
                return t.room_key
        return None

    def available_actions(self, engine, player):
        actions = super().available_actions(engine, player)
        result = []
        flags = engine._haunt_flags()
        for action in actions:
            if action.id == "cleanse_object":
                room_id = engine._current_room_template_id(player)
                if room_id not in ("furnace_room", "underground_lake"):
                    continue
                if not engine.tokens_held_by(player.id, "deathly_object"):
                    continue
            elif action.id == "unlock_door":
                # p64："You must **then** unlock the door…"——障碍清完才轮到解锁。
                # 旧门禁只查 door_unlocked=False，于是障碍没清完也照样把解锁摆在
                # 英雄面前：6 人局实测 clear_barricade 反复失败时 unlock_door
                # 出现 7-19 次却一次没轮到（探针报"行动空转"）。
                target = engine._haunt_track_target("barricade_tokens")
                if target <= 0 or engine._haunt_track_value("barricade_tokens") < target:
                    continue
            result.append(action)
        return result

    def perform_action(self, engine, player, action_id, data):
        flags = engine._haunt_flags()
        if action_id == "flee_house":
            escaped = flags.setdefault("escaped", [])
            if player.id not in escaped:
                escaped.append(player.id)
                engine._advance_haunt_track("escaped_count")  # UI 轨道与旗标同步
                engine._log(f"{player.name} 冲出了前门！")
            engine.check_victory()
            return True

        if action_id == "cleanse_object":
            if not engine.tokens_held_by(player.id, "deathly_object"):
                engine._log("你身上没有死亡之物。")
                return False
            token = next(iter(engine.tokens_held_by(player.id, "deathly_object")), None)
            if token:
                engine.remove_token(token.uid)
            flags["object_cleansed"] = True
            engine._log("死亡之物被净化了——诅咒结束了！")
            engine.check_victory()
            return True

        if action_id == "unlock_door":
            ok = super().perform_action(engine, player, action_id, data)
            if ok and engine.last_haunt_action_succeeded():
                flags["door_unlocked"] = True
                engine._log("前门解锁了！")
            return ok

        return super().perform_action(engine, player, action_id, data)

    def check_victory(self, engine):
        import math
        flags = engine._haunt_flags()
        heroes_start = sum(1 for p in engine.state.players if p.role == "hero")
        escaped = len(flags.get("escaped", []))
        need = math.ceil(heroes_start / 2)
        cleansed = flags.get("object_cleansed", False)
        heroes_alive = sum(1 for p in engine.state.players if p.role == "hero" and not p.dead)

        if cleansed and heroes_alive >= need:
            engine._set_winner("heroes", "死亡之物被净化了——毒气消散了。")
            return True
        if escaped >= need:
            engine._set_winner("heroes", "半数英雄逃出了前门——他们得救了。")
            return True
        # p135：叛徒胜 = **超过半数**英雄死亡（"…more than half of the heroes are
        # dead"）。旧实现写成"全灭"，与原文偏差一档：3 名英雄里死 2 人、4 名里死
        # 3 人时就该收场（`heroes_alive * 2 < heroes_start`）。
        if heroes_alive * 2 < heroes_start:
            engine._set_winner("traitor", "超过半数的继承人倒下了——毒气吞噬了他们。")
            return True
        return True  # 吸收引擎"叛徒死亡即英雄胜"兜底（p135：叛徒死不触发英雄胜）

    # ------------------------------------------------------------- 机器人
    def _best_melee_dice(self, engine: Any, player: Any) -> int:
        """这名英雄用最趁手的近战武器能掷几枚骰（力量 + 武器加成）。"""
        might = int((getattr(player, "stats", {}) or {}).get("might", 0))
        best = might
        for card_id in getattr(player, "items", []):
            card = engine.catalog.cards.get(card_id)
            if card is None or "weapon" not in card.tags or "ranged" in card.tags:
                continue
            best = max(best, might + int((card.bonus or {}).get("attack", 0)))
        return best

    def _has_ranged_weapon(self, engine: Any, player: Any) -> bool:
        for card_id in getattr(player, "items", []):
            card = engine.catalog.cards.get(card_id)
            if card is not None and "weapon" in card.tags and "ranged" in card.tags:
                return True
        return False

    def bot_attack_blocked(self, engine: Any, player: Any, target: Any) -> bool:
        """p64/p135：英雄的胜线是**逃出前门**或**净化死亡之物**——打架换不来胜利。

        实测（seed113/6p 逐回合）：英雄死因是自己的送死攻击——`攻击 地狱犬：2 对 5
        → 受 3 点`、被"叛徒+犬"夹击。规则里狗既不携带死亡之物（p135：物在叛徒手上）、
        也不参与任何胜负判定，打它纯属白送；打叛徒的唯一意义是把死亡之物夺过来
        （另走 `special_steal`），所以要有把握才出手（近战骰数 > 其力量，或持远程武器）。
        """
        if getattr(player, "role", None) != "hero":
            return False
        if getattr(target, "template_id", "") == "dog":
            return True  # 打狗毫无收益：它不携带死亡之物，胜线里也没有它
        if getattr(target, "role", None) != "traitor":
            return False
        if self._has_ranged_weapon(engine, player):
            return False
        return self._best_melee_dice(engine, player) <= int(
            (getattr(target, "stats", {}) or {}).get("might", 0)
        )

    def special_steal(
        self, engine: Any, attacker: Any, target: Any, diff: int, attack_attr: str
    ) -> bool:
        """p135：死亡之物"may be dropped, traded, or stolen like a regular item"。

        实现里它是**令牌**而非卡牌，引擎的通用偷窃通道（只认 `target.items`）看不到
        它——于是"物在叛徒手里"就等于净化线整条不可达（旧实现还把 holder 写成随机
        玩家 id，更没人能净化）。这里按剧本钩子补上：攻击持有者并以 >2 优势获胜
        （引擎只在 diff > 2 时调用本钩子）即夺走。
        """
        if getattr(attacker, "role", None) != "hero":
            return False
        token = self._object_token(engine)
        if token is None or token.holder != getattr(target, "id", None):
            return False
        token.holder = getattr(attacker, "id", None)
        token.room_key = ""
        engine._log(
            f"{engine._player_label(attacker)} 从{engine._player_label(target)}"
            f"手里夺下了死亡之物——恶臭换了个主人。"
        )
        return True

    # ------------------------------------------------------------- bot 寻路
    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        """p64：英雄胜 = 半数逃出前门 或 净化死亡之物(熔炉房/地下湖)+半数存活。
        引导（动态）：
        ① 已净化→无需再移动，返回空（靠存活凑半数）；
        ② 本英雄持死亡之物→去熔炉房/地下湖净化（最稳的取胜线）；
        ③ 否则强化逃生路线（正门）——与 rule_data 的 flee 行动一致，不主动
           追狗（狗速 6，追它纯浪费回合；逃生前门更稳，且顺路也可能捡到掉落物）。
        注：实测 53 号此前靠"半数逃生"就能赢约六成，故 bot 寻路以逃生为基线、
        持物净化为加成，不强行改走更难的净化线。"""
        flags = engine._haunt_flags()
        if flags.get("object_cleansed"):
            return []
        # 持死亡之物→去熔炉房/地下湖净化
        if engine.tokens_held_by(player.id, "deathly_object"):
            for template_id in ("furnace_room", "underground_lake"):
                key = next(
                    (k for k, r in engine.state.board.items()
                     if r.template_id == template_id and not engine._is_collapsed(k)),
                    "",
                )
                if key:
                    return ["__room__" + key]
            return []
        # 否则：强化逃生路线（正门）
        front = next(
            (k for k, r in engine.state.board.items()
             if r.template_id == "entrance_hall" and not engine._is_collapsed(k)),
            "",
        )
        return ["__room__" + front] if front else []
