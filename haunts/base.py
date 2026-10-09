"""剧本行为按 mode 分派（haunt mode 基础设施）。

拆分说明（2026-10-06）
----------------------
本文件由 haunt_modes.py 机械拆分而来：协议/通用基类/数据类/常量/注册机制/
共享助手逐字保留自原模块顶层；具体剧本 handler 见同包 haunt_XX_*.py；
兼容入口仍是 game/haunt_modes.py 门面。

背景
----
70 个剧本在 `haunt_rules.py` 里各有一个唯一 `mode`（werewolf_hunt、
labyrinth_escape、banishment_escort …）。但引擎原本是这样分派的：

    if self.state.haunt.id == 1:  return self._available_haunt1_actions(player)
    if self.state.haunt.id == 5:  return self._available_haunt5_actions(player)
    return self._available_generic_haunt_actions(player)

也就是说：mode 字段写在数据里、引擎从不读取，是死数据；剧本行为只能靠
在引擎里加 `haunt.id == N` 分支来扩展。严格复刻 70 个剧本时，这条路会
把 engine.py 撑爆，而且每加一个剧本都要改引擎。

本模块把分派改成按 mode 查表：
    注册了 handler 的 mode  → 走定制逻辑
    没注册的 mode           → 走 GenericModeHandler（现有通用规则）
这样新增剧本行为只需在这里加一个类，不必碰引擎。

设计约束
--------
* handler 用鸭子类型，不 import engine，避免循环导入。engine 在运行时
  才 import 本模块。
* 未注册的 mode 必须优雅降级到通用规则，绝不能抛异常——否则一个没写
  handler 的剧本就会让整个作祟阶段崩掉。
* 本模块只负责「怎么分派」，具体规则实现仍在 engine / haunt_rules，
  避免把引擎逻辑复制到这里造成第二份维护。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

# 方位→格偏移（与 models.py 保持一致，避免 import engine 循环导入）
DIRECTION_DELTAS = {"north": (0, -1), "east": (1, 0), "south": (0, 1), "west": (-1, 0)}


class HauntAction:
    """与 engine.HauntAction 同构的轻量副本（避免 import engine 循环导入）。

    46 号在"已逃出的英雄可以重新进门"时需要即时造一个行动对象追加到
    可用列表里——过去直接写了 `HauntAction(...)`，但本模块从不 import
    engine，于是这个分支一旦走到就 NameError。3/4 人局碰不到该分支，
    直到 M10-15 的 5 人局扩容扫描才暴露出来。
    """

    __slots__ = ("id", "label", "detail", "data")

    def __init__(self, action_id: str, label: str, detail: str = "", data: dict | None = None):
        self.id = action_id
        self.label = label
        self.detail = detail
        self.data = data if data is not None else {}


class ExitOption:
    """与 engine.ExitOption 同构的轻量副本（避免 import engine 循环导入）。"""

    __slots__ = ("label", "direction", "target_key", "target_room_name", "is_new_room", "is_special", "cost")

    def __init__(self, label: str, direction: str, target_key: str,
                 target_room_name: str | None = None, is_new_room: bool = False,
                 is_special: bool = False, cost: int = 1):
        self.label = label
        self.direction = direction
        self.target_key = target_key
        self.target_room_name = target_room_name
        self.is_new_room = is_new_room
        self.is_special = is_special
        self.cost = cost


@runtime_checkable
class HauntModeHandler(Protocol):
    """一个剧本模式的行为。

    参数里的 engine / player 用 Any 是刻意的：本模块若 import engine 会
    形成循环依赖。实现方按 GameEngine / Player 的真实接口调用即可。
    """

    mode: str

    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        """返回该玩家此刻可执行的剧本行动。"""
        ...

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        """执行一个剧本行动，返回是否成功。"""
        ...

    def check_victory(self, engine: Any) -> bool:
        """检查该模式的专属胜负条件，返回是否已分出胜负。"""
        ...

    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        """作祟刚开始时执行一次：放令牌、补牌等。"""
        ...

    def on_enter_room(self, engine: Any, player: Any, room: Any) -> None:
        """有玩家进入房间时触发（用于令牌拾取之类）。"""
        ...

    def on_room_discovered(self, engine: Any, player: Any, room: Any) -> None:
        """房间首次被发现时触发（用于"某张牌不在场就补抽"这类规则）。"""
        ...

    def on_monster_attack(self, engine: Any, monster: Any, target: Any, amount: int) -> bool:
        """怪物命中时触发。返回 True 表示伤害已由剧本结算，引擎不再处理。"""
        ...

    def on_monster_move(self, engine: Any, monster: Any, rolled: int) -> bool:
        """怪物移动掷骰后触发。返回 True 表示剧本已自行处理移动。"""
        ...

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        """怪物被玩家攻击命中后触发。返回 True 表示剧本已处理后果。

        引擎默认"击败怪物 = 击晕一回合"，但不少剧本要求真正杀死怪物：
          · 剧本 2 p13："One of these Sanity attacks must succeed for the
            ghost to be destroyed"
          · 剧本 3 p14："After you cast the spell on her, any successful
            attack will kill her"
        没有这个钩子，怪物永远只是昏迷，这类剧本的胜利条件无法达成。
        """
        ...

    def on_monster_turn_attack(self, engine: Any, monster: Any) -> bool:
        """怪物回合的攻击阶段触发（无论掷骰成败）。返回 True 表示已接管。

        与 on_monster_attack 的区别：后者只在引擎判定怪物命中后才调用；
        而剧本 6 外星人的意念攻击是"代替普通攻击"的主动技能——对同房间
        每个探险者各自理智对决，输赢都要结算，所以需要这个更早的钩子。
        """
        ...

    def on_turn_start(self, engine: Any, player: Any) -> None:
        """玩家回合开始时触发（用于诅咒发作、计时器推进等）。"""
        ...


class GenericModeHandler:
    """默认处理器：直接执行 rule_data 里声明的 actions / win_conditions。

    当前 68 个没有定制 handler 的剧本都走这里。它把 engine 里原有的通用
    逻辑包装成 handler 接口，行为与改造前完全一致。
    """

    mode = "generic"

    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        return engine._available_generic_haunt_actions(player)

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        return engine._perform_generic_haunt_action(player, action_id, data)

    def check_victory(self, engine: Any) -> bool:
        return engine._check_generic_haunt_victory()

    # 生命周期钩子默认什么都不做，需要时由子类覆盖。
    # 引擎会无条件调用它们，所以这里不能抛异常。
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        return None

    def on_enter_room(self, engine: Any, player: Any, room: Any) -> None:
        return None

    def on_room_discovered(self, engine: Any, player: Any, room: Any) -> None:
        return None

    # 这两个返回 False 是刻意的：False = "我没处理，引擎按默认来"。
    def on_monster_attack(self, engine: Any, monster: Any, target: Any, amount: int) -> bool:
        return False

    def on_monster_move(self, engine: Any, monster: Any, rolled: int) -> bool:
        return False

    def on_turn_start(self, engine: Any, player: Any) -> None:
        return None

    def on_turn_end(self, engine: Any, player: Any) -> None:
        """每位玩家回合结束时调用（剧本 22 p104：每回合结束都要塌房间）。
        引擎在怪物回合之前调用，保证扩散与怪物行动同轮。"""
        return None

    def on_monster_defeated(self, engine: Any, monster: Any, amount: int) -> bool:
        return False

    def on_monster_turn_attack(self, engine: Any, monster: Any) -> bool:
        return False

    def on_monster_turn_start(self, engine: Any, monster: Any) -> bool:
        """每只怪物回合开始（剧本 7 的"拖回根部即吞噬"等）。True=本回合不再行动。"""
        return False

    def mystic_elevator_blocked(self, engine: Any, player: Any) -> bool:
        """神秘电梯是否被剧本机制堵住（剧本 7：藤蔓尖端在电梯房间内）。"""
        return False

    def item_pickup_blocked(self, engine: Any, player: Any, card_id: str) -> bool:
        """某张卡是否禁止被该玩家捡起（剧本 7：叛徒不能重拾古书）。"""
        return False

    def item_trade_blocked(self, engine: Any, giver: Any, target: Any, card_id: str) -> bool:
        """某张卡是否禁止被该玩家自愿交出（剧本 9：持圣徽者不能转交圣徽）。"""
        return False

    def attack_allowed(self, engine: Any, attacker: Any, target: Any) -> bool:
        """剧本是否允许这次攻击（剧本 2：降灵完成前谁都不能动手）。"""
        return True

    def monster_rerolls_blanks(self, engine: Any, monster: Any) -> bool:
        """怪物攻击时是否把空白骰重掷一次（剧本 4 蜘蛛 p86）。"""
        return False

    def on_player_moved(self, engine: Any, player: Any) -> None:
        """玩家移动后回调（剧本 3：背着青蛙走，蛙跟着主人）。"""
        return None

    def attack_attr_override(self, engine: Any, attacker: Any, target: Any, default_attr: str) -> str | None:
        """徒手攻击的属性覆盖（剧本 11：持戒指者对雾中人影改为理智攻击）。"""
        return None

    def monster_counterattack_disabled(self, engine: Any, monster: Any) -> bool:
        """昏迷怪物的反击是否无效（剧本 12 p23：昏迷双胞胎防守但无伤害）。"""
        return False

    def on_attack_resolved(self, engine: Any, attacker: Any, target: Any, attacker_won: bool) -> None:
        """攻击结算后的后处理（剧本 12：与自己的双胞胎交手必掉 1 点各属性）。"""
        return None

    def movement_cost_multiplier(self, engine: Any, player: Any, from_key: str | None = None) -> int:
        """玩家移动费用的倍率（剧本 14：背尸入房按 2 格计）。"""
        return 1

    def movement_cost_floor(self, engine: Any, player: Any, from_key: str | None = None, to_key: str | None = None) -> int:
        """玩家移动费用的下限（剧本 17：蟑螂守厨房离开 3 格；剧本 33：湖面砖 2/3 格）。"""
        return 0

    def attack_loss_damage_disabled(self, engine: Any, attacker: Any, target: Any) -> bool:
        """攻击落败时是否免除攻击者受到的反击伤害（剧本 17：用杀虫剂落败不受伤）。"""
        return False

    def defense_roll_disabled(self, engine: Any, attacker: Any, target: Any, weapon_card_id: str | None = None) -> bool:
        """防守方是否无法防御这次攻击（剧本 41 p123：隐形叛徒的偷袭）。

        返回 True 时引擎把防守方掷骰按 0 结算（攻击骰直接成为伤害）。默认
        False，即正常对抗——不实现该钩子的剧本行为完全不变。
        """
        return False

    def defense_roll_override(self, engine: Any, attacker: Any, target: Any, weapon_card_id: str | None = None) -> int | None:
        """防守方是否改用固定骰数结算（剧本 52 p134：叛徒总是以 3 骰防守，
        与自身属性和攻击者所用武器无关）。

        返回 None = 按常规掷骰（默认，所有未实现它的剧本行为不变）；
        返回整数 = 直接以该值作为防守方掷骰结果。钩子只在真实执行的
        攻击路径上调用，bot 的预判查询不会触发掷骰。
        """
        return None

    def damage_reduction_label(self, engine: Any, player: Any) -> str:
        """伤害减免在日志里的来源名（默认"护甲"；剧本 52 是戒指的魔力）。"""
        return "护甲"

    def special_steal(self, engine: Any, attacker: Any, target: Any, diff: int, attack_attr: str) -> bool:
        """剧本自定义的特殊偷取（剧本 19：>2 伤害偷走长矛）。返回 True 表示已处理。"""
        return False

    def attack_kill_override(self, engine: Any, attacker: Any, target: Any, weapon: Any) -> bool:
        """剧本接管这次攻击的击杀结算（剧本 5 p15：银弹打中狼人/狼犬即死）。

        返回 True 表示目标已由剧本处理——引擎跳过常规伤害结算，只结算武器
        损耗、攻击占用与胜负检查；返回 False（默认）走常规流程。
        """
        return False

    def on_hero_damaged(self, engine: Any, attacker: Any, target: Any) -> None:
        """英雄被击中后的剧本副作用（剧本 5 p14：被叛徒或狼犬打中即感染）。

        attacker 可能是玩家（玩家攻击路径）也可能是怪物（怪物攻击路径），
        来源判断由剧本自己做。只在目标确为英雄时调用。
        """
        return None

    def damage_amount_override(self, engine: Any, player: Any, amount: int, source: str, damage_type: str) -> int | None:
        """剧本整体改写一次伤害的数值（剧本 5 p85：狼人受到的非银弹伤害减半）。

        返回 None（默认）表示不改写，继续走常规的减免逻辑（护甲等）。
        返回整数则直接以该值作为最终伤害。
        """
        return None

    def extra_move_options(self, engine: Any, player: Any, options: list) -> list:
        """追加额外移动选项（剧本 33：湖面砖扩展）。"""
        return []

    def lake_move(self, engine: Any, player: Any, option: Any) -> bool:
        """接管 lake: 前缀的移动选项（剧本 33）。返回 True 表示已处理。"""
        return False

    def on_item_dropped(self, engine: Any, player: Any, card_id: str) -> None:
        """物品丢弃后处理（剧本 33：湖面丢弃即沉没）。"""
        return None

    def on_player_died(self, engine: Any, player: Any) -> None:
        """玩家死亡后的后处理（剧本 14：尸体留在房间里可被搬走）。"""
        return None

    def attack_roll_bonus(self, engine: Any, attacker: Any, target: Any) -> int:
        """对怪物攻击的骰值加值（剧本 15：持矛对巨龙 +4）。"""
        return 0

    def physical_damage_reduction(self, engine: Any, player: Any, amount: int, source: str, damage_type: str) -> int:
        """物理伤害减免（剧本 15：古董护甲 -5，对火焰无效）。"""
        return 0

    def suppress_room_draw(self, engine: Any, player: Any, room: Any) -> bool:
        """本次发现房间是否跳过符号抽牌（剧本 16：改为攻击幻影）。"""
        return False

    def monster_killed_on_defeat(
        self, engine: Any, monster: Any, attacker: Any, attack_attr: str, weapon_id: str
    ) -> bool:
        """这次击败怪物是「直接杀死」还是「仅击晕」（剧本 21 p32：只有力量武器
        与炸药能杀死僵尸，徒手或其他属性只能打晕）。

        返回 True = 杀死（引擎调用 `_kill_monster` 移出对局）。
        优先级高于 `on_monster_defeated`：需要知道"谁用什么打的"就覆盖这个，
        只按怪物类型判定的仍用 `on_monster_defeated`。
        """
        return False

    def monster_attack_roll_bonus(self, engine: Any, monster: Any, target: Any) -> int:
        """怪物主动攻击某目标时的攻击骰修正（剧本 21 p32：圣徽持有者让僵尸
        少掷两枚骰）。默认 0 = 不修正。"""
        return 0

    def explore_stop_suspended(self, engine: Any, player: Any) -> bool:
        """本剧本是否解除「探索新房间必须停下」的限制（剧本 25 p36）。

        返回 True 时引擎在探索新房间后不再强制结束移动、不再清空步数；
        配合 `suppress_room_draw` 把符号抽牌推迟到"结束移动的房间"再结算。
        """
        return False

    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        """剧本定制的 bot 寻路目标（可选，duck-typed，bot_ai 会探测）。

        返回模板 id 列表或 ["__room__<room_key>", ...]；返回空则 bot 退回
        rule_data 的通用换算（actions 的 rooms / same_room / key_rooms）。
        剧本 25 首个使用者：每个英雄要找的是"自己娃娃"的两个候选房间，
        rule_data 的静态 rooms 表表达不了按玩家区分的目标。
        """
        return []

    def bot_stay_in_room(self, engine: Any, player: Any) -> bool:
        """True = 机器人这回合不要离开当前房间（等人、等下一步检定）。"""
        return False

    def bot_blocked_rooms(self, engine: Any, player: Any) -> set[str]:
        """机器人寻路禁区：不走进、也不作为路径中转的房间（可选，duck-typed）。

        剧本 27 首个使用者：Blob 房间对非 Blobperson 是"踏进去立刻被同化"，
        真人不会走，引擎默认图里却把它当普通通路。默认空集合，行为不变。
        """
        return set()

    def bot_hazard_rooms(self, engine: Any, player: Any) -> set[str]:
        """机器人险房：可以靠近/经过，但不该在本回合结束时留在里面（可选）。

        剧本 27 首个使用者：Blob 扩张圈——贴边做完检定/投掷后必须退开，否则
        下一个怪物回合被吞。bot_ai 只在"走进去就没步数退出来"时重扣。
        """
        return set()

    def bot_leave_after_action(self, engine: Any, player: Any) -> bool:
        """True = 本回合剧本行动做完后不要原地等下一回合（可选，duck-typed）。

        剧本 27 首个使用者：贴边检定后留在扩张圈里＝下个怪物回合被同化。
        默认 False，其它剧本"原地等下一步"的行为不变。
        """
        return False

    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        """剧本进度摘要（可选，duck-typed，桌面 UI 面板会探测）。

        返回公开信息的可读行；通用轨道（value/target）由 UI 自己渲染，
        这里只补充轨道表达不了的内容（销毁计数、状态标记等）。
        """
        return []

    def room_entry_blocked(self, engine: Any, player: Any, room: Any) -> bool:
        """该玩家是否禁止进入/探索该房间（剧本 26：英雄与老鼠进不了五芒星室）。

        引擎在两处调用：`available_move_options` 过滤已有的相邻房间选项；
        探索新房间抽牌时若抽到被禁的模板则弃掉重抽。room 可能是 PlacedRoom
        也可能是 RoomTemplate（探索场景），判断时读 template_id / id 即可。
        """
        return False

    def can_discover_rooms(self, engine: Any, player: Any) -> bool:
        """该玩家能否发现新房间（剧本 27：Blobperson 不能发现房间，p109）。

        返回 False 时引擎在探索新房间前直接拦下（与青蛙的处理同款）。
        """
        return True

    def counts_as_movement_obstacle(self, engine: Any, mover: Any, occupant: Any) -> bool:
        """该占用者是否让对手离开房间多花 1 格（剧本 67：入定的叛徒不阻挡）。"""
        return True

    def item_use_blocked(self, engine: Any, player: Any, card_id: str) -> bool:
        """该玩家是否禁止主动使用物品（剧本 67：入定的叛徒不能用物品）。"""
        return False

    def action_room_override(self, engine: Any, player: Any, action: dict) -> bool:
        """剧本行动的地点豁免。返回 True = 忽略该行动的 rooms 要求。

        剧本 2 p84：叛徒持有通灵板时可以在任何地方举行降灵会。默认不豁免，
        未实现该钩子的剧本行为完全不变。
        """
        return False


# mode 字符串 -> handler 实例。新增剧本行为时在这里登记即可。
_MODE_HANDLERS: dict[str, HauntModeHandler] = {}


def register_mode(handler: HauntModeHandler) -> None:
    _MODE_HANDLERS[handler.mode] = handler


OPPOSITE_DOOR = {"north": "south", "south": "north", "east": "west", "west": "east"}



OPPOSITE_DOOR = {"north": "south", "south": "north", "east": "west", "west": "east"}


def name_map(engine: Any, monster: Any) -> str:
    return str(getattr(monster, "name", "巨虫"))

def _is_last_in_round(engine: Any, player: Any) -> bool:
    """判断 player 是否是"本轮最后一名存活玩家"。

    叛徒已出局的剧本要靠 on_turn_end 驱动每轮一次的时钟（怪物回合、
    触手成长、蝙蝠入室……）。turn_order 是循环队列：若下一个活人的位置索引
    不大于当前位置，说明轮转即将绕回开头——当前玩家就是本轮末尾。
    """
    alive = {p.id for p in engine.state.players if not p.dead}
    if player.id not in alive:
        return False
    order = engine.state.turn_order
    total = len(order)
    if not total:
        return True
    for step in range(1, total + 1):
        nxt = (engine.state.turn_index + step) % total
        if order[nxt] in alive:
            return nxt <= engine.state.turn_index
    return True


def _monster_id(monster: Any) -> str:
    """取怪物模板 id，取不到就返回空串。

    引擎会无条件调用 on_monster_* 这组钩子。若某个调用点传来的不是
    Monster（例如怪物已被移除后残留的引用），直接读 .template_id 会抛
    AttributeError 让整局崩溃——所以统一走这个防御式取值。
    """
    return str(getattr(monster, "template_id", "") or "")


def get_mode_handler(mode: str | None) -> HauntModeHandler:
    """按 mode 取 handler；没有定制实现时回落到通用规则。

    这里刻意不抛异常：未注册的 mode 是常态（68 个剧本如此），回落是设计
    行为而不是错误。
    """
    if not mode:
        return _MODE_HANDLERS["generic"]
    return _MODE_HANDLERS.get(mode, _MODE_HANDLERS["generic"])


def registered_modes() -> list[str]:
    return sorted(_MODE_HANDLERS)


__all__ = [
    "Any",
    "DIRECTION_DELTAS",
    "ExitOption",
    "GenericModeHandler",
    "HauntAction",
    "HauntModeHandler",
    "OPPOSITE_DOOR",
    "Protocol",
    "_MODE_HANDLERS",
    "_is_last_in_round",
    "_monster_id",
    "get_mode_handler",
    "name_map",
    "register_mode",
    "registered_modes",
    "runtime_checkable",
]
