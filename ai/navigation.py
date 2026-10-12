from __future__ import annotations

from ._imports import ExitOption, GameEngine, Player, get_haunt_ai_profile

class NavigationDecisions:
    def _choose_move_option(self, engine: GameEngine, player: Player, options: list[ExitOption],
                            ranked: list[ExitOption] | None = None) -> ExitOption | None:
        if not options:
            return None
        if ranked is None:
            ranked = self._rank_move_options(engine, player, options)
        if not ranked:
            return None
        if player.bot_difficulty == "easy" and len(ranked) > 1 and engine.rng.random() < 0.35:
            return ranked[1]
        return ranked[0]

    def _bot_path_filters(
        self, engine: GameEngine, player: Player
    ) -> tuple[set[str], set[str]]:
        """剧本声明的寻路禁区与危险房（duck-typed，默认空 → 行为不变）。

        · 禁区 `bot_blocked_rooms`：不走进去、也不作为路径中转（27 号 Blob
          房间：踏进去立刻被同化，真人不会走，也不该被当成抄近路的通道）。
        · 危险房 `bot_hazard_rooms`：可以靠近/经过（贴边做检定要做），但不该
          在本回合结束时留在里面（27 号扩张圈：下个怪物回合被吞）。评分时
          "走进去就没步数退出来"重扣。
        """
        handler = engine._mode_handler()
        blocked_fn = getattr(handler, "bot_blocked_rooms", None)
        hazard_fn = getattr(handler, "bot_hazard_rooms", None)
        blocked = set(blocked_fn(engine, player) or ()) if callable(blocked_fn) else set()
        hazards = set(hazard_fn(engine, player) or ()) if callable(hazard_fn) else set()
        return blocked - {player.room_key}, hazards

    def _rank_move_options(self, engine: GameEngine, player: Player, options: list[ExitOption]) -> list[ExitOption]:
        profile = self._side_profile(engine, player)
        blocked_rooms, hazard_rooms = self._bot_path_filters(engine, player)
        wants_explore = self._bot_wants_explore(engine, player)
        next_targets = self._next_steps_toward_objectives(engine, player, profile)
        # 剧本层面的目标（该去哪个房间完成剧本任务）。权重刻意低于"追杀"：
        # 先顾眼前的战斗，再顾剧本推进，但也明显高于单纯探索，避免被探索
        # 加分盖过去。
        haunt_targets = (
            self._haunt_goal_targets(engine, player)
            if engine.state.phase == "HAUNT_PHASE"
            else set()
        )
        haunt_goals = self._next_steps_toward(engine, player, haunt_targets)
        if haunt_targets and getattr(engine._mode_handler(), "bot_goal_exclusive", False):
            # 定制后勤目标优先于追杀；同房仍可按规则反击。
            next_targets = set()
        current_threat = self._room_threat(engine, player, player.room_key)
        retreat_allowed = self._retreat_available(engine, player)
        # 认准的那一间：它压过通用目标房间表（+130）——那张表里混着阁楼、
        # 卧室之类的"通用宝地"，会把真正的剧本目标挤掉（2 号实测：英雄被
        # 楼上房间牵着走，五芒星室就在三层外也不去，降灵会开不起来）。
        # 缺关键牌（wants_explore）时不承诺：那时目标是"翻遍房子找牌"。
        committed_target = (
            self._commit_haunt_goal(engine, player, haunt_targets)
            if haunt_targets and not wants_explore
            else None
        )
        committed_steps = (
            self._next_steps_toward(engine, player, {committed_target})
            if committed_target
            else set()
        )
        target_rooms = set(profile.get("target_rooms", []) or [])
        avoid_rooms = set(profile.get("avoid_rooms", []) or [])
        if wants_explore:
            # 剧本明说"关键牌还压在牌堆里、必须去翻出来"时，目标房间的吸引力
            # 必须先让路：圣徽没到手时，五芒星室是间空屋子，站在那儿干等不是
            # 人的打法——去翻新房间抽预兆牌才是。9 号实测：英雄在五芒星室
            # 空站 351 次，圣徽始终留在预兆牌堆里。
            target_rooms = set()
        previous_room_key = self._previous_room_by_player.get(player.id)
        # 探索阶段：站在"该探索的楼层"上时，就地翻门要压过"走去别的待探索房间"。
        # 缺这一条时，前沿寻路的 +130 永远高于探索的 +110（hard），机器人会在
        # 全屋各个待探索房间之间来回跑、却一间也不翻——seed101/4p 实测 300 回合
        # 只探到 26 间房、预兆只出了 2 张，作祟永远不开始，四个剧本全卡在探索期。
        explore_floor = (
            self._exploration_target_floor(engine, player) if engine.state.phase == "EXPLORE" else None
        )
        current_floor = engine.current_room(player).floor if explore_floor is not None else None
        # 剧本目标房间所在的楼层。换层惩罚（-18）原本无差别地压过一切，
        # 导致"目标在别的楼层"的剧本里，机器人永远不下地下室/不上楼
        # （70 号实测：吸血鬼形态差一间地下室的墓穴，叛徒在楼上打转 300 回合）。
        haunt_goal_floors = {
            engine.state.board[key].floor
            for key in haunt_goals
            if key in engine.state.board
        }
        if wants_explore:
            # 缺关键牌：剧本行动房（如还没拿到圣徽时的五芒星室）这时是间空屋子，
            # 站在那儿干等不是人的打法；目标是"去还没翻开的门前翻牌"。所以先把
            # 剧本目标房间的吸引力撤下来（否则 2 号那种 next+haunt 叠到 255 的
            # 房间永远压着探索的 135，而通往其它前沿的最短路又恰好穿过它，
            # 机器人就在它和邻居之间来回——9 号实测空站 351 次）。
            haunt_goals = set()
            # 但"去别的楼层的前沿"不能被换层惩罚挡住，把有待翻门位的楼层
            # 一并算进"该去的楼层"。
            haunt_goal_floors |= {
                floor
                for floor in (-1, 0, 1)
                if engine.exploration_frontier_keys(floor)
            }

        def score(option: ExitOption) -> int:
            value = 0
            if option.direction == "cross_barrier" and haunt_targets:
                return 350  # 已到障碍房，但目标出口在另一侧。
            if retreat_allowed and option.target_key in engine.state.board:
                threat = self._room_threat(engine, player, option.target_key)
                if threat < current_threat and option.target_key not in hazard_rooms:
                    value += 500  # 先退出明显不利的战斗，再恢复胜利目标。
            if option.target_key in committed_steps:
                # 认准的剧本目标：高于一切常驻目标，机器人才会"一条路走到底"。
                value += {"easy": 100, "normal": 130, "hard": 165}.get(
                    player.bot_difficulty, 130
                )
            if option.target_key in next_targets:
                value += 130 if player.bot_difficulty == "hard" else 100
            if option.target_key in haunt_goals:
                # 剧本目标房间。与追杀同档：剧本任务是主要取胜路径，
                # 权重太低会被"追杀最近的怪"永久压制——剧本 4 实测中
                # 蜘蛛一直在动，英雄就永远在追它、永远不去打网。
                value += 125 if player.bot_difficulty == "hard" else 95
            if engine.state.phase == "EXPLORE" and option.is_new_room:
                value += {"easy": 45, "normal": 80, "hard": 95}.get(player.bot_difficulty, 80)
                if explore_floor == current_floor:
                    # 就站在该探的楼层上：翻门（+45 → 155）优先于"走去别的前沿"
                    # （+130），否则整局都在前沿之间打转，见上方 explore_floor 注释。
                    value += 45
            if option.is_new_room:
                if engine.current_room(player).template_id == "mystic_elevator":
                    # 电梯移走会拆掉唯一连接；先走到固定房间，再从固定房间探索。
                    value -= 400
                value += 15
                if wants_explore:
                    # 剧情目标牌还没露面 → 翻新房间比"去王座干等"更接近胜利。
                    # 明确探索意图优先于剧本目标与常驻追击，但仍保留危险房和
                    # 受威胁时的撤退权重，避免探索加分压过生存决策。
                    value += 140
                    exploration_bonus = getattr(
                        engine._mode_handler(), "bot_exploration_bonus", None
                    )
                    if callable(exploration_bonus):
                        value += int(exploration_bonus(engine, player) or 0)
            room = engine.state.board.get(option.target_key)
            if room:
                if option.target_key == previous_room_key:
                    value -= 55
                if (
                    room.template_id in engine.NON_TRANSIT_TEMPLATES
                    and option.target_key not in haunt_goals
                    and option.target_key not in committed_steps
                ):
                    # 进入即被随机传送的房间（神秘电梯）：不是剧本明确目标就别进。
                    # 人不会为了抄近路赌一次随机传送；机器人却会因为它是"前沿"
                    # 或在中转路径上而走进去（seed137/4p）。扣分只影响优先级，
                    # 真的没别的选择时仍然会走。
                    value -= 70
                if engine.state.phase == "EXPLORE" and room.visit_count == 0:
                    value += 20
                if engine.state.phase == "EXPLORE":
                    # 目标楼层由 _next_steps_toward_objectives 决定；这里的前沿数量
                    # 只做轻微的同楼层偏好，不能压过前往另一层的明确路线。
                    # 上限 6：不封顶时"前沿越多、已有房间越香"——房子一大
                    # （前沿 ≥13 间）就永远压过"就地翻门"的 155，机器人从此
                    # 不再探索、整局在几间屋子间绕圈（seed131/3p 实测：
                    # 48/49 房间铺满后停在探索期 400 回合，最后一张预兆房
                    # 明明放得下却没人去翻）。
                    value += 2 * min(6, len(engine.exploration_frontier_keys(room.floor)))
                if engine.room_items(room.key):
                    value += 50 if player.bot_difficulty == "hard" else 35
                if room.name in target_rooms or room.template_id in target_rooms:
                    value += 95 if player.bot_difficulty == "hard" else 70
                if room.name in avoid_rooms or room.template_id in avoid_rooms:
                    value -= 90 if player.bot_difficulty == "hard" else 55
                if option.target_key in blocked_rooms:
                    # 剧本禁区（27 号 Blob 房间：踏进去立刻被同化）。扣到成负分，
                    # 只有真的无路可走时才会走——真人同样宁可不走近路。
                    value -= 400
                elif option.target_key in hazard_rooms and (
                    player.steps_remaining - option.cost <= 0
                    or engine.room_stop_risk(room)
                ):
                    # 剧本危险房（27 号扩张圈：下个怪物回合必被吞）：进去以后
                    # 一步不剩＝要在里面过夜。贴边看一眼就走是可以的，留宿不行，
                    # 所以只在"没步数退出来"时重扣，不禁止靠近。
                    # 另一类同样致命：进房可能立刻终止移动的效果房（保险库/
                    # 研究实验室抽牌、煤导槽/坍塌房传送、深渊/地下墓穴/地下湖
                    # 检定失败停下）——进去就退不出来，等于把命交给掷骰。
                    value -= 400
                value -= self._danger_penalty(player, room.effect_id)
                # 英雄走位三项扣分（均为新增情形，系数均小于追击 +100 / 剧本
                # 目标 +95 的正分，不会压过取胜主线）：
                if player.role == "hero":
                    # 分散：目标房间已有 ≥2 名存活同阵营英雄 → −40
                    same_heroes = sum(
                        1
                        for p in engine.state.players
                        if p.role == "hero" and not p.dead and p.id != player.id and p.room_key == option.target_key
                    )
                    if same_heroes >= 2 and not any(m.room_key == room.key and m.stunned_turns <= 0 for m in engine.state.monsters):
                        value -= 40
                    room_monsters = [
                        m
                        for m in engine.state.monsters
                        if m.room_key == option.target_key and m.stunned_turns <= 0
                    ]
                    if room_monsters:
                        threat = self._room_threat(engine, player, room.key)
                        # 有风险仍须完成目标；封顶避免把唯一取胜房间永久排除。
                        value -= 35 * min(3, threat)
                        if same_heroes:
                            value += 25  # 有同伴时允许会合清场，独自冲强敌则继续扣分。
                        weapon_ids = [None] + engine.available_attack_weapons(player)
                        # 打不动怪所在房：本英雄空手/任一武器都打不动的非眩晕怪 → −60
                        unbeatable = any(
                            not any(
                                engine.attack_would_be_allowed(player, m, wid, ignore_position=True)
                                for wid in weapon_ids
                            )
                            for m in room_monsters
                        )
                        if unbeatable:
                            value -= 60
                        # 力量悬殊：怪 might > 英雄 might+speed 之和 → −25
                        if any(
                            m.might > player.stats.get("might", 0) + player.stats.get("speed", 0)
                            for m in room_monsters
                        ):
                            value -= 25
            if option.target_key and option.target_key not in engine.state.board:
                # 剧本给出的"非棋盘目标"（目前只有 33 号划入湖面的 "lake:" 选项）：
                # 这是剧本明说可以走的路线，不能因为普通房间的小加分或
                # "回上一个房间"的惩罚而被永远压着不选——seed101/5p 实测过
                # 400 回合在岸上与湖面之间来回打转。
                value += 20
            if option.is_special:
                value += 4
                if option.direction in {"up", "down"}:
                    current_room = engine.current_room(player)
                    changing_floor = room.floor != current_room.floor
                    if changing_floor and not engine.has_remaining_room_cards(current_room.floor):
                        value += 95 if engine.has_remaining_room_cards(room.floor) else 15
                    elif changing_floor:
                        # 换层去剧本目标所在楼层时不再惩罚，反而加分——
                        # 否则"目标在别的楼层"的剧本永远走不出去。
                        value += 40 if room.floor in haunt_goal_floors else -18
            return value

        return sorted(options, key=score, reverse=True)

    def _haunt_goal_targets(self, engine: GameEngine, player: Player) -> set[str]:
        """作祟阶段：剧本要求机器人去哪里，而不只是"追人/追怪"。

        过去作祟阶段的寻路目标只有敌对玩家与怪物，导致机器人完全不知道
        剧本要它站到哪个房间——于是出现了这些僵局：
            · 剧本 2：英雄必须到五芒星室才能对幽灵做理智攻击，bot 不去，
              幽灵打不死，回合数空转到上限
            · 剧本 3：书掉在已故英雄脚边，bot 不知道要去捡，永远施不出
              凡人形态，女巫始终无敌
        这里把三类剧本目标一并算出来，交由 _rank_move_options 分层加分。
        返回的是**目标房间本身**，下一步由 `_next_steps_toward` 换算。
        """
        haunt = engine.state.haunt
        rule = (haunt.rule_data or {}) if haunt else {}
        if not rule:
            return set()
        flags = engine._haunt_flags()
        goals: set[str] = set()

        # 0) 剧本可提供定制目标（剧本 25：每个英雄找"自己娃娃"的候选房间，
        #    静态 rule_data 表达不了按玩家区分的目标）。duck-typed 探测，
        #    未实现该方法的 handler 保持原行为。
        handler = engine._mode_handler()
        custom_goals = getattr(handler, "bot_goal_rooms", None)
        if callable(custom_goals):
            provided = custom_goals(engine, player) or []
            if provided:
                goals.update(provided)
                if getattr(handler, "bot_goal_exclusive", False):
                    return {
                        key for goal in provided for key, room in engine.state.board.items()
                        if goal in (key, "__room__" + key, room.template_id, room.name)
                        and not engine._is_collapsed(key)
                    }

        # 0b) 剧本可声明"这个玩家此刻没有任何剧本目标房间"（区别于上面
        #     bot_goal_rooms 返回空 = 退回通用换算）。9 号实测：叛徒唯一的
        #     行动要持圣徽才能做，而 key_rooms 保底会把深渊/熔炉房/地下湖
        #     当成目的地，它在三间空房之间绕了 33 圈；此时它的正确目标是
        #     追杀英雄（通用追击逻辑），不该再被空目标牵着走。
        suppressed = getattr(handler, "bot_goal_suppressed", None)
        if callable(suppressed) and suppressed(engine, player):
            return set()

        # 1) 有房间要求的剧本行动：挖曼德拉草要去温室/储藏室/厨房，
        #    降灵会要去五芒星室……
        action_blocked = getattr(handler, "bot_action_blocked", None)
        for action in rule.get("actions", []):
            if not engine._haunt_side_allowed(player, str(action.get("side", "both"))):
                continue
            # 模式层已经作废的行动不再是目标。22 号"每个驱魔来源只能用一次"
            # 记在 used_exorcism_sources 里（不是 set_flags），bot 看不见就
            # 一直往用过的房间跑——实测 3/5 时三名英雄在五芒星室/花园之间
            # 空转到 400 回合。
            if callable(action_blocked) and action_blocked(
                engine, player, str(action.get("id", ""))
            ):
                continue
            # 该行动的产出已经拿到了就不必再去（例如已经挖到草）
            set_flags = action.get("set_flags", {})
            if set_flags and all(flags.get(key) == value for key, value in set_flags.items()):
                continue
            goals.update(action.get("rooms") or [])

            # 要求"与某个目标同房间"的行动，目标就是它当前所在房间：
            #   · same_room:<怪物模板>   → 该怪物所在房间（如女巫）
            #   · same_room:<令牌类型>   → 该令牌所在房间（如剧本 4 的蛛网）
            #     ——attack_web 没有 rooms 字段，过去这段解析被
            #        "if not rooms: continue" 挡在前面，蛛网房间从未成为
            #        寻路目标，英雄根本不去打网。
            #   · same_room:revealer     → 作祟揭示者所在房间（如销毁蛛卵）
            for requirement in action.get("requires", []):
                if not str(requirement).startswith("same_room:"):
                    continue
                target = str(requirement).split(":", 1)[1]
                if target == "revealer":
                    revealer = next(
                        (p for p in engine.state.players if p.id == engine.state.haunt_revealer_id),
                        None,
                    )
                    if revealer is not None and not revealer.dead:
                        goals.add("__room__" + revealer.room_key)
                    continue
                for monster in engine.state.monsters:
                    if monster.template_id == target:
                        goals.add("__room__" + monster.room_key)
                for token in engine.tokens_of_kind(target):
                    if token.room_key:
                        goals.add("__room__" + token.room_key)

        # 2) 剧本关键牌掉在地上时，去把它捡回来
        required = {str(card_id) for card_id in rule.get("required_cards", [])}
        if required:
            for room_key, items in engine.state.room_items.items():
                if required & {str(item) for item in items}:
                    goals.add("__room__" + room_key)

        # 3) 自己拿着关键牌、队友持有令牌（正在执行任务）时，去和他会合。
        #    令牌不能交易，所以只能让持牌方走过去（见 _try_share_quest_items）。
        #    剧本也可以直接指定"该把牌交给谁"（39 号继承人，quest_carrier）。
        if required & {str(item) for item in player.items}:
            carrier_id = self._quest_carrier_id(engine)
            for other in engine.state.players:
                if other.id == player.id or other.dead or other.frog:
                    continue
                if carrier_id is not None:
                    if other.id == carrier_id:
                        goals.add("__room__" + other.room_key)
                    continue
                if other.role == player.role and engine.tokens_held_by(other.id):
                    goals.add("__room__" + other.room_key)

        # 3) 剧本关键房间作为**保底**目标：只有前面几类具体目标（剧本行动房间、
        #    关键牌、令牌会合）都算不出来时才启用。以前是无条件并入，70 号实测
        #    受害最重——它的 key_rooms 有 22 间"形态可能用到的房间"，叛徒的目标
        #    集合被稀释成 19 间，承诺机制只能在最近的保底房里打转（地窖 ⇄ 地下湖），
        #    真正的形态房（雕像走廊 3 格、温室 6 格）永远排不上，转变停在 0/5。
        if not goals:
            for key_room in rule.get("key_rooms", []):
                goals.add(str(key_room))

        # 把模板 id / 房间名解析成实际房间 key
        room_keys: set[str] = set()
        for goal in goals:
            if goal.startswith("__room__"):
                room_keys.add(goal[len("__room__") :])
                continue
            for key, room in engine.state.board.items():
                if room.template_id == goal or room.name == goal:
                    room_keys.add(key)

        # 关键一步：打分比较的是"下一步走哪个房间"，所以这里换算成路径的第二格。
        # 直接返回目标房间的话，只有一步能抵达时才会加分，等于没引导。
        return room_keys

    def _next_steps_toward(self, engine: GameEngine, player: Player, room_keys: set[str]) -> set[str]:
        """把目标房间集合换算成"下一步该走进哪间"的集合。

        寻路会绕开剧本禁区（`bot_blocked_rooms`）：27 号实测，英雄从入口大厅
        去地下室方向的检定位，最短路穿过 Blob 已经吞掉的房间，机器人照走不误、
        一进去就被同化（seed101/3p 首名英雄）。
        """
        next_steps: set[str] = set()
        blocked, _hazards = self._bot_path_filters(engine, player)
        for room_key in room_keys:
            if room_key not in engine.state.board or room_key == player.room_key:
                continue
            path = engine._shortest_path(
                player.room_key, room_key, avoid_transit=True, blocked=blocked
            )
            if len(path) > 1:
                next_steps.add(path[1])
        return next_steps

    def _commit_haunt_goal(
        self, engine: GameEngine, player: Player, targets: set[str]
    ) -> str | None:
        """在一堆剧本目标里**认准一间**，并在若干回合内不换（像人一样先走到）。

        没有承诺时挑"走得通且最近"的那间（距离并列时按 key 排序取第一个，
        保证同种子可复现）；玩家已站在目标房间、目标消失或承诺过期时清掉。

        返回承诺的目标房间 key（没有可用目标时返回 None）。
        """
        turn = engine.state.turn_count
        committed = self._goal_commitment_by_player.get(player.id)
        if committed is not None:
            target_key, expires = committed
            if (
                expires > turn
                and target_key in engine.state.board
                and target_key != player.room_key
                and target_key in targets
            ):
                return target_key
            # 目标已达成/已消失/承诺过期：换一个（`target_key in targets` 这条
            # 很关键——访到形态房后它就不再是目标，死守承诺只会白站几回合）。
            self._goal_commitment_by_player.pop(player.id, None)

        reachable: list[tuple[int, str]] = []
        blocked, _hazards = self._bot_path_filters(engine, player)
        for key in sorted(targets):
            if key not in engine.state.board or key == player.room_key:
                continue
            distance = engine._path_length(
                player.room_key, key, avoid_transit=True, blocked=blocked
            )
            if distance == 9999:
                continue
            reachable.append((distance, key))
        if not reachable:
            return None
        _distance, target_key = min(reachable)
        self._goal_commitment_by_player[player.id] = (
            target_key,
            turn + self.GOAL_COMMITMENT_TURNS,
        )
        return target_key

    def _haunt_goal_rooms(self, engine: GameEngine, player: Player) -> set[str]:
        """剧本目标房间的**下一步**集合（`_haunt_goal_targets` 的路径换算）。"""
        return self._next_steps_toward(engine, player, self._haunt_goal_targets(engine, player))

    def _next_steps_toward_objectives(self, engine: GameEngine, player: Player, profile: dict) -> set[str]:
        targets: list[str] = []
        if engine.state.phase == "EXPLORE":
            current_room = engine.current_room(player)
            target_floor = self._exploration_target_floor(engine, player)
            if target_floor == current_room.floor:
                targets.extend(engine.exploration_frontier_keys(current_room.floor))
            elif target_floor is not None:
                # 跨楼层只能先走到已有的楼梯/平台，再从目标楼层的前沿继续探索。
                targets.extend(self._floor_anchor_keys(engine, target_floor))

        if engine.state.phase == "HAUNT_PHASE":
            if self._bot_wants_explore(engine, player):
                # 缺关键牌：把**每一层**还能翻门的房间都当成目标，让机器人先
                # 走到前沿再翻牌（跨层由 BFS 自动经过楼梯/平台）。缺这条，
                # 身边没有可翻门的机器人只会在几间屋子之间来回晃——9 号实测：
                # 圣徽还压在 8 张预兆牌里，英雄在一层小教堂那一带空转 180 次，
                # 永远不去楼上的前沿。
                for floor in (-1, 0, 1):
                    targets.extend(engine.exploration_frontier_keys(floor))
            if player.role == "traitor":
                # 剧本可用 chase_heroes=False 关掉"追英雄"的常驻目标（+130），
                # 让位给剧本目标（+125）——70 号实测：叛徒要访遍形态房间才能
                # 完成转变，追人权重更高时它会一路追人、从不访点，全局僵死。
                if profile.get("chase_heroes", True):
                    targets.extend(
                        other.room_key
                        for other in engine.state.players
                        if other.role == "hero" and not other.dead
                    )
            elif profile.get("attack_monsters", True):
                # 英雄追怪的两道闸门：
                # (i) 持有关键牌或剧本令牌时，优先去交付/会合而非盲目追怪；
                # (ii) 打不动的怪（免疫当前所有可用攻击属性）不值得追，省得白跑送死。
                rule = (engine.state.haunt.rule_data or {}) if engine.state.haunt else {}
                required = {str(card_id) for card_id in rule.get("required_cards", [])}
                holds_required = bool(required & {str(item) for item in player.items})
                holds_token = bool(engine.tokens_held_by(player.id))
                if not (holds_required or holds_token):
                    weapon_ids = [None] + engine.available_attack_weapons(player)
                    for monster in engine.state.monsters:
                        if monster.stunned_turns > 0:
                            continue
                        # 同源查询（忽略位置）：空手或任一武器都打不动就不追。
                        can_hurt = any(
                            engine.attack_would_be_allowed(player, monster, wid, ignore_position=True)
                            for wid in weapon_ids
                        )
                        if can_hurt:
                            targets.append(monster.room_key)
            if player.role == "hero":
                # 保护作祟揭示者（存活英雄）：其房间作为寻路目标，与 protect_humans 同档。
                revealer = next(
                    (p for p in engine.state.players if p.id == engine.state.haunt_revealer_id),
                    None,
                )
                if revealer is not None and not revealer.dead and revealer.role == "hero":
                    targets.append(revealer.room_key)
                if player.bot_difficulty == "hard" and profile.get("protect_humans", True):
                    for human in engine.state.players:
                        if human.control == "human" and human.role == "hero" and not human.dead:
                            targets.append(human.room_key)

        wanted_rooms = set(profile.get("target_rooms", []) or [])
        if wanted_rooms and not self._bot_wants_explore(engine, player):
            # 缺关键牌时目标房间不再是目的地（见 _rank_move_options 的同款判断）
            for key, room in engine.state.board.items():
                if room.name in wanted_rooms or room.template_id in wanted_rooms:
                    targets.append(key)

        next_steps: set[str] = set()
        blocked, _hazards = self._bot_path_filters(engine, player)
        for target_key in targets:
            # avoid_transit=True：不能把"进入即传送"的神秘电梯当中转。默认
            # 路径会把它当普通房间穿过去，机器人于是主动走进电梯、被丢到随机
            # 楼层（seed137/4p 实测 400 行日志里 15 次进电梯、17 次被传送）。
            # blocked：同 _next_steps_toward，绕开剧本禁区。
            path = engine._shortest_path(
                player.room_key, target_key, avoid_transit=True, blocked=blocked
            )
            if len(path) > 1:
                next_steps.add(path[1])
        return next_steps

    def _exploration_target_floor(self, engine: GameEngine, player: Player) -> int | None:
        current_floor = engine.current_room(player).floor
        floors = [floor for floor in (-1, 0, 1) if engine.has_remaining_room_cards(floor)]
        if not floors:
            return None

        # 用已放置房间数 / (已放置 + 剩余牌数) 衡量楼层进度。旧逻辑只看当前
        # 楼层是否还有牌，导致机器人永远在一层的新门位上打转，根本不会去二层。
        # 选择进度最低的楼层，并用玩家编号稳定打散平局，让机器人自然分工。
        progress: dict[int, float] = {}
        for floor in floors:
            placed = sum(1 for room in engine.state.board.values() if room.floor == floor)
            remaining = sum(
                1
                for room_id in (*engine.state.room_deck, *engine.state.room_discard)
                if room_id in engine.catalog.room_templates
                and engine.catalog.room_templates[room_id].floor == floor
            )
            progress[floor] = placed / max(1, placed + remaining)

        lowest = min(progress.values())
        candidates = [floor for floor in floors if progress[floor] <= lowest + 0.025]
        # 当前楼层有可探索前沿时给一个很小的稳定偏好，避免刚到某层就立即折返；
        # 但不会改变明显落后楼层的优先级。
        if current_floor in candidates and engine.exploration_frontier_keys(current_floor):
            last_floor = self._last_exploration_floor_by_player.get(player.id)
            if last_floor == current_floor or len(candidates) == 1:
                return current_floor
        return candidates[player.id % len(candidates)]

    def _floor_anchor_keys(self, engine: GameEngine, floor: int) -> list[str]:
        anchor_ids = {
            -1: ("basement_landing", "stairs_from_basement"),
            0: ("entrance_hall", "grand_staircase"),
            1: ("upper_landing",),
        }.get(floor, ())
        anchors = [
            room.key
            for room in engine.state.board.values()
            if room.floor == floor and room.template_id in anchor_ids
        ]
        if anchors:
            return anchors
        return [room.key for room in engine.state.board.values() if room.floor == floor]

    def _danger_penalty(self, player: Player, effect_id: str) -> int:
        risky_physical = {"room_bloody_room", "room_furnace_room", "room_chasm", "room_collapsed_room", "room_tower"}
        risky_mental = {"room_charred_room"}
        if effect_id in risky_physical and min(player.stats.get("speed", 0), player.stats.get("might", 0)) <= 2:
            base = 55 if player.bot_style == "cautious" else 20 if player.bot_style == "aggressive" else 35
            return base + (25 if player.bot_difficulty == "hard" else -15 if player.bot_difficulty == "easy" else 0)
        if effect_id in risky_mental and min(player.stats.get("sanity", 0), player.stats.get("knowledge", 0)) <= 2:
            base = 55 if player.bot_style == "cautious" else 20 if player.bot_style == "aggressive" else 35
            return base + (25 if player.bot_difficulty == "hard" else -15 if player.bot_difficulty == "easy" else 0)
        return 0

    def _side_profile(self, engine: GameEngine, player: Player) -> dict:
        haunt_id = engine.state.haunt.id if engine.state.haunt else None
        profile = get_haunt_ai_profile(haunt_id)
        key = "traitor" if player.role == "traitor" else "hero"
        return dict(profile.get(key, {}))
