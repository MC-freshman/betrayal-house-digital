"""MadWorldMode（剧本 34）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    _monster_id,
)


class MadWorldMode(GenericModeHandler):
    """剧本 34 疯狂世界（Mad, Mad World）。

    权威原文：英雄手册 p45 / 叛徒手册 p116。

    · 保险库强制入场（p45）；疯子卡归叛徒（p116 "Marc Antony"）。
    · 随从（Servants）：数量 = 其他玩家数，每层一只 + 其余随机；
      用 spider 模板承载（Speed 3 / Might 3 / Sanity 1，p99），
      项目无Servant模板，engine_note 惯例。
    · 捕获（p45）：力量攻击击败随从/叛徒 → 选择抓住（不伤害不击晕）。
      背负者力量攻击 -2 骰、入房按 2 格、可转交（pass_captive 行动）。
      一次只能背一人。
    · 锁入（p45）：在保险库房间与被缚者同房花整回合（lock_up 行动），
      出局；入库后不可被营救。
    · 营救（p116）：未被捕获的随从/叛徒以力量攻击胜过背负者 2+ 点
      → 释放被缚者（不伤害背负者）。入库后不可营救。
    · 胜负（p45）：所有随从 + 叛徒均被锁入（或杀死）→ 英雄胜；
      英雄全灭 → 叛徒胜。
    · 简化：叛徒被杀 → 随从不死亡（原文只说 "kill or lock up the
      traitor"，英雄胜利条件改为"叛徒被锁或被杀 + 全部随从被锁或被杀"）；
      随从 bot 追最近英雄（引擎默认）；随从/叛徒主动攻击落败不受伤
      （p116 "Neither you nor the Servants take damage … if you are
      defeated when you attack"——attack_loss_damage_disabled 对随从/叛徒
      主动攻击也生效）。
    · 已知简化（M10-49 更正）：**叛徒当前无法被"抓"**（p45 允许对叛徒用
      力量攻击改为抓住）——`_captors` 只会写 "servant"，`check_victory` 里
      `"traitor" in locked` / `traitor_carried` 两个分支实际不可达；英雄要赢
      只能**杀死**叛徒（画像因此开 attack_traitor_players）或关押随从后杀他。
      抓捕叛徒需要引擎在"玩家被击败但未死"处开钩子，留待后续批次。
    · 保险库开启状态读引擎房间数据 `room.data["opened"]`（M10-49 修：此前
      查 handler 旗标 `flags["vault_open"]`，全项目无人置位，"关进保险库"
      整条胜线曾是死代码）。
    """

    mode = "mad_world"

    SERVANT = "spider"

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags["captor"] = {}  # {captor_player_id: captive_kind ("servant"|"traitor")}
        flags["locked_up"] = []
        flags["vault_open"] = False
        # p45：保险库强制入场
        vault = engine._ensure_room_in_play("vault", room_key)
        flags["vault_room"] = vault
        # p116：疯子卡归叛徒
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None:
            madman_holder = next(
                (p for p in engine.state.players if "omen_madman" in p.items), None
            )
            if madman_holder is not None and madman_holder.id != traitor.id:
                madman_holder.items.remove("omen_madman")
                traitor.items.append("omen_madman")
                engine._log(f"{traitor.name} 夺走了疯子卡——Marc Antony 站在了他这一边。")
        # p116：随从 = 其他玩家数，每层一只 + 其余随机
        players = len(engine.state.players)
        floors = sorted({r.floor for r in engine.state.board.values()})
        spec_source = haunt.rule_data.get("monsters", [])
        spec = next((s for s in spec_source if s.get("template_id") == self.SERVANT), {})
        spec = dict(spec)
        spec["name"] = "疯人院随从"
        spec["speed"], spec["might"], spec["sanity"] = 3, 3, 1
        placed = 0
        for floor in floors:
            candidates = sorted(
                k for k, r in engine.state.board.items()
                if r.floor == floor and not r.data.get("lake_tile")
            )
            if candidates:
                key = candidates[placed % len(candidates)]
                monster = engine._spawn_single_haunt_monster(spec, key)
                if monster is not None:
                    placed += 1
        for _ in range(max(0, players - 1) - placed):
            candidates = sorted(
                k for k, r in engine.state.board.items()
                if not r.data.get("lake_tile")
            )
            if not candidates:
                break
            key = engine.rng.choice(candidates)
            monster = engine._spawn_single_haunt_monster(spec, key)
            if monster is not None:
                placed += 1
        engine._log(f"{placed} 名疯人院随从在房子里游荡，嘴里念着 Caesar 的名字。")

    # ------------------------------------------------------------- 内部
    def _captors(self, engine: Any) -> dict:
        return engine._haunt_flags().setdefault("captor", {})

    def _vault_room(self, engine: Any) -> str | None:
        return engine._haunt_flags().get("vault_room")

    def _vault_is_open(self, engine: Any) -> bool:
        """p45：保险库必须先被打开才能关人。

        开启状态是**引擎的房间数据**（`_apply_vault`：知识 4+ →
        `room.data["opened"]=True` 并抽两张物品），不是本 handler 的旗标——
        过去这里查 `flags["vault_open"]`，而全项目没有任何地方会把它置 True，
        于是 `lock_up` 永远不出现在行动列表里（seed101/4p 实测：英雄背着俘虏
        在库里站到 300 回合也关不进去）。这里改读房间数据；旧存档/既有测试
        仍认旗标，两者取或。
        """
        flags = engine._haunt_flags()
        if flags.get("vault_open") is True:
            return True
        vault = self._vault_room(engine)
        room = engine.state.board.get(vault) if vault else None
        return bool(room is not None and room.data.get("opened"))

    def on_player_died(self, engine: Any, player: Any) -> None:
        """背负者阵亡 → 俘虏挣脱。

        p45 只规定"被背着的俘虏不能行动"，没说背着的人倒下怎么办；电子版按
        "没人制住他了"处理：随从回场继续游荡，叛徒只是恢复自由。缺这条时
        `captor` 里的死携带者会永久占住俘虏——俘虏既不能行动也不会回场，
        "随从全部被处置"永远凑不齐（seed101/4p 实测：机器人3 背着随从阵亡，
        剩下两名英雄在酒窖↔地下室平台打转到 300 回合）。
        """
        kind = self._captive_kind(engine, player)
        if kind is None:
            return
        self._drop_captive(engine, player)
        room_key = getattr(player, "room_key", "")
        if kind == "servant" and room_key in engine.state.board:
            spec = {
                "template_id": self.SERVANT,
                "name": "疯人院随从",
                "speed": 3,
                "might": 3,
                "sanity": 1,
            }
            if engine._spawn_single_haunt_monster(dict(spec), room_key) is not None:
                engine._log(f"背着俘虏的{player.name}倒下了——随从挣脱出来，重新在屋里游荡。")
        else:
            engine._log(f"背着俘虏的{player.name}倒下了——叛徒挣脱了束缚。")
        engine.check_victory()

    def _servants(self, engine: Any) -> list:
        return [m for m in engine.state.monsters if _monster_id(m) == self.SERVANT]

    def _is_captive_carrier(self, engine: Any, player: Any) -> bool:
        return str(getattr(player, "id", "")) in self._captors(engine)

    def _captive_kind(self, engine: Any, player: Any) -> str | None:
        return self._captors(engine).get(str(getattr(player, "id", "")))

    def _drop_captive(self, engine: Any, player: Any) -> None:
        self._captors(engine).pop(str(getattr(player, "id", "")), None)

    # ------------------------------------------------------------- 移动
    def movement_cost_multiplier(self, engine: Any, player: Any, from_key: str | None = None, to_key: str | None = None) -> int:
        """p45：背着人入房按 2 格计。"""
        if self._is_captive_carrier(engine, player):
            return 2
        return 1

    def on_turn_start(self, engine: Any, player: Any) -> None:
        if player.dead:
            return
        # p45：背负者力量攻击 -2 —— 通过 flags 实现（attack 用 _effective_stat + _check_bonus）
        # 攻击减值用 on_attack_resolved 不够，直接在回合开始时记一个惩罚骰数标记

    # ------------------------------------------------------------- 攻击
    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """p45：力量击败随从 → 可选择抓住（不击晕）。杀死也计入胜利条件。"""
        if _monster_id(monster) != self.SERVANT:
            return False
        attacker = None
        active_id = getattr(engine, "_active_player_id", None)
        if active_id is not None:
            attacker = engine.state.players[active_id]
        if attacker is None or attacker.frog:
            return False
        # 只有力量的胜利才可捕获
        if amount <= 0:
            return False
        # 询问英雄：抓住还是击晕？
        if engine.prompter is not None:
            choice = engine.prompter.confirm(
                "捕获", f"要抓住 {monster.name}（代替击晕）吗？"
            )
        else:
            choice = True  # bot 默认抓住
        if choice:
            self._captors(engine)[str(attacker.id)] = "servant"
            monster_id = getattr(monster, "id", None)
            engine.state.monsters = [
                m for m in engine.state.monsters if getattr(m, "id", None) != monster_id
            ]
            engine._log(f"{attacker.name} 制伏了 {monster.name}，把TA扛了起来！")
            return True  # 不击晕（被捕获了）
        return False  # 默认击晕

    def attack_loss_damage_disabled(self, engine: Any, attacker: Any, target: Any) -> bool:
        """p116：随从/叛徒主动攻击落败不受伤。"""
        if isinstance(getattr(target, "role", None), str) and target.role == "traitor":
            return True
        if _monster_id(target) == self.SERVANT:
            return True
        return False

    def on_attack_resolved(self, engine: Any, attacker: Any, target: Any, attacker_won: bool) -> None:
        """p45：背负者力量攻击 -2 骰。用简化：直接在 effective_stat 减（不行）。
        改为在 _roll_attack 之后减——不可行，此处只处理营救。"""
        # 营救：未被捕获的随从以力量 2+ 胜过背负者
        if not isinstance(attacker_won, bool):
            return
        if not attacker_won:
            return
        if _monster_id(attacker) != self.SERVANT:
            return
        # 本模块刻意不 import engine（防循环导入），所以"是不是玩家"只能按
        # 鸭子类型判：Player 有 role（str），Monster 只有 template_id。
        # 过去这里写 isinstance(target, Player) 必抛 NameError（该行虽因
        # _monster_id(attacker) 前置判断而不可达，仍是必须拆掉的雷）。
        if not isinstance(getattr(target, "role", None), str):
            return
        if not self._is_captive_carrier(engine, target):
            return
        # 随从以 2+ 点力量胜过背负者 → 释放
        engine._log(f"随从击溃了 {target.name} 的抓握，俘虏挣脱了！")
        self._drop_captive(engine, target)

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        actions = super().available_actions(engine, player)
        result = []
        vault = self._vault_room(engine)
        for action in actions:
            if action.id == "lock_up":
                if player.role != "hero" or not self._is_captive_carrier(engine, player):
                    continue
                if player.room_key != vault:
                    continue
                if not self._vault_is_open(engine):
                    continue
            if action.id == "pass_captive":
                if player.role != "hero" or not self._is_captive_carrier(engine, player):
                    continue
                if not any(
                    other.role == "hero" and not other.dead
                    and other.room_key == player.room_key and other.id != player.id
                    and not self._is_captive_carrier(engine, other)
                    for other in engine.state.players
                ):
                    continue
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        flags = engine._haunt_flags()
        vault = self._vault_room(engine)
        if action_id == "lock_up":
            if not self._is_captive_carrier(engine, player) or player.room_key != vault:
                engine._log("需要在保险库房间背着俘虏才能锁入。")
                return False
            if not self._vault_is_open(engine):
                engine._log("保险库还锁着——得先把它打开才能把人关进去。")
                return False
            kind = self._captive_kind(engine, player)
            captive_desc = "叛徒" if kind == "traitor" else "随从"
            locked = flags.setdefault("locked_up", [])
            locked.append(captive_desc)
            self._drop_captive(engine, player)
            player.movement_stopped = True
            player.steps_remaining = 0
            engine._log(f"{player.name} 花了整回合把{captive_desc}锁进了保险库！（{len(locked)} 人已锁）")
            engine.check_victory()
            return True

        if action_id == "pass_captive":
            kind = self._captive_kind(engine, player)
            target_id = (data or {}).get("target_id")
            target = next(
                (p for p in engine.state.players
                 if p.id == target_id and p.role == "hero" and not p.dead
                 and p.room_key == player.room_key and p.id != player.id
                 and not self._is_captive_carrier(engine, p)),
                None,
            )
            if target is None or kind is None:
                engine._log("需要同房间的一名可接手的英雄。")
                return False
            self._drop_captive(engine, player)
            self._captors(engine)[str(target.id)] = kind
            engine._log(f"{player.name} 把俘虏交给了 {target.name}。")
            return True

        return super().perform_action(engine, player, action_id, data)

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        locked = flags.get("locked_up", [])
        servants_alive = len(self._servants(engine))
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        traitor_alive = traitor is not None and not traitor.dead
        traitor_carried = self._captive_kind(engine, traitor) == "traitor" if traitor else False
        # 需要叛徒被锁或死 + 全部随从被锁或死
        traitor_done = (not traitor_alive) or ("traitor" in locked) or traitor_carried
        servants_done = servants_alive == 0
        if traitor_done and servants_done:
            engine._set_winner("heroes", "疯王与他的随从全部被锁进了保险库——世界暂时安全。")
            return True
        if not any(p.role == "hero" and not p.dead for p in engine.state.players):
            engine._set_winner("traitor", "Veni, vidi, vici——疯王 Caesar 征服了最后的元老院议员。")
            return True
        # 吸收引擎「叛徒死亡→英雄胜」兜底：p45/p116 要求"随从全部被锁 + 叛徒被锁或死"，
        # 随从还在时叛徒单独死亡不算英雄胜利。
        if not any(p.role == "traitor" and not p.dead for p in engine.state.players):
            return True
        return False
