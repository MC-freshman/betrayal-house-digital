"""K2 两侧模型。只有提供明确版次/卡面配置的房间才启用，不猜门的分组。"""


class BarrierRules:
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

    def entities_share_room(self, a, b):
        if a.room_key != b.room_key:
            return False
        room = self.state.board.get(a.room_key)
        return not room or not self._barrier_config(room) or self._barrier_side(a) == self._barrier_side(b)

    def _barrier_attempt_key(self, player, room):
        return f"barrier:{player.id}:{room.key}"

    def _barrier_can_attempt(self, player, room):
        return self._barrier_attempt_key(player, room) not in self.state.meta.get("barrier_attempts", [])

    def _cross_barrier(self, player):
        room = self.current_room(player)
        config = self._barrier_config(room)
        if not config or not self._barrier_can_attempt(player, room):
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
