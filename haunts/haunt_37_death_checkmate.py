"""DeathCheckmateMode（剧本 37）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    _monster_id,
)


class DeathCheckmateMode(GenericModeHandler):
    """剧本 37 将军（Checkmate）。

    权威原文：英雄手册 p48 / 叛徒手册 p119。

    · 死神（shadow 模板承载）：不可被攻击/影响（invulnerable）；
      放在有英雄的房间；Speed 0 不移动。
    · 国际象棋（p48/p119）：死神回合开始，同房知识最高英雄 vs 死神
      （知识 8、空白骰重掷一次——monster_rerolls_blanks）。
      英雄知识 > 死神知识 → 将军（英雄胜）。
    · 圣印（p48）：5 枚放保险库/地窖/实验室/手术室/游戏室（未发现的
      房间等发现时补放）；理智 4+ 破解（break_seal 行动）；
      每破一枚死神掷骰 -1（3-4 人局 -2）。
    · 古书：持有者知识检定 +1 骰（上限 8）。
    · 死神赢 1-2 → 全英雄 -1 理智；3-4 → -1 力量；5+ → -1 理智 -1 力量。
    · 弃赛（p119）：死神房间无英雄 → 叛徒胜。
    · 机器人（M10-50 补）：坐庄制——知识最高的英雄守着棋盘（bot_stay_in_room
      钉在房里），其余人去破圣印；叛徒 bot 进不了死神房间（bot_blocked_rooms，
      p119"你不能进这间房"）。缺这三条时英雄没有目标，作祟后 3 个回合房间就空，
      18/18 全败且从未下过一盘棋。
    · 简化：叛徒用铃/枪/炸药远程影响房内英雄未在引擎层拦截；圣印可被叛徒
      偷取未建模。
    """

    mode = "death_checkmate"

    DEATH = "shadow"

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags["seals_broken"] = 0
        flags["death_dice_reduction"] = 0
        # p119：死神放"有英雄的房间"（原文由叛徒挑选）——引擎按 spawn:"haunt_room"
        # 生成在揭露房，而揭露者本人就是叛徒：英雄不在那间时，死神第一个回合
        # 直接触发弃赛判负（seed101/3p 实测 t51 揭示、t54 英雄全败，一局棋都没下）。
        # bot 取"英雄最多的房间"，同数取房间 key 最小的一间，保证种子可复现。
        death = self._death(engine)
        hero_rooms = [
            p.room_key for p in engine.state.players if p.role == "hero" and not p.dead
        ]
        if death is not None and hero_rooms and death.room_key not in hero_rooms:
            crowded = sorted(set(hero_rooms), key=lambda k: (-hero_rooms.count(k), k))
            death.room_key = crowded[0]
        # p119：圣印放五个房间（在场即放，否则等发现时补放）
        seal_rooms = ["vault", "crypt", "research_laboratory", "operating_laboratory", "game_room"]
        for template_id in seal_rooms:
            key = next(
                (k for k, r in engine.state.board.items() if r.template_id == template_id),
                None,
            )
            if key:
                engine.spawn_token("holy_seal", label="圣印", role="marker", room_key=key)
        engine._log("一个暗影从棋盘对面缓缓浮现——死神在等你落子。")

    def on_room_discovered(self, engine: Any, player: Any, room: Any) -> None:
        seal_rooms = ["vault", "crypt", "research_laboratory", "operating_laboratory", "game_room"]
        if room.template_id in seal_rooms and not engine.tokens_in_room(room.key, "holy_seal"):
            engine.spawn_token("holy_seal", label="圣印", role="marker", room_key=room.key)

    # ------------------------------------------------------------- 内部
    def _death(self, engine: Any) -> Any | None:
        return engine._monster_by_template(self.DEATH)

    def _hero_dice_penalty(self, engine: Any) -> int:
        """p48：每破一枚圣印死神 -1 骰（3-4 人局 -2）。"""
        seals = int(engine._haunt_flags().get("seals_broken", 0))
        return seals * (2 if len(engine.state.players) <= 4 else 1)

    # ------------------------------------------------------------- 攻击
    def monster_rerolls_blanks(self, engine: Any, monster: Any) -> bool:
        """p119：死神掷骰后重掷空白骰。"""
        return _monster_id(monster) == self.DEATH

    def attack_allowed(self, engine: Any, attacker: Any, target: Any) -> bool:
        """p48：死神不可被攻击。"""
        if _monster_id(target) == self.DEATH:
            return False
        return True

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        result = []
        for action in actions:
            if action.id == "break_seal":
                if not engine.tokens_in_room(player.room_key, "holy_seal"):
                    continue
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "break_seal":
            token = next(iter(engine.tokens_in_room(player.room_key, "holy_seal")), None)
            if token is None:
                engine._log("这个房间里没有圣印。")
                return False
            ok = super().perform_action(engine, player, action_id, data)
            if ok and engine.last_haunt_action_succeeded():
                engine.remove_token(token.uid)
                flags = engine._haunt_flags()
                flags["seals_broken"] = int(flags.get("seals_broken", 0)) + 1
                # 轨道与旗标同步：rule_data 把"已破解圣印 5"声明成 UI 进度条
                # （●○ 由 tracks 渲染），此前只写旗标，进度条永远是 0/5
                # （M10-50 实测 18 局全为 0，而骰数惩罚其实已经生效）。
                engine._advance_haunt_track("seals_broken", 1)
                engine._log(f"圣印碎裂了！死神的力量被削弱（已破 {flags['seals_broken']} 枚）。")
            return ok
        return super().perform_action(engine, player, action_id, data)

    # ------------------------------------------------------------- 死神回合
    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        if _monster_id(monster) != self.DEATH:
            return False
        flags = engine._haunt_flags()
        # p119：死神房间无英雄 → 弃赛
        heroes_here = [
            p for p in engine.state.players
            if p.role == "hero" and not p.dead and p.room_key == monster.room_key
        ]
        if not heroes_here:
            engine._set_winner("traitor", "没有人敢坐在死神对面——棋赛弃权了。")
            engine.check_victory()
            return True
        # p48/p119：国际象棋
        challenger = max(heroes_here, key=lambda p: engine._effective_stat(p, "knowledge"))
        # 死神知识 8，空白骰重掷（monster_rerolls_blanks），减去圣印惩罚
        death_dice = max(1, 8 - self._hero_dice_penalty(engine))
        death_values = [engine.rng.choice((0, 1, 2)) for _ in range(death_dice)]
        blanks = [i for i, v in enumerate(death_values) if v == 0]
        for idx in blanks:
            death_values[idx] = engine.rng.choice((0, 1, 2))
        death_roll = sum(death_values)
        # 英雄掷知识（古书 +1 骰，上限 8）
        hero_dice = min(8, engine._effective_stat(challenger, "knowledge"))
        if "omen_book" in challenger.items:
            hero_dice = min(8, hero_dice + 1)
        hero_roll = engine.roll_dice(hero_dice, "国际象棋")
        engine._log(
            f"国际象棋对弈：{challenger.name}（{hero_roll}，{hero_dice} 骰）"
            f" vs 死神（{death_roll}，{death_dice} 骰）。"
        )
        if hero_roll > death_roll:
            engine._set_winner("heroes", "Checkmate. 死神微笑着化为尘埃……")
            engine.check_victory()
            return True
        if hero_roll == death_roll:
            engine._log("和棋——双方都不敢轻举妄动。")
            return True
        diff = death_roll - hero_roll
        if diff <= 2:
            losses = (("sanity", 1),)
            engine._log("死神吃了一枚兵——所有英雄理智 -1。")
        elif diff <= 4:
            losses = (("might", 1),)
            engine._log("死神吃了一枚重要棋子——所有英雄力量 -1。")
        else:
            losses = (("sanity", 1), ("might", 1))
            engine._log('死神冷冷地说："Check." ——所有英雄理智 -1、力量 -1。')
        for p in list(engine.state.players):
            if p.role != "hero" or p.dead:
                continue
            for stat, amount in losses:
                engine._apply_stat_loss(p, stat, amount)
            # p48 的损失与战斗伤害一样会把属性打到骷髅上：归零即倒下。缺这一步
            # 时坐庄英雄会带着 0/0 永远坐在棋盘前——叛徒又进不了死神房间，
            # 对局再也收不了场（M10-50 seed127/3p 实测 300 回合跑不完，
            # 属性停在 理智0/力量0 而人还活着）。
            engine._check_player_death(p)
        engine.check_victory()
        return True

    # ------------------------------------------------------------- 机器人
    def _unbroken_seal_rooms(self, engine: Any) -> list[str]:
        """场上还没破解的圣印所在房间（p48：5 枚；破一枚死神少掷 1~2 颗骰）。"""
        return sorted(
            {
                token.room_key
                for token in engine.state.tokens
                if getattr(token, "kind", "") == "holy_seal" and token.room_key
            }
        )

    def _board_sitter(self, engine: Any) -> Any | None:
        """该坐庄的英雄：全场知识最高者（同值取 id 小者，保持可复现）。

        死神每个回合都与"房里知识最高的英雄"对弈（p119），知识最高的人本来就
        是最该长期坐在棋盘前的人。
        """
        heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        if not heroes:
            return None
        return max(heroes, key=lambda p: (engine._effective_stat(p, "knowledge"), -p.id))

    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        """p48/p119：棋盘上必须一直有人，否则弃赛判负。

        实测（seed101/3p）：作祟后英雄各走各的，死神第一个回合（揭露后仅 3 个
        玩家回合）房间就空了——一局棋都没下完就输（探针 18/18 全败）。像人的打法
        只有一种：留一个人坐着，其余人去破解圣印（每破一枚死神少掷 1~2 颗骰，
        是唯一能把胜率拉回五五开的路）。这里按三种局面给目标。
        """
        if player.dead or player.role != "hero":
            return []
        death = self._death(engine)
        sitter = self._board_sitter(engine)
        if death is None or sitter is None:
            return []
        board = death.room_key
        heroes = [p for p in engine.state.players if p.role == "hero" and not p.dead]
        seals = self._unbroken_seal_rooms(engine)
        sitters_here = [p for p in heroes if p.room_key == board]
        # ① 棋盘空着：坐庄的人立刻去坐，其余人照旧去破圣印
        if not sitters_here:
            if player.id == sitter.id:
                return [f"__room__{board}"]
            return [f"__room__{k}" for k in seals] or [f"__room__{board}"]
        # ② 我到了棋盘、而且我就是坐庄的人：守住（别跟着队友去凑热闹）
        if player.id == sitter.id and player.room_key == board:
            return [f"__room__{board}"]
        # ③ 其余英雄：先去破还没破的圣印；都破完（或圣印房不在场）再回棋盘
        if seals:
            return [f"__room__{k}" for k in seals]
        return [f"__room__{board}"]

    def bot_stay_in_room(self, engine: Any, player: Any) -> bool:
        """坐庄的人一旦落座就不再移动——离开等于把棋赛让给死神。"""
        if player.dead or player.role != "hero":
            return False
        death = self._death(engine)
        sitter = self._board_sitter(engine)
        return bool(
            death is not None
            and sitter is not None
            and player.id == sitter.id
            and player.room_key == death.room_key
        )

    def bot_blocked_rooms(self, engine: Any, player: Any) -> list[str]:
        """p119：叛徒不许进死神房间（原文"你既不能进这间房，也不能用铃铛/左轮/
        炸药影响里面的英雄"）。

        旧注释写"bot 自然不会进"——那时没有英雄会坐在那儿。现在坐庄的英雄常驻，
        叛徒 bot 会跟进房间把人捶死（棋赛随即弃权判负），必须显式挡掉。
        """
        if getattr(player, "role", None) != "traitor":
            return []
        death = self._death(engine)
        return [death.room_key] if death is not None else []

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "最后一个棋子也被将死了。")
            return True
        # 吸收引擎「叛徒死亡→英雄胜」兜底：p48/p119 只认"知识检定将死死神"，
        # 死神是独立怪物，叛徒死后照常下棋。
        if not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            return True
        return False
