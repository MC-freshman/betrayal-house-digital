from __future__ import annotations

from ._imports import DIRECTION_DELTAS, OPPOSITE, deque

class PathRules:
    def _build_graph(
        self, avoid_transit: bool = False, blocked: set[str] | None = None
    ) -> dict[str, set[str]]:
        # 邻接表必须是有序结构。若用 set，BFS 遍历顺序会随 PYTHONHASHSEED
        # 变化，导致同一种子在不同进程得到不同的最短路径——种子回放、
        # 存档复现、联机重放都会失效。这里用 dict 做有序去重，再输出排序列表。
        #
        # avoid_transit=True：把"进入即传送"的房间（神秘电梯）的**出边**去掉。
        # 它仍是合法终点（可以特意走进电梯），但不能被当作去别处的通路——
        # 玩家一进去就被送到随机房间，站在里面是不可能的。默认 False 保持
        # 原有行为（怪物不触发房间效果，仍可穿行）。
        #
        # blocked：机器人寻路禁区（剧本 27 的 Blob 房间：踏进去立刻被同化，
        # 真人不会走，也不该被当成抄近路的通道）。默认 None 行为完全不变。
        blocked = blocked or set()
        adjacency: dict[str, dict[str, None]] = {
            key: {}
            for key, room in self.state.board.items()
            if not room.data.get(self.COLLAPSE_KEY) and key not in blocked
        }
        for room in self.state.board.values():
            if room.data.get(self.COLLAPSE_KEY):
                continue  # 塌进深渊的板块既不是节点也不是通路
            if room.key in blocked:
                continue
            if avoid_transit and room.template_id in self.NON_TRANSIT_TEMPLATES:
                continue
            for direction in room.doors:
                if direction not in DIRECTION_DELTAS:
                    continue
                dx, dy = DIRECTION_DELTAS[direction]
                pos = (room.floor, room.x + dx, room.y + dy)
                target_key = self.state.pos_index.get(pos)
                if not target_key:
                    continue
                target = self.state.board[target_key]
                if target.data.get(self.COLLAPSE_KEY) or target_key in blocked:
                    continue
                if OPPOSITE[direction] in target.doors:
                    adjacency[room.key][target_key] = None
                    adjacency[target_key][room.key] = None
            for link_value in room.links.values():
                target_key = self._link_target_key(link_value)
                if (
                    target_key
                    and target_key not in blocked
                    and not self.state.board[target_key].data.get(self.COLLAPSE_KEY)
                ):
                    adjacency[room.key][target_key] = None
                    adjacency[target_key][room.key] = None
        graph = {key: sorted(neighbors) for key, neighbors in adjacency.items()}
        if avoid_transit:
            # 传送房的**出边**要最后统一清掉：邻居房间遍历时会做对称补边，
            # 只在自己那一趟跳过（上面的 continue）挡不住它们把出边加回来。
            # 清掉之后：进得去（别人到它的边还在，可作为终点），出不来（不能当中转）。
            for key, room in self.state.board.items():
                if room.template_id in self.NON_TRANSIT_TEMPLATES and key in graph:
                    graph[key] = []
        return graph

    def _reachable_nodes(self, start_key: str, graph: dict[str, list[str]]) -> set[str]:
        visited = {start_key}
        queue = deque([start_key])
        while queue:
            key = queue.popleft()
            for neighbor in graph.get(key, ()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        return visited

    def _path_length(
        self,
        start_key: str,
        target_key: str,
        avoid_transit: bool = False,
        blocked: set[str] | None = None,
    ) -> int:
        """两房间之间的步数（相邻为 1，同房间为 0，不可达返回 9999）。

        修正说明：_shortest_path 返回的是**包含起点**的节点序列，所以步数
        是 长度 - 1。过去直接返回 len(path)，导致距离整体多算 1
        （自己房间算出 1、相邻房间算出 2）。

        更严重的是：没找到路径时 _shortest_path 也返回 [start_key]，
        与"同房间"无法区分，于是不可达的房间被算成距离 1——比真正相邻的
        房间（2）还要近，9999 这个哨兵值从来没生效过。后果是怪物会优先
        追那些根本走不到的目标。

        avoid_transit=True：不把传送房（神秘电梯）当中转，见 _build_graph。
        blocked：机器人寻路禁区，见 _build_graph（默认 None 行为不变）。
        """
        if start_key == target_key:
            return 0
        path = self._shortest_path(
            start_key, target_key, avoid_transit=avoid_transit, blocked=blocked
        )
        if len(path) < 2:
            return 9999
        return len(path) - 1

    def _shortest_path(
        self,
        start_key: str,
        target_key: str,
        avoid_transit: bool = False,
        blocked: set[str] | None = None,
    ) -> list[str]:
        if start_key == target_key:
            return [start_key]
        graph = self._build_graph(avoid_transit=avoid_transit, blocked=blocked)
        if (avoid_transit and start_key in self.state.board
                and self.state.board[start_key].template_id in self.NON_TRANSIT_TEMPLATES):
            # 已在传送房内可以离开；「不把它当中转」不应把起点的所有出口抹掉。
            graph[start_key] = self._build_graph(blocked=blocked).get(start_key, [])
        queue = deque([(start_key, [start_key])])
        visited = {start_key}
        while queue:
            key, path = queue.popleft()
            for neighbor in graph.get(key, ()):
                if neighbor in visited:
                    continue
                new_path = path + [neighbor]
                if neighbor == target_key:
                    return new_path
                visited.add(neighbor)
                queue.append((neighbor, new_path))
        return [start_key]

    def _link_target_key(self, link_value: str) -> str | None:
        """把链接目标解析为板块 key。
        静态链接（如楼梯）存的是模板 id，动态链接（如密道）存的是板块 key。"""
        if link_value in self.state.board:
            return link_value
        for key, room in self.state.board.items():
            if room.template_id == link_value:
                return key
        return None
