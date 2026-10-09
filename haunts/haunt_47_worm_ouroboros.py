"""OuroborosMode（剧本 47）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
)


class OuroborosMode(GenericModeHandler):
    """剧本 47「Worm Ouroboros / 衔尾蛇虫」（英雄手册 p58 / 叛徒手册 p129）。

    叛徒的身体从中线裂开，化作环绕世界的巨蛇闯入现实：双头各自游走，
    每离开一个房间就留下一节蛇身。16 节蛇身铺满全屋之日，就是宅子
    被碾碎之时。英雄必须先削弱、再围殴，赶在蛇长成之前斩下双头。

    · 开局（p129）：叛徒移出游戏——物品全部掉在揭示房、Girl/Dog/
      Madman 被蛇吞掉（直接弃置，不掉落）；两个蛇头放揭示房；
      16 节蛇身备用（flags 计数）。
    · 骷髅（p58）：英雄施咒要捡起叛徒掉落的骷髅（作祟由骷髅预兆触发
      时它就在叛徒手里）。强制触发的测试局叛徒未必持有——开局在
      揭示房补一张（28 号"无合格房时强行入场"同口径）。
    · 蛇头行动（p129）：每个蛇头单独掷 1 骰（0/1/2）定步数；走过的
      房间若无蛇身则放 1 节（每房限 1 枚、已放过的可穿过）；不能走
      密道/秘门/神秘电梯（门邻居天然排除前两者，电梯房显式排除）；
      探索者不影响蛇头移动；蛇头可以探索新房间并忽略符号抽牌。
    · 施咒（p58）：持骷髅者与蛇头同房间，每回合一次理智 5+——成功后
      该蛇头力量降为 5 且此后可被攻击（未施咒的蛇头 attack_allowed 拦截）。
    · 击杀（p58/p129）：施咒后每次击败 = 1 hit；每颗头需 hit 数 =
      玩家数的一半向上取整（3-4 人 2 次、5-6 人 3 次）。蛇头不可击晕
      ——on_monster_defeated 拦下击晕并计 hit，满数由 handler 杀死。
    · 免疫（p58/p129）：左轮与一切速度攻击无效（monster_specs immune_to）。
    · 胜负（p58/p129）：英雄胜 = 双头皆斩；叛徒胜 = 16 节蛇身全部进场。
      叛徒开局就出局（变蛇），必须吸收"叛徒死亡→英雄胜"兜底——
      老坑 #1 在本剧本必然触发（10 号同款）。

    已知简化：
        · 蛇头/蛇身对探索者移动的影响（p12 怪物阻挡口径）未建模——
          引擎没有"经过怪物房间受限"的移动层，蛇身只作记数与地图标记。
        · 蛇头探索新房间"掷出 2 时不因符号房间停止移动"自动满足
          （handler 放房不触发符号结算）。
        · 叛徒侧的 Turn/Damage Track 记 hit：本引擎用 flags dict 按蛇头
          id 计数（两只头各自独立），UI 进度以蛇身轨道呈现。
        · 骷髅兜底补牌不回记账目（直接放进房间物品，不从牌堆核销）。
    """

    mode = "worm_ouroboros"

    HEAD = "ouroboros_head"
    SKULL = "omen_skull"
    DEVOUR_CARDS = ("omen_dog", "omen_girl", "omen_madman")
    ELEVATOR = "mystic_elevator"
    BODY_TOTAL = 16
    DELTAS = {"north": (0, -1), "east": (1, 0), "south": (0, 1), "west": (-1, 0)}

    # ------------------------------------------------------------- 开局
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags.setdefault("weakened_heads", [])
        flags.setdefault("head_hits", {})
        players = len(engine.state.players)
        flags["hits_needed"] = -(-players // 2)  # ceil(p/2)：3-4 人 2 次、5-6 人 3 次
        flags["body_left"] = self.BODY_TOTAL

        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None:
            # p129：Girl/Dog/Madman 被蛇吞掉（直接弃置）——同伴类预兆卡
            # 在 items 与 companions 里都有记录，两边都要清。
            for cid in list(traitor.items):
                if cid in self.DEVOUR_CARDS:
                    traitor.items.remove(cid)
            for cid in list(traitor.companions):
                if cid in self.DEVOUR_CARDS:
                    traitor.companions.remove(cid)
            pile = engine.state.room_items.setdefault(room_key, [])
            pile.extend(traitor.items)
            traitor.items.clear()
            pile.extend(traitor.companions)
            traitor.companions.clear()
            traitor.dead = True
            engine._log("叛徒的身体从中线裂开——他已化作双头巨蛇，不再是玩家。")
            if self.SKULL not in pile and not any(
                self.SKULL in p.items for p in engine.state.players
            ):
                pile.append(self.SKULL)
                engine._log("叛徒掉落的物品里有一具骷髅——那是施咒的焦点。")

        for _ in range(2):
            engine._spawn_single_haunt_monster(
                {"template_id": self.HEAD, "name": "衔尾蛇头"}, room_key
            )
        engine._log("两条蛇头在房间里昂起，鳞片摩擦声充满了整栋房子。")

    # ------------------------------------------------------- 蛇头行动
    def _heads(self, engine: Any) -> list[Any]:
        return [m for m in engine.state.monsters if m.template_id == self.HEAD]

    def _drop_body(self, engine: Any, room_key: str) -> None:
        """蛇头离开的房间放 1 节蛇身（每房限 1 枚，p129）。"""
        flags = engine._haunt_flags()
        if int(flags.get("body_left", 0)) <= 0:
            return
        if any(
            t.kind == "ouroboros_body" and t.room_key == room_key
            for t in engine.state.tokens
        ):
            return
        flags["body_left"] = int(flags["body_left"]) - 1
        engine.spawn_token("ouroboros_body", label="蛇身", role="marker", room_key=room_key)
        engine._advance_haunt_track("ouroboros_body")

    def _head_discover(self, engine: Any, direction: str, from_room: Any) -> str | None:
        """蛇头探索新房间（忽略符号抽牌，p129）。bot 取首个可行放置。"""
        dx, dy = self.DELTAS[direction]
        target_pos = (from_room.floor, from_room.x + dx, from_room.y + dy)
        if target_pos in engine.state.pos_index:
            return engine.state.pos_index[target_pos]
        budget = len(engine.state.room_deck) + len(engine.state.room_discard) + 1
        while budget > 0:
            budget -= 1
            template = engine._draw_room_template(from_room.floor)
            if template is None:
                return None
            placements = engine._compute_explore_placements(template, direction, target_pos)
            if not placements:
                engine.state.room_discard.append(template.id)
                continue
            placement = placements[0]
            rotated = engine._build_rotated_template(template, placement["rotation"])
            new_room = engine._place_room(
                rotated, target_pos[1], target_pos[2], placement["rotation"]
            )
            engine._log(f"蛇头撞开了未知区域：{new_room.name}")
            return new_room.key
        return None

    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        if getattr(monster, "template_id", "") != self.HEAD:
            return False
        target = engine._find_monster_target(monster)
        steps = engine.roll_dice(monster.speed, "蛇头移动")
        visited = [monster.room_key]
        cur = monster.room_key
        for _ in range(steps):
            room = engine.state.board[cur]
            body_keys = {
                t.room_key for t in engine.state.tokens if t.kind == "ouroboros_body"
            }
            # 已探明门邻居（排除神秘电梯，密道/秘道不在门邻居里）
            known = [
                k
                for k in engine._door_neighbors(cur)
                if engine.state.board[k].template_id != self.ELEVATOR
            ]
            fresh = [k for k in known if k not in body_keys]  # 已探明、还没蛇身
            unknown_dirs = [
                d
                for d in sorted(room.doors)
                if self._pos_of(engine, room, d) is None
            ]  # 未探明的门：蛇头可以探索新房间（p129）
            dest: str | None = None
            if fresh:
                if target is not None:
                    dest = min(fresh, key=lambda k: engine._path_length(k, target.room_key))
                else:
                    dest = sorted(fresh)[0]
            elif unknown_dirs:
                new_key = self._head_discover(engine, unknown_dirs[0], room)
                if new_key is None:
                    # 牌堆放不出新房间：退回已放蛇身的房间游走
                    if not known:
                        break
                    dest = (
                        min(known, key=lambda k: engine._path_length(k, target.room_key))
                        if target is not None
                        else sorted(known)[0]
                    )
                else:
                    visited.append(new_key)
                    cur = new_key
                    monster.room_key = new_key
                    continue
            elif known:
                # 只剩已放蛇身的房间：可以穿过（不再放，p129）
                dest = (
                    min(known, key=lambda k: engine._path_length(k, target.room_key))
                    if target is not None
                    else sorted(known)[0]
                )
            else:
                break
            visited.append(dest)
            cur = dest
            monster.room_key = dest
        # p129：蛇头离开的房间放 1 节蛇身（终点不算离开）
        for key in visited:
            if key != monster.room_key:
                self._drop_body(engine, key)
        engine._log(f"{monster.name} 游到了{engine.state.board[monster.room_key].name}。")
        if target is not None and target.room_key == monster.room_key:
            engine._monster_attack(monster, target)
        return True

    def _pos_of(self, engine: Any, room: Any, direction: str) -> str | None:
        """房间某门方位对应的板块 key（未放房为 None）。"""
        dx, dy = self.DELTAS.get(direction, (0, 0))
        return engine.state.pos_index.get((room.floor, room.x + dx, room.y + dy))

    # ------------------------------------------------------------- 攻击
    def attack_allowed(self, engine: Any, attacker: Any, target: Any) -> bool:
        """p58：施放削弱咒之前不能攻击蛇头。"""
        if getattr(target, "template_id", "") == self.HEAD:
            if target.id not in set(engine._haunt_flags().get("weakened_heads", [])):
                return False
        return super().attack_allowed(engine, attacker, target)

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """p129：蛇头不可击晕——每次击败记 1 hit，满数即杀（p58）。"""
        if getattr(monster, "template_id", "") != self.HEAD:
            return False
        flags = engine._haunt_flags()
        hits = dict(flags.get("head_hits", {}))
        hits[monster.id] = int(hits.get(monster.id, 0)) + 1
        flags["head_hits"] = hits
        needed = int(flags.get("hits_needed", 2))
        if hits[monster.id] >= needed:
            engine._log(f"{monster.name} 轰然倒地——第 {hits[monster.id]}/{needed} 次重击奏效！")
            engine._kill_monster(monster)
        else:
            engine._log(f"{monster.name} 受创（{hits[monster.id]}/{needed}），但仍在扭动。")
        return True  # 不击晕、不默认离场——击杀由 handler 全权

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        result = []
        weakened = set(engine._haunt_flags().get("weakened_heads", []))
        for action in actions:
            # 已削弱的蛇头别再显示施咒
            if getattr(action, "id", "") == "cast_weakening_spell":
                if not any(
                    h.room_key == player.room_key and h.id not in weakened
                    for h in self._heads(engine)
                ):
                    continue
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "cast_weakening_spell":
            return self._cast_spell(engine, player)
        return super().perform_action(engine, player, action_id, data)

    def _cast_spell(self, engine: Any, player: Any) -> bool:
        """p58：持骷髅 + 蛇头同房 → 理智 5+，成功则该头力量降 5、可被攻击。"""
        if self.SKULL not in player.items:
            return False
        weakened = set(engine._haunt_flags().get("weakened_heads", []))
        targets = [
            h
            for h in self._heads(engine)
            if h.room_key == player.room_key and h.id not in weakened
        ]
        if not targets:
            return False
        head = targets[0]
        if len(targets) > 1 and getattr(player, "control", "bot") != "bot":
            idx = engine.prompter.choose_from_list(
                "削弱咒", "对哪颗蛇头施咒？", [f"蛇头 {i + 1}" for i in range(len(targets))]
            )
            if idx is not None and 0 <= idx < len(targets):
                head = targets[idx]
        ok = engine._resolve_check(player, "sanity", 5, "削弱咒")
        if not ok:
            engine._log(f"{engine._player_label(player)} 的咒文散在了空气里。")
            return False
        flags = engine._haunt_flags()
        flags["weakened_heads"] = sorted(weakened | {head.id})
        head.might = 5
        engine._log(f"咒文缠住了{head.name}——它的力量降到了 5，现在可以对它出手了！")
        return True

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        heroes_alive = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        # p129：16 节蛇身全部进场 → 叛徒胜
        if int(flags.get("body_left", self.BODY_TOTAL)) <= 0:
            engine._set_winner("traitor", "十六节蛇身环抱整栋房子——巨蛇开始收拢它的绞索。")
            return True
        # p58：双头皆斩 → 英雄胜
        if not self._heads(engine):
            engine._set_winner("heroes", "两条蛇头都被斩落——世界之蛇的入侵到此为止。")
            return True
        # 通用：英雄全灭 → 叛徒胜
        if not heroes_alive:
            engine._set_winner("traitor", "所有英雄都倒下了。")
            return True
        # 吸收兜底：叛徒开局变蛇出局（p129）——绝不能因此判英雄胜（10 号同款）
        return True

    # ------------------------------------------------------------- bot/UI
    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        if player.role != "hero":
            return []
        weakened = set(engine._haunt_flags().get("weakened_heads", []))
        # 追未削弱的蛇头施咒（骷髅掉在地上，bot 的关键牌拾取会顺路去拿）
        return [
            f"__room__{head.room_key}"
            for head in self._heads(engine)
            if head.id not in weakened
        ]

    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        flags = engine._haunt_flags()
        lines = []
        weakened = set(flags.get("weakened_heads", []))
        for head in self._heads(engine):
            state = "已削弱（力 5）" if head.id in weakened else "未削弱"
            hits = int(flags.get("head_hits", {}).get(head.id, 0))
            lines.append(f"{head.name}：{state}，受创 {hits}/{flags.get('hits_needed', '?')}。")
        placed = self.BODY_TOTAL - int(flags.get("body_left", self.BODY_TOTAL))
        lines.append(f"蛇身：{placed}/{self.BODY_TOTAL} 节。")
        return lines
