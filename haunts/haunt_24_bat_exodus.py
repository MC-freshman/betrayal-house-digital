"""BatSwarmMode（剧本 24）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    _is_last_in_round,
    _monster_id,
)


class BatSwarmMode(GenericModeHandler):
    """剧本 24 蝙蝠归巢（Fly Away Home）。

    权威原文：英雄手册 p35 / 叛徒手册 p106。

    已按原文实现：
        · 数值：蝙蝠 Speed 5 / Might 2 / Sanity 1（p106 页脚，新增 bat 模板——
          骨架此前用 spider 冒充蝙蝠）。
        · 开局：叛徒已死并移出对局；风琴房不在场就从牌堆找出来放上（p35）；
          塔楼或阁楼放 3 只、裂隙或地下墓穴放 3 只，两处都没发现就少放（p106
          "the haunt begins with fewer Bats"）。
        · 入室（p106）：每个怪物回合掷「玩家数」枚骰决定进入数量，入口为
          塔楼/裂隙/温室/门厅/花园/墓地/露台/阳台（有朝外窗的房间），每个入口
          一次只进一只，蝙蝠多于入口才轮着重复进；场内蝙蝠封顶 24 只。
        · 攻击（p106）：蝙蝠不做普通攻击——贴脸的蝙蝠每只掷 1 枚骰，掷出 2
          就贴到该探险者身上；贴附后不再移动也不再攻击。
        · 贴附代价（p35/p106）：宿主每回合开始按贴附数各受 1 点物理伤害，
          且每只贴附蝙蝠让宿主少走 1 格（至少保 1 格）；贴附的蝙蝠跟着宿主一起移动。
        · 英雄胜三步（p35，每步每回合只试一次）：① 风琴房力量 5+ 启动管风琴
          → ② 风琴房知识 6+ 奏出驱蝠之音，赶走所有未贴附的蝙蝠并封住入口
          → ③ 杀死仍贴在人身上的蝙蝠。
        · 力量攻击击败蝙蝠 = 直接杀死而非击晕（p35，走 monster_killed_on_defeat）。
        · 叛徒胜：所有英雄死亡。叛徒开局即死，吸收引擎"叛徒死亡即英雄胜"兜底
          （老坑第 14 次）。

    已知简化：
        · p35「持盔甲少受 1 点吸血伤害」由引擎既有的盔甲效果统一承担
          （本仓库的盔甲是"挡掉一次物理伤害"），比原文更强，不在剧本里另加减免
          ——两处都减会让盔甲把 2 点伤害全挡掉。
        · p35「爱好音乐的角色可用知识 5+ 代替 6+」未建模——本仓库角色数据里
          没有爱好（hobby）字段，需要先在 content.py 补爱好数据。
        · 「任何有朝外窗的房间」只按 p106 明列的八个入口判定，其余房间的窗户
          属性未建模。
        · 额外蝙蝠进哪个入口由确定性轮转决定，原版由叛徒任选。
    """

    mode = "bat_exodus"

    BAT = "bat"
    BAT_CAP = 24
    ENTRY_ROOMS = ("tower", "chasm", "conservatory", "entrance_hall", "garden", "graveyard", "patio", "balcony")
    START_SPOTS = (("tower", "attic"), ("chasm", "catacombs"))
    DAMAGE_SOURCE = "吸血蝙蝠"

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None:
            engine._drop_inventory_on_death(traitor)
            traitor.dead = True
            engine._log(f"{traitor.name}把窗户全部推开，把血交给了祂们。")
        engine._ensure_room_in_play("organ_room", room_key)  # p35
        engine._haunt_flags().setdefault("attached", {})
        spec = self._bat_spec(engine)
        released = 0
        for options in self.START_SPOTS:
            key = self._first_discovered(engine, options)
            if not key:
                continue  # p106：两处都没发现就少放蝙蝠
            for _ in range(3):
                if engine._spawn_single_haunt_monster(spec, key) is None:
                    break
                released += 1
        if released:
            engine._advance_haunt_track("bats_released", released)
        engine._log(f"{released} 只蝙蝠先从塔楼与地裂的方向落了进来。")

    def _first_discovered(self, engine: Any, template_ids: tuple[str, ...]) -> str:
        for template_id in template_ids:
            for key, room in engine.state.board.items():
                if room.template_id == template_id and room.revealed and not engine._is_collapsed(key):
                    return key
        return ""

    def _bat_spec(self, engine: Any) -> dict:
        specs = engine._haunt_rule_state().get("monster_specs", {})
        return dict(specs.get(self.BAT) or {"template_id": self.BAT, "name": "蝙蝠"})

    # ------------------------------------------------------------ 贴附状态
    def _bats(self, engine: Any) -> list[Any]:
        return [m for m in engine.state.monsters if _monster_id(m) == self.BAT]

    def _attached_map(self, engine: Any) -> dict:
        return engine._haunt_flags().setdefault("attached", {})

    def _attached_ids(self, engine: Any, player: Any) -> list[str]:
        return [str(i) for i in (self._attached_map(engine).get(str(player.id), []) or [])]

    def _host_of(self, engine: Any, bat: Any) -> Any | None:
        bat_id = str(getattr(bat, "id", ""))
        for pid, ids in self._attached_map(engine).items():
            if bat_id in [str(i) for i in (ids or [])]:
                return next((p for p in engine.state.players if str(p.id) == str(pid)), None)
        return None

    def _attach(self, engine: Any, bat: Any, player: Any) -> None:
        attached = self._attached_map(engine)
        ids = [str(i) for i in (attached.get(str(player.id), []) or [])]
        ids.append(str(bat.id))
        attached[str(player.id)] = ids
        bat.room_key = player.room_key
        engine._log(f"一只蝙蝠贴上了{player.name}，开始吸血。")

    def _drop_dead_bat(self, engine: Any, bat: Any) -> None:
        bat_id = str(getattr(bat, "id", ""))
        attached = self._attached_map(engine)
        for pid in list(attached):
            rest = [str(i) for i in (attached[pid] or []) if str(i) != bat_id]
            if rest:
                attached[pid] = rest
            else:
                attached.pop(pid, None)

    def _release_host(self, engine: Any, player: Any) -> None:
        """宿主死亡后蝙蝠不再钉在尸体上，可以重新出去找人。"""
        self._attached_map(engine).pop(str(player.id), None)

    # --------------------------------------------------------- 怪物回合
    def on_turn_end(self, engine: Any, player: Any) -> None:
        """p106：蝙蝠在怪物回合入室。叛徒已出局，怪物回合就在"本轮最后一名
        存活玩家"的回合结束触发——挂在这里而不是 on_monster_turn_start，
        否则开局一只蝙蝠都没落下时（塔楼/阁楼与裂隙/地下墓穴都没被发现）
        根本没有怪物回合，蝙蝠永远进不来（实测 150 回合僵局）。"""
        if _is_last_in_round(engine, player):
            self._enter_bats_this_round(engine)

    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        if _monster_id(monster) != self.BAT:
            return False
        if self._host_of(engine, monster) is not None:
            return True  # 已贴附：不移动不攻击，代价在宿主回合开始结算
        target = engine._find_monster_target(monster)
        if target is None:
            return True
        if monster.room_key != target.room_key:
            steps = engine.roll_dice(max(1, getattr(monster, "speed", 5)), "蝙蝠移动")
            path = engine._shortest_path(monster.room_key, target.room_key)
            if len(path) > 1:
                monster.room_key = path[min(len(path) - 1, max(1, steps))]
            return True
        roll = engine.roll_dice(1, "蝙蝠扑附")
        if roll >= 2:
            self._attach(engine, monster, target)
        else:
            engine._log(f"蝙蝠在{target.name}头顶盘旋，没能落下来（掷出 {roll}）。")
        return True

    def _entry_doors(self, engine: Any) -> list[str]:
        """p106 的蝙蝠入口：只要"在房子里"即可，不要求已发现。

        原版开局那几块起始板块就是正面朝上的，本引擎把 entrance_hall 等起始房
        记作 revealed=False（等人踩进去才翻正），若按"已发现"筛入口会让作祟
        开局根本没有蝙蝠能入室。坍塌掉的板块不算入口。
        """
        keys = []
        for template_id in self.ENTRY_ROOMS:
            key = next(
                (
                    k for k, room in engine.state.board.items()
                    if room.template_id == template_id and not engine._is_collapsed(k)
                ),
                "",
            )
            if key:
                keys.append(key)
        return keys

    def _enter_bats_this_round(self, engine: Any) -> None:
        """p106：每个怪物回合按玩家数掷骰放蝙蝠；一个怪物回合只放一批。"""
        flags = engine._haunt_flags()
        if flags.get("bats_sealed"):
            return
        turn = engine.state.turn_count
        if int(flags.get("last_entry_turn", -1)) == turn:
            return
        flags["last_entry_turn"] = turn
        count = engine.roll_dice(len(engine.state.players), "蝙蝠入室")
        if count <= 0:
            return
        doors = self._entry_doors(engine)
        if not doors:
            return
        spec = self._bat_spec(engine)
        entered = 0
        for index in range(count):
            if len(self._bats(engine)) >= self.BAT_CAP:
                engine._log("蝙蝠令牌用尽了——屋里已经挤满 24 只。")
                break
            if engine._spawn_single_haunt_monster(spec, doors[index % len(doors)]) is None:
                break
            entered += 1
        if entered:
            engine._advance_haunt_track("bats_released", entered)
            engine._log(f"{entered} 只蝙蝠从窗口与地裂挤了进来。")

    # ------------------------------------------------------- 宿主回合开始
    def on_turn_start(self, engine: Any, player: Any) -> None:
        if player.role != "hero":
            return
        if player.dead:
            # 宿主已被别的来源杀死：蝙蝠该松开去找下一个活人，而不是钉在尸体上
            self._release_host(engine, player)
            return
        count = len(self._attached_ids(engine, player))
        if not count:
            return
        engine._log(f"{player.name} 身上贴着 {count} 只蝙蝠。")
        engine._deal_damage(player, "physical", count, source=self.DAMAGE_SOURCE)
        if player.dead:
            self._release_host(engine, player)
            return
        player.steps_remaining = max(1, player.steps_remaining - count)

    def on_player_moved(self, engine: Any, player: Any) -> None:
        """贴附的蝙蝠跟着宿主走。"""
        for bat_id in self._attached_ids(engine, player):
            bat = next((m for m in engine.state.monsters if str(getattr(m, "id", "")) == bat_id), None)
            if bat is not None:
                bat.room_key = player.room_key

    # ------------------------------------------------------------- 战斗
    def monster_killed_on_defeat(
        self, engine: Any, monster: Any, attacker: Any, attack_attr: str, weapon_id: str
    ) -> bool:
        """p35：力量攻击击败蝙蝠 = 杀死，不是击晕。"""
        if _monster_id(monster) != self.BAT or attack_attr != "might":
            return False
        self._drop_dead_bat(engine, monster)
        return True

    # ------------------------------------------------------------- 三步
    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id != "drive_away_bats":
            return super().perform_action(engine, player, action_id, data)
        if not super().perform_action(engine, player, action_id, data):
            return False
        engine._haunt_flags()["bats_sealed"] = True
        driven = 0
        for bat in list(self._bats(engine)):
            if self._host_of(engine, bat) is None:
                engine._kill_monster(bat, killer=player)
                driven += 1
        engine._log(f"管风琴砸出刺耳的和弦，{driven} 只没贴住人的蝙蝠撞出窗外——入口封死了。")
        engine.check_victory()
        return True

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "屋里只剩下翅膀摩擦声，和一地抽干的空壳。")
            return True
        if engine._haunt_flags().get("bats_sealed") and not self._bats(engine):
            engine._set_winner("heroes", "最后一只吸饱的蝙蝠被砸在地上，窗外透进黎明的光。")
            return True
        return True  # 叛徒开局即死：吸收引擎兜底

    # ------------------------------------------------------------- bot 寻路
    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        """p35：英雄真实胜利 = 把蝙蝠封回窗外（bats_sealed 且场上无蝙蝠），
        不是逃生。封印链两步都在管风琴房（力量5+启动管风琴、知识6+奏驱蝠之音），
        之后才是清掉仍贴在人身上的蝙蝠。故 bot 唯一推进点 = 管风琴房；封印
        完成前一直把它当寻路目标，封印后再去打贴附的蝙蝠（由 attack_monsters 处理）。"""
        flags = engine._haunt_flags()
        if flags.get("bats_sealed"):
            return []  # 封印已成，去杀仍贴附的蝙蝠（任意房间，靠 attack_monsters）
        organ = next(
            (k for k, r in engine.state.board.items()
             if r.template_id == "organ_room" and not engine._is_collapsed(k)),
            "",
        )
        if organ:
            return [organ]
        return []
