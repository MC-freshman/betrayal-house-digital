"""ShadowExorcismMode（剧本 43）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    _monster_id,
)


class ShadowExorcismMode(GenericModeHandler):
    """剧本 43 影子集会（A Gathering of Shadows）。

    权威原文：英雄手册 p54 / 叛徒手册 p125。

    · 影子（ghost 模板承载，Speed 3）：每个英雄一只，"绑定"关系存
      flags["shadow_bound"]（{monster_id: hero_id}）。影子自动向五芒星
      室移动（p125 traitor moves Shadows toward Pentagram Chamber）。
    · 五芒星室强制入场（_ensure_room_in_play）。
    · 影子进入五芒星室 → 对应英雄变成 Specter（死亡，p54）。
    · 攻击影子：Speed/Sanity 攻击，击败 → 击晕 + 绑定英雄 -1 Speed
      （p54 "the hero bound to that Shadow takes 1 point of Speed damage"）。
    · 光明仪式：①知识 4+ 在地窖/教堂/图书馆/实验室找仪式 →
      ②知识/理智 5+ 在阳台/花园/墓地/庭院/塔楼放仪式令牌；
      每房一次；玩家数枚 → 英雄胜。
    · 机器人（M10-53 修）：仪式检定成功后由 handler 亲自落令牌，并把
      `ritual_rooms_used` 记进旗标——引擎的通用成功路径只推进轨道、**从不落
      令牌**，而本 handler 的胜负判定数的正是令牌：修前英雄胜线永远不成立
      （探针 18/18 全败，追踪实测某局 7 次检定成功却判不出胜负）。
      `bot_attack_blocked` 拦掉"拿命换击晕"的影子攻击（修前 18 局 120 次，
      每局都有人速度归零而死）。
    · 已知简化：蜡烛移动影子 2 格未建模；影子沿墙爬未逐格建模，用
      `roll_dice(速度) // 2` 近似（见 on_monster_move 注释）。
    """

    mode = "shadow_exorcism"

    SHADOW = "ghost"
    # p54 的外缘房间只有这五间，且每间只能用一次；6 人局需要的令牌数
    # （等于玩家数）超过可用房间数，按原文无解——目标在 setup 里封顶。
    RITUAL_ROOMS = ["balcony", "garden", "graveyard", "patio", "tower"]

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags["shadow_bound"] = {}
        flags.setdefault("pentagram_reached", [])
        flags.setdefault("ritual_rooms_used", [])
        # p54：五芒星室强制入场
        engine._ensure_room_in_play("pentagram_chamber", room_key)
        pentagram = next(
            (k for k, r in engine.state.board.items() if r.template_id == "pentagram_chamber"),
            room_key,
        )
        flags["pentagram_room"] = pentagram
        # 每个英雄一只影子
        spec = next(
            (s for s in haunt.rule_data.get("monsters", []) if s.get("template_id") == self.SHADOW),
            {},
        )
        spec = dict(spec)
        spec["name"] = "影子"
        spec["speed"] = 3
        bound = flags.setdefault("shadow_bound", {})
        for hero in engine.state.players:
            if hero.role != "hero" or hero.dead:
                continue
            monster = engine._spawn_single_haunt_monster(spec, hero.room_key)
            if monster is not None:
                bound[str(monster.id)] = hero.id
        engine._log(f"{len(bound)} 道影子从探险者身上剥离——它们在向五芒星室飘去！")
        # p54 只列了五间外缘房（阳台/花园/墓地/庭院/塔楼），每间只能用一次：
        # 6 人局按"令牌数 = 玩家数"需要 6 枚，原文口径下无解。目标封顶到
        # 可用房间数，5-6 人局的进度条与实际需求才对得上。
        track = engine._haunt_tracks().get("ritual_progress")
        if track is not None:
            track["target"] = min(int(track.get("target", 0)), len(self.RITUAL_ROOMS))

    # ------------------------------------------------------------- 内部
    def _pentagram(self, engine: Any) -> str | None:
        return engine._haunt_flags().get("pentagram_room")

    def _bound_hero(self, engine: Any, monster: Any) -> Any | None:
        hid = engine._haunt_flags().get("shadow_bound", {}).get(str(getattr(monster, "id", "")))
        return next((p for p in engine.state.players if p.id == hid), None)

    # ------------------------------------------------------------- 影子移动
    def on_monster_move(self, engine: Any, monster: Any, rolled: int) -> bool:
        if _monster_id(monster) != self.SHADOW:
            return False
        pentagram = self._pentagram(engine)
        if not pentagram:
            return False
        if monster.room_key == pentagram:
            # 已到达：检查 Specter 转换
            hero = self._bound_hero(engine, monster)
            if hero is not None and not hero.dead:
                hero.dead = True
                engine._log(f"{hero.name} 的影子在五芒星室——{hero.name} 变成了 Specter！")
                engine.check_victory()
            return True
        path = engine._shortest_path(monster.room_key, pentagram)
        if len(path) > 1:
            # p125：影子是**沿墙**爬的——绕一个拐角算一格、穿过门到另一侧墙
            # 再算一格，一间房大约要花 2-3 格；Speed 5 折合每回合 1-2 间。
            # 旧实现按房间图直接走 roll_dice(3)（均 3 间/回合）快了一倍多：
            # M10-53 实测揭示后 3-12 个玩家回合内就有英雄变成 Specter，而窗口
            # 内仪式尝试只有 0-2 次——英雄连"找仪式 + 走过去"的回合都不够。
            # 折半是对沿墙爬的近似（18 局口径：英雄 0→2 胜，进度常见 3/3、4/4）。
            steps = engine.roll_dice(getattr(monster, "speed", 3), "影子移动") // 2
            monster.room_key = path[min(len(path) - 1, steps)]
            engine._log(f"影子飘到了{engine.state.board[monster.room_key].name}。")
        if monster.room_key == pentagram:
            hero = self._bound_hero(engine, monster)
            if hero is not None and not hero.dead:
                hero.dead = True
                engine._log(f"{hero.name} 的影子到达了五芒星室——{hero.name} 变成了没有灵魂的 Specter！")
                engine.check_victory()
        return True

    # ------------------------------------------------------------- 攻击
    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """p54：击败影子 → 击晕 + 绑定英雄 -1 Speed。"""
        if _monster_id(monster) != self.SHADOW:
            return False
        hero = self._bound_hero(engine, monster)
        if hero is not None and not hero.dead:
            engine._apply_stat_loss(hero, "speed", 1)
            engine._log(f"{hero.name} 的影子被驱散，但TA失去了 1 点 Speed。")
        return False  # 默认击晕

    # ------------------------------------------------------------- 光明仪式
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        """p54：每个外缘房间只能用一次——用过的房间不再提供仪式检定。"""
        used = set(engine._haunt_flags().get("ritual_rooms_used", []))
        result = []
        for action in super().available_actions(engine, player):
            if action.id == "ritual_roll" and engine._current_room_template_id(player) in used:
                continue
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        """仪式检定成功后由 handler 落令牌。

        引擎的通用成功路径（`_apply_generic_haunt_success`）只推进 `progress`
        轨道、写旗标，**不会生成检定令牌**；而本 handler 的胜负判定数的就是
        `sanity_check` / `knowledge_check` 令牌——不补这一步，英雄胜线永远
        不成立（M10-53 修前探针 18/18 全败）。
        """
        if action_id != "ritual_roll":
            return super().perform_action(engine, player, action_id, data)
        flags = engine._haunt_flags()
        room_id = engine._current_room_template_id(player)
        used = set(flags.get("ritual_rooms_used", []))
        if room_id not in self.RITUAL_ROOMS or room_id in used:
            engine._log("这个房间不能用于仪式（或已被使用）。")
            return False
        ok = super().perform_action(engine, player, action_id, data)
        if ok and engine.last_haunt_action_succeeded():
            used.add(room_id)
            flags["ritual_rooms_used"] = sorted(used)
            # 令牌种类跟行动实际用的属性走（rule_data 声明 knowledge/sanity，
            # 引擎取玩家较高的那一项）——与 p54"用哪项就放哪种令牌"一致。
            chosen = max(
                ("knowledge", "sanity"),
                key=lambda stat: engine._effective_stat(player, stat),
            )
            kind = "knowledge_check" if chosen == "knowledge" else "sanity_check"
            engine.spawn_token(kind, label="仪式成功", role="check", room_key=player.room_key)
        return ok

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        # p54：仪式令牌数 = 玩家数 → 英雄胜（封顶在可用外缘房间数，见 setup）
        need = min(len(engine.state.players), len(self.RITUAL_ROOMS))
        tokens = engine.tokens_of_kind("sanity_check") + engine.tokens_of_kind("knowledge_check")
        if len(tokens) >= need:
            engine._set_winner("heroes", "光明仪式完成——所有影子在圣光中消散了！")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "所有的影子都找到了它们的主人——在五芒星室里。")
            return True
        # 吸收引擎「叛徒死亡→英雄胜」兜底：p54/p125 只认"光明仪式完成"，
        # 影子不随叛徒死亡停下。
        if not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            return True
        return False

    # ------------------------------------------------------------- 机器人
    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        """p54：英雄胜 = 光明仪式满员，别把回合花在打影子上。

        ① 仪式还没找到 → 去地窖/教堂/图书馆/研究实验室（知识 4+）；
        ② 找到了 → 去还没用过的外缘房（阳台/花园/墓地/庭院/塔楼）。
        """
        if player.dead or player.role != "hero":
            return []
        flags = engine._haunt_flags()
        if not flags.get("ritual_found"):
            rooms = ["catacombs", "chapel", "library", "research_laboratory"]
        else:
            used = set(flags.get("ritual_rooms_used", []))
            rooms = [template_id for template_id in self.RITUAL_ROOMS if template_id not in used]
        goals: list[str] = []
        for template_id in rooms:
            key = next(
                (k for k, room in engine.state.board.items() if room.template_id == template_id),
                None,
            )
            if key:
                goals.append(f"__room__{key}")
        return goals

    def bot_wants_explore(self, engine: Any, player: Any) -> bool:
        """仪式已找到、但还有外缘房没翻进场时，得靠探索把它们翻出来。"""
        if player.dead or player.role != "hero":
            return False
        flags = engine._haunt_flags()
        if not flags.get("ritual_found"):
            return False
        in_play = {room.template_id for room in engine.state.board.values()}
        if not [template_id for template_id in self.RITUAL_ROOMS if template_id not in in_play]:
            return False
        return any(engine.has_remaining_room_cards(floor) for floor in (-1, 0, 1))

    def bot_attack_blocked(self, engine: Any, attacker: Any, target: Any) -> bool:
        """p54：击败影子的代价是**绑定英雄** -1 速度，而速度归零即死。

        修前实测（18 局）：英雄对影子出手 120 次，每局都有人因速度归零而死，
        仪式进度停在 0-3 —— 拿命换"击晕影子一回合"不是人打的牌。只有两种
        情况值得出手：① 影子马上要飘进五芒星室（那一下不挡，绑定英雄直接
        变 Specter）；② 自己速度 ≥2（打得起这 1 点）。速度 ≤1 时打赢也是自杀。
        """
        if _monster_id(target) != self.SHADOW:
            return False
        speed = int(getattr(attacker, "stats", {}).get("speed", 0))
        if speed <= 1:
            return True
        pentagram = self._pentagram(engine)
        if pentagram and engine._path_length(target.room_key, pentagram) <= 2:
            return False
        return True

    # ------------------------------------------------------------- 进度摘要
    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        """公开信息：仪式是否找到 + 已用/可用的外缘房间（p54 令牌摆在板块上）。"""
        flags = engine._haunt_flags()
        used = sorted(set(flags.get("ritual_rooms_used", [])))
        need = min(len(engine.state.players), len(self.RITUAL_ROOMS))
        found = "仪式已找到" if flags.get("ritual_found") else "仪式尚未找到（地窖/教堂/图书馆/实验室 知识 4+）"
        names = [
            engine.state.board[key].name
            for key in sorted(engine.state.board)
            if engine.state.board[key].template_id in self.RITUAL_ROOMS
        ]
        lines = [f"{found}；光明仪式 {len(used)}/{need} 枚令牌。"]
        if names:
            lines.append("可用于仪式的房间：" + "、".join(names) + "（每间只能用一次）。")
        return lines
