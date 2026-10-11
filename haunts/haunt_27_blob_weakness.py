"""AmokFleshMode（剧本 27）—— 机械拆分自动生成头，类体逐字保留自 haunt_modes.py。

权威原文、已核对项与已知简化见下方类 docstring（原文未动）。
"""
from __future__ import annotations

from typing import Any
from .base import (  # noqa: F401  机械拆分：按引用自动生成
    GenericModeHandler,
    _is_last_in_round,
)


class AmokFleshMode(GenericModeHandler):
    """剧本 27 失控的血肉（Amok Flesh）。

    权威原文：英雄手册 p38 / 叛徒手册 p109。

    已按原文实现：
        · Blob 不是怪物——是单团不断扩张的肉体，用房间集合
          （flags["blob_rooms"]）表示；实体桌游的 ≥20 枚令牌只是计数手段，
          引擎不设上限（ Blob 令牌不可被影响、不攻击，p109）。
        · 开局（p38/p109）：叛徒仍在场；持水晶球者弃掉它，Blob 从水晶球
          所在房间开始生长。没人持球时按叛徒所在房起算（原文默认作祟由
          水晶球触发，校准回退）。
        · 扩张（p109）：第一个怪物回合吞没起源房 + 门邻房；之后每个怪物
          回合沿门与既有 links（楼梯）扩散一圈；扩张完掷 1 骰，掷出 2 就
          再扩一圈，直到不是 2。
        · 转化（p109）：任何人进入/身处有 Blob 的房间（含叛徒）立刻变成
          Blobperson——弃掉所有物品与预兆、速度 2、不能攻击/被攻击/抽牌/
          用神秘电梯/发现新房间（新引擎钩子 can_discover_rooms），为叛徒
          而战。Blobperson 所占房间在怪物回合开始时种下新 Blob
          （flags["blob_seeded"]），与主体门连通后才并入并从那里扩张。
        · 英雄流程（p38，全部知识 3+，每步每回合一次）：
          ① 检查弱点：在与 Blob 房间门相连的邻室检定，累计成功玩家数次 →
             弱点找到（weakness_found）；
          ② 搜配料：在 11 间配料房检定，成功得 1 份配料（按英雄分开计数），
             该房不可再搜；
          ③ 投掷：在与 Blob 房间门相连的邻室用 1 格移动投出自己身上的
             1 份配料；投满玩家数份 → Blob 销毁，英雄胜。
        · 时钟（p109）：扩张挂在"怪物回合开始"——叛徒 alive 时为其回合
          结束，出局后由本轮最后一名存活玩家代推（惯例；老坑 17 号吸收者）。

    已知简化：
        · 原文"Blob 用尽所有移动方式（含煤导槽/画廊/坍塌房，且这三类
          进出要多花一步）"——本仓库这三间房没有 links 数据，煤导槽是
          房间效果而非链接，故 Blob 只按门与楼梯链接扩散，慢速规则未表达。
        · 配料房按本仓库模板共 11 间：无独立 Storeroom（larder 兼任），
          保险库不建模"打开"状态。
        · Blobperson 的 bot 行为：速度 2 移动，不攻击不行动（为叛徒效力
          的具体策略未建模——它已无事可做）。
        · 弱点/配料投掷的每房理智标记只落在 flags（searched_rooms），
          不生成实体令牌（无 gameplay 作用，纯标记）。
    """

    mode = "blob_weakness"
    bot_goal_exclusive = True

    def progress_summary(self, engine: Any, viewer: Any) -> list[str]:
        flags = engine._haunt_flags()
        rows = [f"Blob 已吞没 {len(flags.get('blob_rooms', []))} 间房间"]
        rows.append("弱点：已找到" if flags.get("weakness_found") else "弱点：未找到")
        bp = len(flags.get("blobperson_ids", []))
        if bp:
            rows.append(f"已被同化 {bp} 人")
        return rows

    INGREDIENT_ROOMS = (
        "attic", "conservatory", "furnace_room", "garden", "library",
        "research_laboratory", "junk_room", "kitchen", "larder", "vault",
        "wine_cellar",
    )

    # ------------------------------------------------------------- setup
    def setup(self, engine: Any, haunt: Any, room_key: str) -> None:
        flags = engine._haunt_flags()
        flags.setdefault("weakness_found", False)
        flags.setdefault("blob_rooms", [])
        flags.setdefault("blob_seeded", [])
        flags.setdefault("blob_grew_once", False)
        flags.setdefault("blobperson_ids", [])
        flags.setdefault("ingredients", {})
        flags.setdefault("searched_rooms", [])
        # p38/p109：持水晶球者弃掉它，Blob 从水晶球所在房间开始生长
        origin = ""
        holder = next(
            (p for p in engine.state.players if "omen_crystal_ball" in p.items and not p.dead),
            None,
        )
        if holder is not None:
            engine._discard_card_from_player(holder, "omen_crystal_ball", return_to_room=False)
            origin = holder.room_key
            engine._log(f"{holder.name} 手中的水晶球迸裂——Blob 从{engine.state.board[origin].name}开始涌动。")
        else:
            revealer = next(
                (p for p in engine.state.players if p.id == engine.state.haunt_revealer_id),
                None,
            )
            if revealer is not None and not revealer.dead:
                origin = revealer.room_key
            engine._log("水晶球不知去向——Blob 从叛徒身边开始涌动。")
        flags["blob_origin"] = origin

    # ----------------------------------------------------------- 状态查询
    def _is_blobperson(self, engine: Any, player: Any) -> bool:
        return str(player.id) in {str(i) for i in engine._haunt_flags().get("blobperson_ids", [])}

    def _is_blob_room(self, engine: Any, key: str) -> bool:
        flags = engine._haunt_flags()
        return key in flags.get("blob_rooms", []) or key in flags.get("blob_seeded", [])

    def _blob_adjacent(self, engine: Any, player: Any) -> bool:
        """p38：与 Blob 房间门相连的邻室。"""
        return any(
            self._is_blob_room(engine, nxt)
            for nxt in engine._door_neighbors(player.room_key)
            if nxt != player.room_key
        )

    def _needed(self, engine: Any) -> int:
        return len(engine.state.players)  # p38/p109：均按玩家数计

    # ------------------------------------------------- Blobperson 限制
    def on_turn_start(self, engine: Any, player: Any) -> None:
        if not player.dead and self._is_blobperson(engine, player):
            player.steps_remaining = 2  # p109：Blobperson Speed 2

    def attack_allowed(self, engine: Any, attacker: Any, target: Any) -> bool:
        if self._is_blobperson(engine, attacker) or self._is_blobperson(engine, target):
            return False  # p109：Blobperson 不能攻击、也不能被攻击
        return super().attack_allowed(engine, attacker, target)

    def suppress_room_draw(self, engine: Any, player: Any, room: Any) -> bool:
        return self._is_blobperson(engine, player)  # p109：Blobperson 不能抽牌

    def can_discover_rooms(self, engine: Any, player: Any) -> bool:
        return not self._is_blobperson(engine, player)  # p109：不能发现房间

    def mystic_elevator_blocked(self, engine: Any, player: Any) -> bool:
        return self._is_blobperson(engine, player)  # p109：不能用神秘电梯

    # --------------------------------------------------------- 扩张时钟
    def on_turn_end(self, engine: Any, player: Any) -> None:
        traitor = next((p for p in engine.state.players if p.role == "traitor"), None)
        if traitor is not None and not traitor.dead:
            if player.id != traitor.id:
                return
        elif not _is_last_in_round(engine, player):
            return
        # p109：怪物回合开始——Blobperson 播种 → Blob 扩张 → 掷 2 追加
        self._seed_blobperson_rooms(engine)
        self._grow_blob(engine)
        guard = 0
        while engine.roll_dice(1, "Blob 扩张检定") == 2 and guard < 24:
            self._grow_blob(engine)
            guard += 1
        self._convert_in_blob(engine)
        engine.check_victory()

    def _blob_neighbors(self, engine: Any, key: str) -> set[str]:
        """Blob 扩散目标：门邻房 + 楼梯/特殊链接（慢速房间无链接数据，见简化）。"""
        room = engine.state.board.get(key)
        targets: set[str] = set()
        if room is None:
            return targets
        for nxt in engine._door_neighbors(key):
            if nxt != key and not engine._is_collapsed(nxt):
                targets.add(nxt)
        for target in room.links.values():
            tk = engine._link_target_key(target)
            if tk and tk != key and not engine._is_collapsed(tk):
                targets.add(tk)
        return targets

    def _grow_blob(self, engine: Any) -> None:
        flags = engine._haunt_flags()
        blob = set(flags.get("blob_rooms", []))
        if not flags.get("blob_grew_once"):
            # p109：第一个怪物回合吞没起源房 + 门邻房
            origin = flags.get("blob_origin")
            if origin and origin in engine.state.board:
                blob.add(origin)
            grew: set[str] = set()
            for key in sorted(blob):
                grew |= self._blob_neighbors(engine, key)
            blob |= grew
            flags["blob_rooms"] = sorted(blob)
            flags["blob_grew_once"] = True
            engine._log(f"血肉骤然膨胀——Blob 吞没了 {len(blob)} 个房间！")
            return
        grew = set()
        for key in sorted(blob):
            grew |= self._blob_neighbors(engine, key)
        grew -= blob
        flags["blob_rooms"] = sorted(blob | grew)
        if grew:
            engine._log(f"Blob 蔓延进了 {len(grew)} 个新房间。")

    def _seed_blobperson_rooms(self, engine: Any) -> None:
        """p109：怪物回合开始，Blobperson 所占房间种下新 Blob；与主体门连通
        后并入主 Blob 并从那里扩张。"""
        flags = engine._haunt_flags()
        bp_ids = {str(i) for i in flags.get("blobperson_ids", [])}
        seeded = set(flags.get("blob_seeded", []))
        for person in engine.state.players:
            if person.dead or str(person.id) not in bp_ids:
                continue
            key = person.room_key
            if key not in flags["blob_rooms"] and key not in seeded:
                seeded.add(key)
                engine._log(f"{person.name} 脚下的房间也泛起了绿色的肉浪。")
        connected = set(flags["blob_rooms"])
        promoted = {
            k for k in seeded
            if any(n in connected for n in engine._door_neighbors(k))
        }
        for k in promoted:
            seeded.discard(k)
            flags["blob_rooms"].append(k)
            engine._log("种下的 Blob 与主体连成了一片。")
        flags["blob_seeded"] = sorted(seeded)

    def _convert_in_blob(self, engine: Any) -> None:
        for person in engine.state.players:
            if person.dead:
                continue
            if self._is_blob_room(engine, person.room_key):
                self._convert(engine, person)

    def _convert(self, engine: Any, player: Any) -> None:
        flags = engine._haunt_flags()
        bp = {str(i) for i in flags.get("blobperson_ids", [])}
        if str(player.id) in bp or player.dead:
            return
        bp.add(str(player.id))
        flags["blobperson_ids"] = sorted(bp)
        # p109：立刻弃掉所有物品与预兆
        for card_id in list(player.items):
            engine._discard_card_from_player(player, card_id, return_to_room=False)
        player.movement_stopped = True
        engine._log(f"{player.name} 被融进了 Blob——他变成了 Blobperson，转而为叛徒效力！")
        engine.check_victory()

    def on_enter_room(self, engine: Any, player: Any, room: Any) -> None:
        # p109：任何人在有 Blob 的房间里立刻变成 Blobperson
        if self._is_blob_room(engine, room.key):
            self._convert(engine, player)

    # ------------------------------------------------------------- 行动
    def available_actions(self, engine: Any, player: Any) -> list[Any]:
        if self._is_blobperson(engine, player):
            return []
        actions = super().available_actions(engine, player)
        if not actions:
            return actions
        flags = engine._haunt_flags()
        blob_adjacent = self._blob_adjacent(engine, player)
        ingredients = int(flags.get("ingredients", {}).get(str(player.id), 0))
        searched = set(flags.get("searched_rooms", []))
        result = []
        for action in actions:
            if action.id == "examine_blob" and not blob_adjacent:
                continue  # 必须站在与 Blob 门相连的邻室（p38）
            if action.id == "search_ingredient" and player.room_key in searched:
                continue  # p38：该房已放过理智标记，不可再搜
            if action.id == "throw_ingredient" and (not blob_adjacent or ingredients <= 0):
                continue  # 必须邻室且身上有配料
            result.append(action)
        return result

    def perform_action(self, engine: Any, player: Any, action_id: str, data: dict) -> bool:
        if action_id == "examine_blob":
            return self._examine(engine, player)
        if action_id == "search_ingredient":
            return self._search(engine, player)
        if action_id == "throw_ingredient":
            return self._throw(engine, player)
        return super().perform_action(engine, player, action_id, data)

    def _examine(self, engine: Any, player: Any) -> bool:
        if not self._blob_adjacent(engine, player):
            return False
        if not engine._resolve_check(player, "knowledge", 3, "检查 Blob"):
            engine._log(f"{player.name} 盯着那团翻涌的血肉，什么也没看出来。")
            return True
        value = engine._advance_haunt_track("knowledge_rolls", 1)
        needed = self._needed(engine)
        if value >= needed:
            engine._haunt_flags()["weakness_found"] = True
            engine._set_haunt_track_value("knowledge_rolls", 0)
            engine._log(f"弱点找到了！{player.name} 的最后一次次检定揭示了 Blob 的死穴（p38）。")
        else:
            engine._log(f"{player.name} 记下了 Blob 的一处特征（{value}/{needed}）。")
        return True

    def _search(self, engine: Any, player: Any) -> bool:
        flags = engine._haunt_flags()
        room = engine.current_room(player)
        if room.template_id not in self.INGREDIENT_ROOMS or room.key in flags.get("searched_rooms", []):
            return False
        if not engine._resolve_check(player, "knowledge", 3, "搜寻配料"):
            engine._log(f"{player.name} 在{room.name}翻遍了架子，没找到能用的东西。")
            return True
        ingredients = flags.setdefault("ingredients", {})
        key = str(player.id)
        ingredients[key] = int(ingredients.get(key, 0)) + 1
        flags.setdefault("searched_rooms", []).append(room.key)
        engine._log(f"{player.name} 在{room.name}找到了一份配料（身上现有 {ingredients[key]} 份）。该房已放过理智标记，不能再搜。")
        return True

    def _throw(self, engine: Any, player: Any) -> bool:
        flags = engine._haunt_flags()
        ingredients = flags.setdefault("ingredients", {})
        key = str(player.id)
        if not self._blob_adjacent(engine, player) or int(ingredients.get(key, 0)) <= 0:
            return False
        # p38：投掷用 1 格移动
        if player.steps_remaining <= 0 and player.moved_this_turn:
            engine._log(f"{player.name} 已没有剩余移动力来投掷。")
            return True
        player.steps_remaining = max(0, player.steps_remaining - 1)
        player.moved_this_turn = True
        ingredients[key] = int(ingredients.get(key, 0)) - 1
        value = engine._advance_haunt_track("blob_ingredients", 1)
        engine._log(f"{player.name} 把一份配料掷进了 Blob（{value}/{self._needed(engine)}）。")
        engine.check_victory()
        return True

    # ------------------------------------------------------------ bot
    # bot 的自保模型（p109「下个怪物回合会吞哪些房间」）：
    #   · Blob 核心：已落地的 Blob 房间；未落地时只有起源房——第一个怪物回合
    #     会连它的门邻/链接邻域一起吞掉。
    #   · 险区（danger）：核心 + 一圈邻域。怪物回合后活下来 = 本回合结束时
    #     不在险区里。贴边检定/投掷必须进险区，所以节奏是"进、做、退"。
    def _blob_all(self, engine: Any) -> set[str]:
        flags = engine._haunt_flags()
        return set(flags.get("blob_rooms", [])) | set(flags.get("blob_seeded", []))

    def _blob_core(self, engine: Any) -> set[str]:
        blob = self._blob_all(engine)
        if blob:
            return blob
        origin = engine._haunt_flags().get("blob_origin")
        if origin and origin in engine.state.board:
            return {origin}
        return set()

    def _neighbors_of(self, engine: Any, keys: set[str], doors_only: bool = False) -> set[str]:
        """keys 的邻域（默认门 + 楼梯链接，与扩张同源；doors_only 只算门）。

        与 `_grow_blob` 用同一套扩张规则，危险预判才和实际吞并对得上。
        """
        out: set[str] = set()
        for key in keys:
            if doors_only:
                out |= {n for n in engine._door_neighbors(key) if n != key}
            else:
                out |= self._blob_neighbors(engine, key)
        return {
            k
            for k in out
            if k in engine.state.board and k not in keys and not engine._is_collapsed(k)
        }

    def _danger_zone(self, engine: Any) -> set[str]:
        """下个怪物回合会被吞掉的房间（核心 + 一圈邻域）。"""
        core = self._blob_core(engine)
        if not core:
            return set()
        return core | self._neighbors_of(engine, core)

    def _safe_keys(self, engine: Any) -> list[str]:
        """险区之外的安全房（在这里结束回合不会被吞）。"""
        danger = self._danger_zone(engine)
        return [
            key
            for key in sorted(engine.state.board)
            if key not in danger and not engine._is_collapsed(key)
        ]

    def bot_blocked_rooms(self, engine: Any, player: Any) -> set[str]:
        """寻路禁区：Blob 房间（bot_ai 不走进也不路过——进去＝立刻同化）。"""
        if player.dead or self._is_blobperson(engine, player):
            return set()
        return self._blob_all(engine)

    def bot_hazard_rooms(self, engine: Any, player: Any) -> set[str]:
        """危险房：扩张圈（本回合结束留在里面＝下个怪物回合被吞）。"""
        if player.dead or self._is_blobperson(engine, player):
            return set()
        return self._danger_zone(engine)

    def bot_leave_after_action(self, engine: Any, player: Any) -> bool:
        """贴边做完本回合的一步后必须挪窝（扩张圈里过夜＝被同化）。"""
        if player.dead or self._is_blobperson(engine, player):
            return False
        return bool(engine._haunt_action_used(player))

    def bot_stay_in_room(self, engine: Any, player: Any) -> bool:
        """本回合的剧本行动已经做完、且退到了险区之外：原地结束回合。"""
        if player.dead or self._is_blobperson(engine, player):
            return False
        if not engine._haunt_action_used(player):
            return False
        return player.room_key not in self._danger_zone(engine)

    def bot_action_blocked(self, engine: Any, player: Any, action_id: str) -> bool:
        """给 bot 判寻路目标/可做行动用（p38 顺序：先找弱点，再搜配料，最后投掷）。

        · 弱点没找到前，配料房不是目的地（引擎同样要求 weakness_found，否则
          bot 会提前跑去配料房干站，把贴边检定的回合浪费掉）。
        · Blobperson 没有任何剧本行动。
        """
        if self._is_blobperson(engine, player):
            return True
        if action_id == "search_ingredient" and not engine._haunt_flags().get("weakness_found"):
            return True
        return False

    def _has_work_here(self, engine: Any, player: Any) -> bool:
        """这个房间此刻还有没有值得做的剧本一步（只看位置与旗标，不掷骰）。

        不能在这里调 `available_actions`：试玩探针靠代理统计该接口的
        "行动出现/使用"，多调一次就把 offered 计数虚增，报出假的"行动空转"
        （seed151/6p 实测 warned `行动空转:search_ingredient`，实际是钩子的
        计数噪声）。这里按 p38 的三步流程手写等价判断。
        """
        flags = engine._haunt_flags()
        if player.room_key in self._blob_all(engine):
            return False
        adjacent = self._blob_adjacent(engine, player)
        if not flags.get("weakness_found"):
            return adjacent  # ① 检查弱点
        if int(flags.get("ingredients", {}).get(str(player.id), 0)) > 0:
            return adjacent  # ③ 贴边投掷
        room = engine.current_room(player)
        return (  # ② 搜配料
            room.template_id in self.INGREDIENT_ROOMS
            and room.key not in set(flags.get("searched_rooms", []))
        )

    def bot_goal_rooms(self, engine: Any, player: Any) -> list[str]:
        """英雄 bot 的推进目标（含"贴边看一眼就退开"的自保节奏）。

        旧实现只给扩张圈，实测两个致命问题（seed101/3p 两回合团灭、未完成）：
        · 英雄在扩张圈里做完检定后原地过夜（`_pending_haunt_action_here`），
          下一个怪物回合 Blob 正好扩进这间房 → 同化；
        · 寻路把 Blob 房间当普通通路穿过去（入口大厅→地下室平台）→ 走进即同化。
        现在：做完一步 / 身处险区却无事可做 → 退回险区外；寻路禁区与危险房
        分别由 `bot_blocked_rooms` / `bot_hazard_rooms` 交给 bot_ai。
        """
        if player.dead or self._is_blobperson(engine, player):
            return []
        flags = engine._haunt_flags()
        danger = self._danger_zone(engine)
        retreat = ["__room__" + key for key in self._safe_keys(engine)]
        if player.role == "traitor":
            # p109：叛徒也会被同化（原文"包括你自己"）。站在险区先退开；
            # 其余交给通用追击逻辑——Blob 自会替他料理英雄。
            return retreat if player.room_key in danger else []
        if not self._blob_all(engine):
            # 第一怪物回合之前：起源房与邻室马上要变 Blob（p38：站那儿的
            # 人赶紧走）。先离开；其余人挪到将来的检定圈上等它落地。
            if not danger:
                return []
            if player.room_key in danger:
                return retreat
            return [
                "__room__" + key
                for key in sorted(self._neighbors_of(engine, danger, doors_only=True))
            ]
        acted = engine._haunt_action_used(player)
        idle_in_danger = player.room_key in danger and not self._has_work_here(engine, player)
        if acted or idle_in_danger:
            return retreat  # 本回合该做的做完了：退回险区外过夜
        ring = ["__room__" + key for key in sorted(self._neighbors_of(engine, self._blob_all(engine), doors_only=True))]
        if not flags.get("weakness_found"):
            return ring  # 弱点阶段：贴着 Blob 检定
        if int(flags.get("ingredients", {}).get(str(player.id), 0)) > 0:
            return ring  # 有配料：贴边投掷
        blob = self._blob_all(engine)
        searched = set(flags.get("searched_rooms", []))
        return [
            "__room__" + key
            for key, room in sorted(engine.state.board.items())
            if room.template_id in self.INGREDIENT_ROOMS
            and key not in searched
            and key not in blob
        ]

    # ------------------------------------------------------------- 胜负
    def check_victory(self, engine: Any) -> bool:
        flags = engine._haunt_flags()
        # p38 英雄胜：投满玩家数份配料 → Blob 销毁
        if engine._haunt_track_value("blob_ingredients") >= self._needed(engine):
            engine._set_winner("heroes", "烧杯落进翻涌的血肉——Blob 抽搐着把自己蒸发殆尽。")
            return True
        # p109 叛徒胜：所有英雄死亡或变成 Blobperson
        bp = {str(i) for i in flags.get("blobperson_ids", [])}
        heroes = [p for p in engine.state.players if p.role == "hero"]
        if heroes and all(p.dead or str(p.id) in bp for p in heroes):
            engine._set_winner("traitor", "最后的英雄也融进了那团不断扩张的血肉。")
            return True
        return True  # 吸收引擎「叛徒死亡→英雄胜」兜底：叛徒死后 Blob 照常扩张
