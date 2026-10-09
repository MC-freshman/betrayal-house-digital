"""FrankensteinMode（剧本 29）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    _monster_id,
)


class FrankensteinMode(GenericModeHandler):
    """剧本 29 弗兰肯斯坦的遗产（Frankenstein's Legacy）。

    权威原文：英雄手册 p40 / 叛徒手册 p111。

    已按原文实现：
        · 数值（p111 页脚，新增 frankenstein 模板）：Speed 3 / Might 8
          （原文未列神智，按无神智处理）。
        · 开局（p111）：怪物放在研究实验室或手术室；两间都不在场就从房间
          牌堆补一间（引擎 `_ensure_room_in_play` 按模板自身楼层放置；
          原文的"放上层"校准为按模板楼层，见已知简化）。另备 5 枚火把令牌。
        · 怪物行为（p111）：全速扑向最近的可攻击英雄（引擎默认）；
          攻击掷骰 +2（走 `monster_attack_roll_bonus`，仅在它主动攻击时加，
          防守不加）；免疫速度攻击（monster_specs `immune_to=["speed"]`，
          覆盖左轮等标了 speed 标签的武器）；赢 2+ 时可抢走并销毁英雄的
          火把而不掉血（`on_monster_attack`）。
        · 火刑（p40）：在 烧焦的房间/熔炉房/五芒星室/厨房 点燃火把
          （每名探险者同时只带 1 支，火把总数不限）；在怪物所在房或门相连
          的邻室做速度攻击投掷——赢则怪物吃 1 次火把命中且英雄失去火把
          （**不击晕**，引擎默认"击败=击晕"在这里不适用，故由 handler
          自己结算），输则只是失去火把、英雄不受伤。命中次数 = 玩家数时
          怪物死亡（轨道 torch_hits，target = player_count）。
        · 推落（p40）：怪物在塔楼/深渊时，同房间力量 6+ 把它推落摔死。
        · 胜负（p40/p111）：英雄胜 = 怪物死亡（火把命中达标或推落成功）；
          叛徒胜 = 英雄全灭。叛徒死亡后怪物照常追杀（怪物回合由本轮最后
          存活玩家代跑，老坑 19 号吸收者）。

    已知简化：
        · 原文"两间实验室都不在场时把该房放在上层"——本引擎
          `_ensure_room_in_play` 按模板自身楼层放置（研究实验室在地面层、
          手术室在二层），未强制上层。
        · 原文的 5 枚火把令牌是实体配件上限，且明说"找火把没有次数限制"，
          引擎按无限火把池处理，只保留"每名探险者同时只能带 1 支"。
        · 本仓库的炸药卡没有 speed 标签（按力量武器建模），因此怪物对
          炸药不免疫——给炸药补 speed 标签会波及全局对局基准，未改。
        · 怪物被英雄普通击败时仍按引擎默认"击晕一回合"处理
          （原文只强调火把命中不击晕）。
    """

    mode = "frankenstein_fire"

    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        if engine._haunt_flags().get("monster_destroyed"):
            return ["怪物：已被火把烧毁"]
        return []

    MONSTER = "frankenstein"
    TORCH = "torch"
    TORCH_ROOMS = ("charred_room", "furnace_room", "pentagram_chamber", "kitchen")
    PUSH_ROOMS = ("tower", "chasm")

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags.setdefault("monster_destroyed", False)
        lab_key = next(
            iter(
                sorted(
                    key
                    for key, room in engine.state.board.items()
                    if room.template_id in ("research_laboratory", "operating_laboratory")
                )
            ),
            "",
        )
        if not lab_key:
            # p111：两间都不在场就从房间牌堆里找出来
            lab_key = (
                engine._ensure_room_in_play("research_laboratory", room_key)
                or engine._ensure_room_in_play("operating_laboratory", room_key)
                or ""
            )
        if not lab_key:
            engine._log("实验室既不在场也补不进来——怪物没能站起来。")
            return
        engine._spawn_single_haunt_monster(self._spec(engine), lab_key)
        engine._log("实验室里传来缝合线崩裂的声音——它站起来了。")

    def _spec(self, engine: Any) -> dict:
        specs = engine._haunt_rule_state().get("monster_specs", {})
        return dict(specs.get(self.MONSTER) or {"template_id": self.MONSTER, "name": "弗兰肯斯坦的怪物"})

    # ----------------------------------------------------------- 状态查询
    def _monster(self, engine: Any) -> Any | None:
        return next((m for m in engine.state.monsters if _monster_id(m) == self.MONSTER), None)

    def _torches(self, engine: Any, player: Any) -> list[Any]:
        return engine.tokens_held_by(player.id, self.TORCH)

    def _near_monster(self, engine: Any, player: Any, monster: Any) -> bool:
        """p40：怪物所在房，或与它有门相连的邻室。"""
        if monster.room_key == player.room_key:
            return True
        return player.room_key in set(engine._door_neighbors(monster.room_key))

    def _needed(self, engine: Any) -> int:
        return len(engine.state.players)

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        if not actions:
            return actions
        monster = self._monster(engine)
        holding = bool(self._torches(engine, player))
        result = []
        for action in actions:
            if action.id == "light_torch" and holding:
                continue  # p40：每名探险者同时只能带 1 支火把
            if action.id == "throw_torch":
                if not holding or monster is None or not self._near_monster(engine, player, monster):
                    continue
            if action.id == "push_monster":
                if monster is None or monster.room_key != player.room_key:
                    continue
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "light_torch":
            return self._light_torch(engine, player)
        if action_id == "throw_torch":
            return self._throw_torch(engine, player)
        if action_id == "push_monster":
            return self._push_monster(engine, player)
        return super().perform_action(engine, player, action_id, data)

    def _light_torch(self, engine: Any, player: Any) -> bool:
        engine.spawn_token(self.TORCH, label="火把", role="carried", holder=player.id)
        engine._log(f"{player.name} 就地引燃了一支火把。")
        return True

    def _throw_torch(self, engine: Any, player: Any) -> bool:
        monster = self._monster(engine)
        torches = self._torches(engine, player)
        if monster is None or not torches:
            return False
        torch = torches[0]
        attack_roll = engine._roll_attack(player, "speed")
        defense = engine._roll_monster_attack(monster, "speed")
        engine._log(f"{player.name} 把火把掷向{monster.name}：{attack_roll} 对 {defense}。")
        engine.remove_token(torch.uid)  # 无论胜负，火把都消耗掉（p40）
        if attack_roll > defense:
            hits = engine._advance_haunt_track("torch_hits", 1)
            needed = self._needed(engine)
            engine._log(f"火把在怪物身上炸开一片火光（{hits}/{needed}）——它没有被击晕。")
            if hits >= needed:
                self._destroy_monster(engine, player)
        else:
            engine._log(f"{player.name} 投偏了，火把落地熄灭——人没受伤，只丢了火把（p40）。")
        return True

    def _push_monster(self, engine: Any, player: Any) -> bool:
        monster = self._monster(engine)
        if monster is None or monster.room_key != player.room_key:
            return False
        if not engine._resolve_check(player, "might", 6, "把怪物推下去"):
            engine._log(f"{player.name} 用尽力气也没能推动它。")
            return True
        engine._log(f"{player.name} 狠狠一推——{monster.name} 坠了下去（p40）。")
        self._destroy_monster(engine, player)
        return True

    def _destroy_monster(self, engine: Any, killer: Any) -> None:
        monster = self._monster(engine)
        if monster is None:
            return
        engine._haunt_flags()["monster_destroyed"] = True
        engine._kill_monster(monster, killer=killer)
        engine.check_victory()

    # ------------------------------------------------------- 怪物战斗特性
    def monster_attack_roll_bonus(self, engine: Any, monster: Any, target: Any) -> int:
        # p111：怪物攻击掷骰 +2（防守时不加——引擎只在这条主动攻击路径调用）
        return 2 if _monster_id(monster) == self.MONSTER else 0

    def on_monster_attack(self, engine: Any, monster: Any, target: Any, amount: int) -> bool:
        # p111：赢 2+ 时可抢走并销毁火把而不掉血
        if _monster_id(monster) != self.MONSTER:
            return False
        torches = engine.tokens_held_by(getattr(target, "id", -1), self.TORCH)
        if amount > 2 and torches:
            for token in torches:
                engine.remove_token(token.uid)
            engine._log(f"{monster.name} 一把夺过{getattr(target, 'name', '探险者')}的火把捏灭了它（p111）。")
            return True  # 伤害已由剧本结算（抢火把，不掉血）
        return False

    # ------------------------------------------------------------ bot
    # p111 怪物速度 3：一次移动掷骰（3 枚 0–2）平均正好 3 格、上限 6 格。
    # 3 步之内算"它一轮就够得着我"，要靠 5 步以上的距离才算过夜安全。
    THREAT_STEPS = 3

    def _monster_distances(self, engine: Any) -> dict[str, int]:
        """从怪物所在房出发做一次 BFS：房间 key → 步数。

        险区判定要问全屋几十间房；逐间调 `engine._path_length` 每次都要
        重建邻接表再跑一遍 BFS，代价高一个量级。这里一次算完，而且走的是
        引擎的完整图（含楼梯/煤导槽等 links），比只看门邻更接近怪物的
        实际走法——它能顺着楼梯上楼，只看门邻会把它算慢。
        """
        monster = self._monster(engine)
        if monster is None:
            return {}
        graph = engine._build_graph()
        distances = {monster.room_key: 0}
        queue = [monster.room_key]
        while queue:
            key = queue.pop(0)
            for neighbor in graph.get(key, ()):
                if neighbor in distances:
                    continue
                distances[neighbor] = distances[key] + 1
                queue.append(neighbor)
        return distances

    def _is_monster_target(self, engine: Any, player: Any, distances: dict[str, int]) -> bool:
        """怪物按"最近的英雄"选目标（引擎 `_find_monster_target`）——我是不是它？

        平手时引擎按 `state.players` 顺序取第一个；这里同样按 (距离, id) 取最小，
        与引擎的稳定排序一致。
        """
        best: tuple[int, int] | None = None
        for other in engine.state.players:
            if other.dead or getattr(other, "role", None) != "hero":
                continue
            distance = distances.get(other.room_key, 9999)
            if best is None or distance < best[0]:
                best = (distance, other.id)
        return best is not None and best[1] == player.id

    def _flee_rooms(self, engine: Any, distances: dict[str, int], keep: int) -> list[str]:
        """全速撤离目标：优先距离 ≥ keep 步的房间，从最远的数起。

        房子太小、凑不出 keep 步开外的房间时退回"能选到的最远几间"，
        绝不能返回空——那等于把走位交回通用逻辑，而通用逻辑会朝着
        怪物/目标房走。
        """
        ranked = sorted(
            ((distance, key) for key, distance in distances.items() if distance > 0),
            key=lambda item: (-item[0], item[1]),
        )
        beyond = [item for item in ranked if item[0] >= keep]
        chosen = beyond or ranked
        return ["__room__" + key for _distance, key in chosen[:6]]

    def bot_blocked_rooms(self, engine: Any, player: Any) -> set[str]:
        """英雄禁区：怪物所在的房间（p111 力 8 + 2，踏进去＝被摸到＝秒杀）。

        实测（seed149/4p）：英雄的撤离目标本身没问题，但到远处的最短路径
        要穿过怪物所在的那间房，机器人就照走不误、还顺手空手开打（1 对 13，
        反手吃 12 点当场倒下）。唯一值得走进去的时候是 p40 的推落：怪物在
        塔楼/深渊、自己力量够——这一间正是要去的目的地。"""
        if player.dead or player.role != "hero":
            return set()
        monster = self._monster(engine)
        if monster is None:
            return set()
        room = engine.state.board.get(monster.room_key)
        stats = getattr(player, "stats", {}) or {}
        if (
            room is not None
            and room.template_id in self.PUSH_ROOMS
            and int(stats.get("might", 0)) >= 5
        ):
            return set()
        return {monster.room_key}

    def bot_attack_blocked(self, engine: Any, player: Any, target: Any) -> bool:
        """英雄不主动肉搏本剧本的怪物（p111：力 8 且被攻击落败要挨差值反击）。

        画像里的 `attack_monsters: False` 只挡住了"追怪"的走位，挡不住攻击
        本身：被怪物堵在同一间房里时空手开打，几乎必然 0 命中反吃 10+ 点。
        真人的赢法是火把投掷（剧本行动）与推落，不是拳头。"""
        if player.role != "hero":
            return False
        return _monster_id(target) == self.MONSTER

    def bot_hazard_rooms(self, engine: Any, player: Any) -> set[str]:
        """本回合结束时不该留在里面的房间（"进去就没步数退出来"时重扣）。

        实测（seed101/4p 追踪）：怪物力 8 + 2 打未受伤英雄平均 7 点，而英雄
        物性总量才 8 点上下——被它在房间里摸到就是秒杀，所以险区不是"门邻
        一圈"，而是它一轮移动（≤3 步）能到的整个范围。

        拿火把的人另算：投掷位（1 步的门邻室）正是他该站的位置，不算险区；
        但怪物自己的房间（0 步，站进去＝白给）和"够得着又投不了"的中段
        （2–3 步）都不该过夜。
        """
        if player.dead or player.role != "hero":
            return set()
        distances = self._monster_distances(engine)
        if not distances:
            return set()
        holding = bool(self._torches(engine, player))
        hazards = set()
        for key, distance in distances.items():
            if holding:
                if distance == 0 or 2 <= distance <= self.THREAT_STEPS:
                    hazards.add(key)
            elif distance <= self.THREAT_STEPS:
                hazards.add(key)
        return hazards

    def bot_leave_after_action(self, engine: Any, player: Any) -> bool:
        """投完火把（或推完）必须挪窝：留在投掷圈里＝下个怪物回合被拍。"""
        if player.dead or player.role != "hero":
            return False
        return bool(engine._haunt_action_used(player))

    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        """英雄 bot 的推进目标（p40 的两条杀怪线 + 保命）。

        实测（seed101/4p 逐回合追踪）：上一版拿到火把就直奔怪物门邻、投完
        只退一间就停（`bot_stay_in_room`），而怪物移动 3 格——四人被一轮
        一个拍死，整局只点 1 支火把、投 1 次、命中 0。按"距离—相位"重排：
          ① 推落窗口：怪物已在塔楼/深渊、自己力量 ≥5 → 直奔它房间
             （一次 6+ 检定直接摔死，比火把快得多的赢法）；
          ② 站在投掷位上（同房或门邻）且手里有火把 → 原地不动：行动层
             开局就会投（`available_actions` 只在射程内给 throw_torch）；
             行动已用掉还杵在圈里（投不了/已投完）→ 按 ③ 撤；
          ③ 没火把且怪物够得着我（≤3 步），或已经贴到 2 步内 → 全速拉开
             到 5 步外。拿火把的人不在此列：他的活儿就是站进投掷位；
          ④ 拿着火把：只有"这一步能踏进投掷位 + 行动还没用掉"才靠过去。
             每个探险者每回合只有一次剧本行动——刚在点火房点完火把的人
             这一回合已经投不了了（`_haunt_action_used`），再走进投掷位
             就是白站：p111 的怪物赢 2+ 就把火把抢走（30 局实测被抢 23 次、
             有效投掷只有 31 次）。够不着/投不了时保持 5 步外，让它自己追近
             （它只追最近的人）；
          ⑤ 空手 → 去四间点火房之一（烧焦的房间/熔炉房/五芒星室/厨房）。
        """
        if player.role != "hero" or player.dead:
            return []
        monster = self._monster(engine)
        if monster is None:
            return []
        distances = self._monster_distances(engine)
        distance = distances.get(player.room_key, 9999)
        holding = bool(self._torches(engine, player))
        stats = getattr(player, "stats", {}) or {}
        might = int(stats.get("might", 0))
        room = engine.state.board.get(monster.room_key)

        # ① 推落窗口
        if (
            room is not None
            and room.template_id in self.PUSH_ROOMS
            and might >= 5
            and distance <= self.THREAT_STEPS + 1
            and not engine._haunt_action_used(player)
        ):
            return ["__room__" + monster.room_key]

        # ② 已在投掷位、手里有火把
        if holding and distance <= 1:
            if not engine._haunt_action_used(player):
                return []
            return self._flee_rooms(engine, distances, keep=self.THREAT_STEPS + 2)

        # ③ 危险中：没火把的人不当靶子
        if not holding and (
            distance <= 2
            or (
                distance <= self.THREAT_STEPS
                and self._is_monster_target(engine, player, distances)
            )
        ):
            return self._flee_rooms(engine, distances, keep=self.THREAT_STEPS + 2)

        # ④ 拿着火把：只在这一步真能踏进投掷位时才靠过去。
        #    实测（30 局）：无脑靠拢会在半路停下，怪物一回身就把火把抢走
        #    （p111 赢 2+ 抢火把，全场被抢 38 次、有效投掷只有 33 次）——
        #    真人是"等它追近到一脚能进圈，进去就投，投完就跑"。够不着时
        #    先把距离保持在 5 步外，让它自己追过来（它只追最近的人）。
        if holding:
            speed = int(stats.get("speed", 0))
            if distance <= speed and not engine._haunt_action_used(player):
                ring = [k for k in engine._door_neighbors(monster.room_key) if k != monster.room_key]
                if not ring:
                    ring = [monster.room_key]
                return ["__room__" + key for key in ring]
            if distance <= self.THREAT_STEPS + 2:
                return self._flee_rooms(engine, distances, keep=self.THREAT_STEPS + 2)

        # ⑤ 空手：去点火房
        return [
            "__room__" + key
            for key, board_room in engine.state.board.items()
            if board_room.template_id in self.TORCH_ROOMS
        ]

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        # p40 英雄胜：怪物死亡（火把命中达标或推落坠亡）
        if engine._haunt_flags().get("monster_destroyed"):
            engine._set_winner("heroes", "怪物终于不动了——弗兰肯斯坦的秘密随它一起烧成灰烬。")
            return True
        # p111 叛徒胜：英雄全灭
        heroes = [p for p in engine.state.players if p.role == "hero"]
        if heroes and all(p.dead for p in heroes):
            engine._set_winner("traitor", "缝合的怪物踩着英雄们的尸体，等待下一个命令。")
            return True
        return True  # 吸收引擎「叛徒死亡→英雄胜」兜底：叛徒死后怪物照常追杀
