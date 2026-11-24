"""K2 两侧模型。只有提供明确版次/卡面配置的房间才启用，不猜门的分组。"""

try:
    from ..content import BARRIER_SPECS
    from ..engine_parts.geometry import _rotate_direction
    from ..models import Monster
except ImportError:  # pragma: no cover - direct script execution
    from content import BARRIER_SPECS  # type: ignore
    from engine_parts.geometry import _rotate_direction  # type: ignore
    from models import Monster  # type: ignore


class BarrierRules:
    def configure_disclosed_barrier(self, room):
        """按 ``content.BARRIER_SPECS`` 的显式卡面数据给落位板块配置两侧模型。

        生产环境唯一的接线点（`_place_room` 与 `_set_room_orientation` 各调一次），
        规则是"没登记 = 不配置"：宁可让 room_effects 里的既有近似继续生效，也不猜
        门的分组/属性/阈值。登记表当前有 tower/chasm/catacombs 三条（数值来自二手
        交叉验证）；vault 因官方为 1 门、引擎无 1 门房间能力而故意留空，见
        ``content.BARRIER_SPECS`` 注释与 docs/延后项台账.md D-06。

        返回 True = 该板块现在真的带 barrier 配置。
        """
        spec = BARRIER_SPECS.get(room.template_id)
        if not spec:
            return False
        # 登记表按模板的基准朝向写（rotation=0），落位/旋转后要跟着转。
        doors = {
            _rotate_direction(direction, room.rotation): side
            for direction, side in (spec.get("doors") or {}).items()
            if direction in ("north", "east", "south", "west")
        }
        try:
            self.configure_barrier(room, doors, spec.get("stat"), spec.get("target"), spec.get("source"))
        except ValueError:
            # 登记表写错时 fail-closed：不配置（而不是配一半），并留下可搜索的日志。
            self._log(f"[规则缺口] {room.name} 的障碍登记无效，已跳过；不给该房间加障碍。")
            return False
        return True

    def configure_barrier(self, room, doors, stat, target, source):
        if (not source or stat not in ("speed", "might", "sanity", "knowledge")
                or not isinstance(target, int) or target < 0
                or set(doors) != set(room.doors) or set(doors.values()) != {0, 1}):
            raise ValueError("障碍须有明确来源、全部门的两侧映射、属性和阈值")
        room.data["barrier"] = {"doors": dict(doors), "stat": stat, "target": target, "source": source}

    def _barrier_config(self, room):
        return room.data.get("barrier")

    def _barrier_side(self, entity):
        sides = self.state.meta.get("barrier_sides", {})
        return sides.get(entity.room_key, {}).get(str(entity.id), 0)

    def _set_barrier_side(self, entity, room, side):
        if side not in (0, 1):
            raise ValueError("障碍侧须为 0 或 1")
        self.state.meta.setdefault("barrier_sides", {}).setdefault(room.key, {})[str(entity.id)] = side

    def _is_monster_entity(self, entity) -> bool:
        """该实体是否为怪物。

        官方 2nd Ed. 规则手册 p2：**Monsters ignore barriers**（叛徒不免疫）。
        障碍的两侧归属只约束探险者；怪物既不受侧门禁限制，也不因跨越障碍
        而掷检定。三种写法都认，避免调用方拿到的怪物代理对象漏判：
        显式 ``is_monster`` 标记 / ``Monster`` 类型 / ``state.monsters`` 成员。
        """
        if getattr(entity, "is_monster", False):
            return True
        if isinstance(entity, Monster):
            return True
        return any(monster is entity for monster in self.state.monsters)

    def entities_share_room(self, a, b):
        if a.room_key != b.room_key:
            return False
        # p2：怪物无视障碍。BARRIER_SPECS 为空时这段判定是死代码，K2 落地后
        # 第一次被走到（见 docs/延后项台账.md D-06）：英雄与德古拉分居两侧时
        # 攻击曾被这里误拒。任一实体是怪物即视为同侧。
        if self._is_monster_entity(a) or self._is_monster_entity(b):
            return True
        room = self.state.board.get(a.room_key)
        return not room or not self._barrier_config(room) or self._barrier_side(a) == self._barrier_side(b)

    def _barrier_attempt_key(self, player, room):
        return f"barrier:{player.id}:{room.key}"

    def _barrier_can_attempt(self, player, room):
        return self._barrier_attempt_key(player, room) not in self.state.meta.get("barrier_attempts", [])

    def _cross_barrier(self, player):
        room = self.current_room(player)
        config = self._barrier_config(room)
        if not config:
            return False
        # p2：怪物无视障碍，跨越不掷检定、也不消耗每回合一次的机会。
        if self._is_monster_entity(player):
            self._set_barrier_side(player, room, 1 - self._barrier_side(player))
            return True
        if not self._barrier_can_attempt(player, room):
            return False
        self.state.meta.setdefault("barrier_attempts", []).append(self._barrier_attempt_key(player, room))
        success = (player.role == "traitor" and room.template_id != "vault") or self._resolve_check(
            player, config["stat"], config["target"], "跨越障碍")
        if success:
            self._set_barrier_side(player, room, 1 - self._barrier_side(player))
        else:
            player.movement_stopped = True
            player.steps_remaining = 0
        return True

    def _barrier_choose_arrival(self, entity, room, direction=None):
        config = self._barrier_config(room)
        if not config:
            return
        if direction in config["doors"]:
            side = config["doors"][direction]
        elif room.template_id == "vault":
            side = 0  # 规则明确：传入保险库总在门外。
        else:
            index = self.prompter.choose_from_list("障碍落点", "选择到达障碍的哪一侧。", ["第一侧", "第二侧"])
            side = 1 if index == 1 else 0
        self._set_barrier_side(entity, room, side)
