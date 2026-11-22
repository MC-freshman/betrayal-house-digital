# A-33 对局美术渲染 —— 只读验收矩阵

- **文档性质**：只读设计。本文不修改 `ui.py` / `game_art.py` / `ui_asset_binding.py` / engine / `assets/` / `photos/`，不运行会写文件的脚本，不签发 claim。
- **适用**：桌面端 `source/desktop/game/`，「P 表美术接入对局 UI」的独立验收轮次。
- **配套脚本**：`source/desktop/game/qa/verify_game_art.py`（只读，机读 JSON 打到 stdout，不落盘）。
- **上游**：`.codebuddy/wfat/art_acceptance_criteria.md`（A-33 六条判据正文）、`art_architecture.json`（组件与接口）、`art_boundary_audit.json`（24 个渲染面 / 9 类不可达 / RK-01…RK-10）。
- **本文与上游的关系**：判据编号与阈值口径以本文为准；本文新增的裁决一律带 `K-xx` 编号，**不得**被当作对 `art_acceptance_criteria.md` 的静默改写。

一句话边界：**A-33 只断言「已渲染且非占位」**。丑但合格、被正确渲染的图判 PASS；这是刻意的。

---

## 1. 编号、门禁与三态

| 字段 | 值 |
| --- | --- |
| id | `A-33` |
| 标题 | 对局美术渲染 |
| 门禁 | `G5`（UI 与三档 DPI） |
| 优先级 | `P0` |
| 依赖产物 | `qa/game_art_probe.json` + `qa/screenshots/art_*.png` |
| 三态 | PASS / FAIL / NOT_RUN（+ `CONFLICT` 仅用于口径冲突） |
| 判据规模 | **6 条主判据（J1–J6）+ 1 条证据归属（J0）+ 3 条静态检查（S1–S3）= 10 项检查 / 46 条细分断言** |

**判定后果**

- `FAIL` → `G5 = FAIL`，`completion_claim@execution = not-attested`；报告不得写 `verdict=PASS`。
- `NOT_RUN` → `G5 = NOT_RUN`，claim 上限 `partial`；**不得**折算 PASS，也不进通过率分母。
- `CONFLICT` → 同一事项存在两个未合并口径且证据只满足其中一个；按 `partial` 处理，需书面裁决。
- `PASS` → 不抵消任何其他项；A-33 不替代 A-19/20/21/22/32。

**断言计数（脚本以 `ASSERTION_COUNT` 自检）**

| 检查 | J0 | J1 | J2 | J3 | J4 | J5 | J6 | S1 | S2 | S3 | 合计 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 断言条数 | 4 | 5 | 6 | 7 | 6 | 6 | 5 | 2 | 3 | 2 | **46** |

---

## 2. 证据链与执行顺序

```
ui.py(接线) → qa/game_art_probe.py（独立进程，真实 Tk）
             → qa/game_art_probe.json + qa/screenshots/art_*.png
             → qa/verify_game_art.py（本脚本，只读复算）
```

1. **探针必须先跑完**，验收进程只读其产物；验收期间跑探针一律按「并发写入」处理（`readonly=false`，PASS 全部降级 NOT_RUN）。
2. 探针只允许写 `qa/game_art_probe.json` 与 `qa/screenshots/art_*.png`；**不得**写 `assets/`、`photos/`、`saves/`。
3. 截图必须 `PIL.ImageGrab` 抓真实窗口；`shot_size` 与 PNG IHDR 必须一致（脚本逐张核对，不一致判 FAIL，防合成）。
4. 三次连续运行应给出相同 `verdict` 与相同 `counters`（`redraw_ms`、缓存命中数允许抖动）。
5. 验收脚本自身对 4 个输入（`ui.py` / `ui_asset_binding.py` / `p_table.json` / `asset_mapping.json`）做 sha256 快照；运行期变化即把原 PASS 降为 NOT_RUN。

---

## 3. 判据矩阵

> 术语：**账本** = `qa/game_art_probe.json` 的 `ledger[]`；**占位** = `placeholder == true`，或 `rel_path` 落在 `assets/placeholders/`、`assets_ww/` 下。
> 尺寸一律按 `base × (dpi/96)` 复算，容差 ±2 px；`dpi` 取 `probe.environment.system_dpi`（或 `scale × 96`），缺失即 NOT_RUN。

### 3.0 J0 证据归属（前置闸门，4 条）

| # | 断言 | 机读字段 | 失败语义 |
| --- | --- | --- | --- |
| 1 | 探针文件存在且 JSON 可解析 | `qa/game_art_probe.json` | 缺失 → NOT_RUN；损坏 → FAIL |
| 2 | `mode == "real-tk"` | `probe.mode` | `headless`/缺省 → NOT_RUN |
| 3 | 4 个输入哈希与当前产物逐一相等 | `inputs.ui_py_sha256` / `ui_asset_binding_sha256` / `p_table_sha256` / `asset_mapping_sha256` | 缺失或不符 → NOT_RUN（证据早于产物） |
| 4 | `environment.system_dpi`（或 `scale`）可解析 | `probe.environment` | 缺失 → NOT_RUN（无法独立复算尺寸） |

J0 未通过时，**J1–J6 一律 NOT_RUN**，不冒充 PASS、不做"部分通过"折算。

### 3.1 J1 棋盘房间贴图（阻断，5 条）

| # | 断言 | 机读字段 |
| --- | --- | --- |
| 1 | `turns_played >= 6` 且 `rooms_placed >= 8`（样本下限，防 0/0 空洞通过） | `board.turns_played` / `board.rooms_placed` |
| 2 | **`canvas_image_items >= rooms_placed`** | `board.canvas_image_items`（`canvas.find_all()` 中 `type(item)=="image"` 的计数） |
| 3 | `rooms_with_image == rooms_placed`（每间房都能在账本找到 `surface=="board"` 且 `placeholder==false` 的记录） | `board.rooms_with_image` |
| 4 | 每条 `surface=="board"` 记录满足 `asset_type=="room"` 且 `key` 以 `room:` 开头 | `ledger[].asset_type` / `ledger[].key` |
| 5 | 账本 `board` 去重 key 数 == `rooms_with_image`，且 `board` 记录 `placeholder` 全为 false | `ledger[]` |

失败示例（写进 detail）：`rooms_with_image=9 != rooms_placed=10；board 账本去重 key=10 != rooms_with_image=9（疑似自报虚高）`。

### 3.2 J2 抽卡弹窗卡面（阻断，6 条）

| # | 断言 | 机读字段 |
| --- | --- | --- |
| 1 | `cards` ≥ 3 条，`kind` 覆盖 `{omen,item,event}`，且每条 `popup_opened == true` | `cards[].kind` / `popup_opened` |
| 2 | `photo_size == (round(240×dpi/96), round(336×dpi/96))` ±2 | `cards[].photo_size` |
| 3 | 探针自报 `expected_size` 与脚本独立复算一致（±1） | `cards[].expected_size` |
| 4 | `abs(w/h - 5/7) / (5/7) <= 0.02` | `cards[].photo_size` |
| 5 | 每张卡截图存在、是真 PNG、`png_ihdr == shot_size`、截图宽 ≥ 卡面宽 | `cards[].screenshot` / `shot_size` |
| 6 | 每条 `placeholder == false`，且 `record_id` 落在 P 表卡牌记录内 | `cards[].record_id` |

- 缺任一 kind、或 `popup_opened==false`、或**缺截图** → NOT_RUN（不得 PASS）；但只要出现尺寸/比例/占位违规，**FAIL 优先**。
- 断言 3 是防「探针自报期望值给自己放水」：自报值与公式不符即 FAIL，不再看该条尺寸结论。

### 3.3 J3 全账本零占位（阻断，唯一硬兜底，7 条）

| # | 断言 | 机读字段 |
| --- | --- | --- |
| 1 | `len(ledger) >= 20`（< 20 → NOT_RUN）；`len(ledger) <= 512` | `ledger` |
| 2 | **`counters.placeholder_hits == 0`** | `counters.placeholder_hits` |
| 3 | 账本 `placeholder == true` 计数 == 0，且与 `counters` 交叉一致 | `ledger[].placeholder` |
| 4 | 无 `rel_path` 含 `assets/placeholders/` 或 `assets_ww/` | `ledger[].rel_path` |
| 5 | 每条记录必填字段齐备（`seq/surface/key/asset_type/record_id/rel_path/placeholder`），`surface` ∈ 六类 | `ledger[]` |
| 6 | 每条 `record_id` 存在于 P 表，且该行 `availability=="usable"`、`runtime_status=="ok"` | `assets/p_table.json` |
| 7 | `counters.loader_errors == 0` 且 `counters.resolve_failures == 0` | `counters` |

> 为什么单列：`load_asset_photo` 在文件缺失时返回**占位图 PhotoImage 而非 None**（`ui_asset_binding.py:236-260`），"没报错"不等于"用了真图"。J3 是"无一条渲染记录落在占位图上"的正式口径，也是 A-33 唯一的全账本兜底。

### 3.4 J4 玩家头像（阻断，6 条）

| # | 断言 | 机读字段 |
| --- | --- | --- |
| 1 | `players.count >= 3`（一局最少 3 人） | `players.count` |
| 2 | **面板/头像记录（`surface ∈ {panel, portrait}`）的去重 key 数 == `players.count`** | `ledger[].surface` / `key` |
| 3 | `players.records` 覆盖全部玩家，且每人有 `character_id` / `record_id` / `photo_size` | `players.records[]` |
| 4 | 头像 `record_id` 全落在 P 表 12 位 `character` 记录内，且互不重复 | `players.records[]` / `ledger[]` |
| 5 | 面板档 = `64×64 × dpi/96` ±2；详情档 = `160×160 × dpi/96` ±2 | `ledger[].actual` |
| 6 | 全部 `placeholder == false` | `ledger[]` / `players.records[]` |

裁决见 `K-03`：`panel` 与 `portrait` 视为同一"头像面"的两种标记，合并计数，避免因实现选词差异把正确实现判死。

### 3.5 J5 房间 tooltip / 详情缩略图（阻断，6 条）

| # | 断言 | 机读字段 |
| --- | --- | --- |
| 1 | `room_tooltip.hovered` 去重后 ≥ 3 个不同房间；`room_detail.opened >= 1` | `room_tooltip.hovered` / `room_detail.opened` |
| 2 | **tooltip 图元 = `112×112 × dpi/96` ±2**（命中旧口径 `96×96` → CONFLICT） | `ledger[].actual`（`surface=="room_tooltip"`） |
| 3 | **详情图元 = `160×160 × dpi/96` ±2**（命中旧口径 `192×192` → CONFLICT） | `ledger[].actual`（`surface=="room_detail"`） |
| 4 | 两段合计非占位记录 ≥ 4 | `ledger[]` |
| 5 | `room_tooltip.photo_refs_after_close == 0`（关闭后不泄漏 PhotoImage 引用） | `room_tooltip.photo_refs_after_close` |
| 6 | `art_room_tooltip.png` / `art_room_detail.png` 存在、真 PNG、IHDR == `shot_size` | `room_tooltip.screenshot` / `room_detail.screenshot` / `probe.screenshots` |

- **缺截图 → NOT_RUN**（不得只凭账本折算 PASS）；尺寸/占位违规 → FAIL 优先。
- 尺寸口径冲突见 `K-01`：本轮取 **112 / 160**（边界审计 `mapping_table` 的 S-08 / S-09 实际接线尺寸），`art_acceptance_criteria.md §J5` 的 96 / 192 属旧口径；命中旧口径不判 FAIL 也不判 PASS，判 CONFLICT 要求书面裁决。

### 3.6 J6 取图键可反查（阻断，5 条）

| # | 断言 | 机读字段 |
| --- | --- | --- |
| 1 | 账本每条 `key` 经 `AssetRegistry.resolve(key)` 非 None | `ledger[].key` + `asset_registry.AssetRegistry` |
| 2 | `ref.record_id == ledger[].record_id`（键↔记录双向一致） | 同上 |
| 3 | `counters.resolve_failures == 0` | `counters` |
| 4 | `counters.name_ambiguous == 0`（>0 表示有卡退化成纯文字） | `counters` |
| 5 | `unreachable` 升序去重后**完全等于** `["storeroom"]` | `probe.unreachable` |

> J6-5 是「允许项」而非「豁免项」：`storeroom` 是 P 表有、`content.build_catalog().room_templates` 无的唯一差集。集合变化必须同步改判据并留 diff，不得默默放行。

---

## 4. 静态检查（不依赖探针，7 条）

| 检查 | # | 断言 | 缺失/不达标 |
| --- | --- | --- | --- |
| **S1** `ui.py` 接线 | 1 | `create_image` 调用点（AST `Call` 节点，不含注释/字符串）≥ 4 | 0 处 → NOT_RUN（未接线）；1–3 处 → FAIL |
| | 2 | 每个调用点行号可定位并列入 evidence | 不可定位 → FAIL |
| **S2** `game_art.py` | 1 | 文件存在且可 `ast.parse` | 不存在 → NOT_RUN；不可解析 → FAIL |
| | 2 | 三个键前缀 `room:` / `card:` / `character:` 均出现在函数体内（f-string、`+` 拼接、`%` 格式化均可） | 缺任一 → FAIL |
| | 3 | 每个前缀都能定位到具体函数名（如 `room_key`），并报出 `ledger()` 是否存在 | 仅信息，不单独阻断 |
| **S3** 缓存容量 | 1 | 能定位模块级字面量 `DEFAULT_CACHE_CAPACITY` | 找不到 → FAIL |
| | 2 | `DEFAULT_CACHE_CAPACITY >= 128` | <128 → FAIL（RK-05：64 只够一个尺寸档） |

**为什么 S1 的 0 处判 NOT_RUN 而不是 FAIL**：断言对象尚未存在（接线未开始）≠ 已交付但不达标。已交付但只接了 1–3 处 → FAIL。此规则见 `K-06`，与「缺证据只允许 FAIL / NOT_RUN」一致。

---

## 5. 汇总判定

```
problems（违规）非空                  → FAIL
conflicts（口径冲突）非空且无违规      → CONFLICT
shortfalls（证据缺失/样本不足）非空    → NOT_RUN
否则                                  → PASS
```

- 脚本无 `skip` 分支；`--probe` 指向不存在的文件只会得到 NOT_RUN。
- 验收期间输入被改写 → 全部原 PASS 降为 NOT_RUN，`readonly=false` 写进 payload。
- 退出码：`0 PASS` / `1 FAIL` / `3 INCOMPLETE（仅 NOT_RUN、CONFLICT）` / `2 参数或内部异常`。

---

## 6. 明确排除项：U-01…U-09（9 条，不做断言）

这 9 类渲染面**没有资源位或没有可达键**，A-33 对其**不做任何断言**，也不把它们计入失败。排除不等于豁免实现：每条都要求「显式登记」而非隐藏（J6-5 是唯一被机读的登记项）。

| ID | 渲染面 | 排除理由 | 判别证据 | A-33 是否断言 |
| --- | --- | --- | --- | --- |
| U-01 | S-03 探索落点预览 | 房间尚未翻牌，state 无 `template_id`；P 表无牌背键 | `resolve('card:back:omen') = None` | 否 |
| U-02 | S-05 怪物标记 | P 表无 `monster` 资源类型 | `resolve('monster:mummy') = None` | 否 |
| U-03 | S-18 剧本揭示/手册 | `Haunt` 无插画字段；`haunts_zh` 无图片引用；无 `haunt:*` 键 | `resolve('haunt:1') = None` | 否 |
| U-04 | S-19 结算画面 | 绘制层不存在；无 `ending:*` 键 | `resolve('ending:heroes') = None` | 否 |
| U-05 | S-21 局势面板牌堆卡背 | 无 `card:back:*` 资源位 | `resolve('card:back:omen') = None` | 否 |
| U-06 | **S-11 多选舍弹窗**（原含 S-10） | `choose_from_list` 只收 `list[str]`，无 `card_id` | `ui.py` 三方法签名无 card 参数 | 否（S-10 由 J2 承担，见 K-02） |
| U-07 | S-24 骰子 | P 表五类资源无 `dice` | `p_table` 检索 `dice` 命中 0 | 否 |
| U-08 | 反向孤儿 `room:storeroom` | P 表 50 房间 vs catalog 49 模板，有图无模板 | 差集实测 `['room:storeroom']`（P-ROOM-048） | 仅 J6-5 要求"显式登记" |
| U-09 | 合成临时房 `template_id='temp'` | 仅落点可行性模拟，不进 `state.board` | `engine.py:1086` 局部变量 | 否 |

排除项合计 **9 条**，覆盖 **9 个渲染位置**。脚本把这份清单原样写进 `payload.excluded_unmapped`（含理由与证据），便于报告引用与后续变更追踪。

---

## 7. 口径裁决（K-01…K-06）

| 编号 | 冲突/歧义 | 裁决 | 影响 |
| --- | --- | --- | --- |
| **K-01** | J5 尺寸：本文取 112/160（边界审计 `mapping_table` 的 S-08/S-09），`art_acceptance_criteria.md §J5` 写 96/192 | 以 **112/160** 为本轮口径；命中 96/192 判 **CONFLICT**，不判 PASS 也不判 FAIL | J5-2/J5-3；需产品书面确认后把旧文档改齐，脚本删掉 legacy 分支 |
| **K-02** | U-06 把 S-10 抽卡弹窗登记为不可达，但 J2 明确要求卡面 | **U-06 收窄为 S-11**；S-10 不排除，由 J2 承担。若实现选择不改 `DecisionProvider` 协议，J2 自然落 NOT_RUN（缺 `popup_opened`/卡面），不得折算 PASS | 排除项仍为 9 条；J2 的前置风险= RK-10 |
| **K-03** | 账本 `surface` 有 `panel` 与 `portrait` 两种自然写法，判据只写"面板头像" | 二者**合并**为同一头像面计数（去重 key）；尺寸按 64（面板）/ 160（详情）两档分别判 | J4-2/J4-5 |
| **K-04** | 探针自报 `expected_size` 可能被用来"给自己放水" | 脚本按 `240×336×dpi/96` **独立复算**；自报值与公式不符即 FAIL | J2-3；J4/J5 同样只信复算值 |
| **K-05** | `game_art.py` 账本字段与探针账本 schema 不同（见 §8） | 由**探针侧**做字段映射，不改实现；映射缺失导致 J3-5 FAIL 由探针负责 | J1/J3/J4/J5 的字段口径 |
| **K-06** | 「实现未交付」与「已交付不达标」都可能不是 PASS，但含义不同 | 未交付（`game_art.py` 不存在、`create_image` 0 处、探针未跑、缺截图）→ **NOT_RUN**；已交付但违规 → **FAIL**；两文档口径冲突且证据只满足其一 → **CONFLICT** | 全部检查项 |

---

## 8. 接口落差：`game_art.py` 账本 → 探针账本（K-05 明细）

实测当前 `game_art.GameArt._record()` 写出的字段是 `kind / key / size / placeholder / resolved / record_id / path`，而 A-33 探针 schema 要求 `seq / surface / key / asset_type / requested / actual / record_id / rel_path / placeholder`。这不是缺陷，是**两层的职责不同**：`game_art` 只记"取图事实"，`art_probe` 负责"渲染面归属与截图"。

| `game_art` 字段 | 探针字段 | 映射规则 | 缺失后果 |
| --- | --- | --- | --- |
| `kind`（room/card/character） | `asset_type` | `room→room`；`card→card_<kind>`（从 key 第 2 段解析）；`character→character` | J1-4 / J4-4 |
| `kind` | `surface` | 由**调用点**标记：棋盘→`board`、抽卡→`card`、面板→`panel`、头像档→`portrait`、tooltip→`room_tooltip`、详情→`room_detail` | J1-4 / J2 / J4-2 / J5 |
| `size` | `requested` + `actual` | 直接复制；若绑定层等比缩得更小，`actual` 应取 `photo.width()/height()` | J2-2 / J4-5 / J5-2、J5-3 |
| `path`（绝对） | `rel_path` | 去掉项目根前缀，保留 `source/desktop/game/...` | J3-4 |
| `record_id` | `record_id` | 直接复制（未解析时为 `None` → J3-6 FAIL，正确） | J3-6 / J6-2 |
| `placeholder` | `placeholder` | 直接复制 | J1-5 / J3-3 / J4-6 |
| — | `seq` | 探针自增 | J3-5 |
| — | `cache`（可选） | 可留空；不参与任何断言 | 无 |

`counters` 侧：`loader_errors` / `resolve_failures` / `placeholder_hits` 已由 `GameArt._counters` 提供，但 **`name_ambiguous` 只能由探针统计**（它属于「卡名→id 反查退化」的 UI 层事实）；探针不统计 → J6-4 NOT_RUN。

---

## 9. 风险映射（RK-01…RK-10 由谁承担）

| 风险 | 内容 | A-33 处置 | 是否阻断 A-33 |
| --- | --- | --- | --- |
| RK-01 | 改 `ui.py` 会让 `qa/ui_capture.json` 变陈旧，A-19/20/21 直接被 `_fresh_enough` 判 FAIL | A-33 不接这个责任；但 J0-3 用同一套"哈希归属"思路保护自己 | 否（相邻项风险） |
| RK-02 | `ui_capture.json` 的 `app_source_sha256` 与当前 `ui.py` 不一致，门禁只查字段存在 | 记为相邻项缺陷；A-33 不采信 `ui_capture.json` | 否 |
| RK-03 | `ui_capture.py` 依赖 `_art_photo/_art_entries/ART_*` 私有属性 | 明确不测"美术预览页重构"；A-33 不触碰 S-14 | 否 |
| RK-04 | 棋盘每 tile 尺寸档冷加载 0.64–0.77 s | 只把 `board.redraw_ms` 记为**非阻断观测**，不计入 A-23 | 否 |
| RK-05 | LRU 容量 64 只够一个尺寸档 | **S3 静态断言 ≥128** | 是 |
| RK-06 | canvas 不持 Python 引用，淘汰即空白 | J1-2/J1-5（图元数）与 J5-5（关闭后引用 0）间接覆盖；"淘汰→空白"端到端仍不可测（见 §12） | 部分 |
| RK-07 | 文字压美术后对比度不足 | **明确不做断言**；A-22 仍按设计值/预览页口径 | 否（不做） |
| RK-08 | PIL 成 UI 硬依赖；缩放只能回 PIL | 若 Pillow 缺失走 subsample → J2-2 尺寸直接 FAIL；探针须登记 `environment.pillow` | 间接 |
| RK-09 | 缺图只有 3 张通用占位图，50 房会长一样 | **J3 零占位**是兜底：任何一条落到占位即 FAIL | 是 |
| RK-10 | 抽卡面要改 `DecisionProvider` 协议（超出 `ui.py`） | J2 的前置；不改协议则 J2 只能 NOT_RUN，不许 PASS | 是（J2） |

---

## 10. 证据形态

### 10.1 `qa/game_art_probe.json`（探针产出，验收只读）

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `tool` / `generated_at` | 是 | `"qa/game_art_probe.py"` / ISO 时间 |
| `mode` | 是 | 必须 `"real-tk"`；`headless` 一律 NOT_RUN |
| `environment` | 是 | `python` / `tk` / `pillow` / `system_dpi` / `scale` / `platform` |
| `inputs` | 是 | `ui_py_sha256` / `ui_asset_binding_sha256` / `p_table_sha256` / `asset_mapping_sha256` |
| `board` | 是 | `turns_played` / `rooms_placed` / `canvas_image_items` / `rooms_with_image` / `redraw_ms` |
| `cards` | 是 | 3 条：`kind` / `card_id` / `record_id` / `popup_opened` / `photo_size` / `expected_size` / `placeholder` / `screenshot` / `shot_size` |
| `players` | 是 | `count` / `records[]`（`player_id` / `character_id` / `record_id` / `photo_size` / `placeholder`） |
| `room_tooltip` | 是 | `hovered` / `records` / `photo_refs_after_close` / `screenshot` / `shot_size` |
| `room_detail` | 是 | `opened` / `records` / `screenshot` / `shot_size` |
| `ledger` | 是 | ≤512 条，schema 见 10.3 |
| `counters` | 是 | `loader_errors` / `resolve_failures` / `name_ambiguous` / `placeholder_hits` |
| `unreachable` | 是 | 必须 `["storeroom"]` |
| `screenshots` | 是 | 见 10.2 |
| `verdict` | 是 | 探针自判；**不作验收依据**，脚本独立复算 |

### 10.2 截图清单（7 张，`qa/screenshots/`）

| 文件名 | 服务于 | 验收用途 |
| --- | --- | --- |
| `art_board_100.png` | J1 | 棋盘已放置房间的贴图总览（人工复核 + 报告插图） |
| `art_card_omen.png` | J2 | 预兆卡弹窗卡面 |
| `art_card_item.png` | J2 | 物品卡弹窗卡面 |
| `art_card_event.png` | J2 | 事件卡弹窗卡面 |
| `art_player_panel.png` | J4 | 玩家面板头像 |
| `art_room_tooltip.png` | J5-6 | 房间 tooltip 缩略图 |
| `art_room_detail.png` | J5-6 | 房间详情缩略图 |

`art_board_100.png` / `art_player_panel.png` 不参与机读断言（J1、J4 已用账本+计数判定），但必须落盘作为报告证据；**缺失时 J1/J4 仍按账本判，不因缺插图而 NOT_RUN**（与 J2/J5 不同）。

### 10.3 账本抽样（探针必须能产出这三类记录）

```json
{"seq": 1, "surface": "board", "key": "room:entrance_hall", "asset_type": "room",
 "requested": [102, 102], "actual": [102, 102], "record_id": "P-ROOM-004",
 "rel_path": "source/desktop/game/assets/rooms/entrance_hall.png",
 "placeholder": false, "reason": "", "cache": "hit", "at": "2026-11-22T10:00:00"}

{"seq": 41, "surface": "card", "key": "card:omen:omen_bite", "asset_type": "card_omen",
 "requested": [240, 336], "actual": [240, 336], "record_id": "P-OMEN-001",
 "rel_path": "source/desktop/game/assets/cards/omen_bite.png",
 "placeholder": false, "reason": "", "cache": "miss", "at": "2026-11-22T10:00:00"}

{"seq": 55, "surface": "panel", "key": "character:card_4:f1", "asset_type": "character",
 "requested": [64, 64], "actual": [64, 64], "record_id": "P-CHR-007",
 "rel_path": "source/desktop/game/assets/characters/card_4_f1.png",
 "placeholder": false, "reason": "", "cache": "hit", "at": "2026-11-22T10:00:00"}
```

`reason ∈ {"", "unresolved", "file-missing", "decode", "no-registry"}`；`placeholder=true` 只允许在 `file-missing` 时出现。`cache` / `reason` 为观测字段，不作必填断言。

---

## 11. 执行、退出码与基线快照

```powershell
# 机读（默认，stdout 只有 JSON）
python qa/verify_game_art.py
# 人读
python qa/verify_game_art.py --human
# 指定探针 / 指定根目录
python qa/verify_game_art.py --probe path/to/game_art_probe.json --root D:/Game/桌游模拟器/Betrayal at House on the Hill
```

| 退出码 | 含义 |
| --- | --- |
| 0 | PASS（10 项检查全 PASS） |
| 1 | FAIL（存在阻断 FAIL） |
| 3 | INCOMPLETE（仅 NOT_RUN / CONFLICT） |
| 2 | 参数或内部异常 |

### 11.1 当前基线快照（只读复跑，非验收结论）

> 采集时间：**2026-11-21 23:35:04**（`ui_asset_binding.py` mtime）。实现正在并发落地，以下任一输入变化都会让 J0 判 NOT_RUN，本节快照随即失效。

| 输入 | sha256（前 16 位） | 字节 | mtime |
| --- | --- | --- | --- |
| `source/desktop/game/ui.py` | `53f7b7d53cb1fcff` | 135269 | 2026-11-21 23:35:00 |
| `source/desktop/game/game_art.py` | `4ade48ff03f2eb78` | 10668 | 2026-11-21 23:33:13 |
| `source/desktop/game/ui_asset_binding.py` | `70f5f9b6c2c92757` | 10518 | 2026-11-21 23:35:04 |
| `source/desktop/game/assets/p_table.json` | `5d459a8b82737c00` | 250711 | 2026-11-21 23:30:55 |

复跑结果：

```
verdict = FAIL    completion_claim = not-attested
检查项 10 条 / 细分断言 46 条
PASS=2  FAIL=1  NOT_RUN=7  CONFLICT=0
  S2 PASS   game_art.py 三键齐备（room_key / card_key / character_key），ledger() 存在
  S3 PASS   DEFAULT_CACHE_CAPACITY=160 ≥ 128
  S1 FAIL   ui.py create_image 仅 1 处（行 2140）< 4 —— 接线只完成 1/4
  J0-J6 NOT_RUN  缺 qa/game_art_probe.json（探针未运行）
```

**读数变化过程（同一脚本，30 分钟内两次复跑）**：

| 时点 | S1 | S2 | S3 | 说明 |
| --- | --- | --- | --- | --- |
| 23:33:41 | NOT_RUN（0 处） | PASS | FAIL（64） | `game_art.py` 刚落地，`ui.py` 未接线 |
| 23:35:04 | FAIL（1 处） | PASS | PASS（160） | `ui.py` 出现首个 `create_image`；容量上调到 160 |

**读法**：这是"实现进行中"的如实快照，不是 A-33 FAIL 的结论。J0–J6 全 NOT_RUN（探针未产出）不足以判 PASS；S1 只接线 1 处，说明四处接线尚未完成（棋盘 / 抽卡 / 面板 / tooltip）。

### 11.2 仪器校准（在项目外临时目录做，未写仓库）

为证明本脚本既能判 PASS 也能判 FAIL，用四份一次性夹具跑过：

| 夹具 | 注入内容 | 期望 | 实测 |
| --- | --- | --- | --- |
| `probe_green.json` | 全绿探针（10 房 / 3 卡 / 3 人 / 20 条账本） | J0–J6 PASS | J0–J6 **全 PASS**；S1/S2 NOT_RUN、S3 FAIL（如实反映实现状态） |
| `probe_red.json` | 5 处已知缺陷：卡面 `300×336`、1 条占位、`placeholder_hits=1`、`name_ambiguous=2`、`unreachable` 多 `attic`、详情图元 `200×200` | 对应 J FAIL | **J1/J2/J3/J5/J6 全 FAIL**，detail 逐条给出数字（如"比例偏离 5:7 25.0% (>2%)"） |
| `probe_no_shot.json` | 抽掉全部截图 | J2/J5 NOT_RUN | **J2/J5 NOT_RUN**，其余仍 PASS |
| `probe_legacy.json` | 尺寸命中旧口径 96/192 | J5 CONFLICT | **J5 CONFLICT**，detail 报"命中旧口径 96x96（本轮口径 112x112），需书面裁决" |

> 校准时点为 2026-11-21 23:33 的输入哈希。此后 `ui.py` / `ui_asset_binding.py` 继续被改写，再跑 `probe_green.json` 会得到 `J0 NOT_RUN（ui_py_sha256 不一致）`——这正是 J0-3 该有的行为：**旧截图不能给新产物背书**。要复现上表的 PASS，必须用当前源码重跑探针，而不是复用旧夹具。

结论：脚本不存在"永远 PASS"或"永远 FAIL"的退化路径；缺证据只落 NOT_RUN，缺陷必落 FAIL，口径冲突落 CONFLICT。

---

## 12. 不可自动验证（`unavailableChecks`，不进 PASS）

1. **"缓存淘汰 + 无自持引用 → canvas 图元空白"的端到端可见性**：需长时间 zoom 抖动并逐帧采图，本轮不做；J1-2/J1-5/J5-5 只覆盖"当帧有图"与"关闭后释放"，不覆盖"淘汰后变空白"。
2. **三档 DPI（96/120/144）下的对局重拍**：A-33 只按 `probe.environment.system_dpi` 复算尺寸；跨档一致性仍归 A-19/A-20/A-21。
3. **对局区叠字后的实测对比度**：RK-07 明确不做（A-22 按设计值口径）。
4. **美术美观 / 风格一致性**：人工目检，见 §13 的 MANUAL 清单。
5. **卡名/房名与画面语义对应**：由 A-30 的 M-15（47/47 语义评审签字）覆盖，不重复计数。
6. **`storeroom` 是否"应该"可见**：只断言"显式登记为不可达"，不断言可见性。
7. **PyInstaller 打包后 PIL/ImageTk 是否可加载**：属打包验证，不在 A-33。
8. **同房 4 名玩家 28–32 px 头像与 14 px 错位步距的重叠情况**：需渲染后目检，机读不可判。

---

## 13. 与既有 A 表兼容 + 停止规则

不得削弱既有项：

1. **不删、不跳、不降级任何既有断言**；A-33 不得作为 A-19/20/21/22/32 的替代证据，反之 `A-32 PASS` 也不代表 A-33 PASS。
2. **A-33 PASS 不得抵消任何 NOT_RUN**；若 A-19/20/21 仍 NOT_RUN，claim 上限仍是 `partial`。
3. 执行器侧（`run_p_table_execution.py` 的 `compute_a_table`）与本文必须**判据等价**：同一份 JSON、同一组阈值；执行器可少写细项，但不得比独立验收宽（例如不得跳过 `unreachable` 与 `name_ambiguous`）。
4. **MANUAL_ITEMS（显式不做机读断言）**：美术美观/风格统一、语义对应（归 A-30）、叠字对比度（归 A-22）、动画/转场、高 DPI 观感。

停止规则：

- S3 未过（容量 <128）不进探针阶段；探针未产出不进 J1–J6 判定。
- J0 未通过（哈希不符/缺 dpi/非 real-tk）时，J1–J6 全部 NOT_RUN，不得"挑几条能算的算"。
- 独立验收与执行器结论不一致 → 回实现定位，不得在报告里择一采信。
- 任何输入在验收期间被改写 → 本轮作废重跑。

---

## 14. 变更记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1.0 | 2026-11-21 | 首版：J0–J6 + S1–S3 共 10 项检查 / 46 条断言；9 条排除项（U-01…U-09）；裁决 K-01…K-06（J5 112/160 口径、U-06 收窄、panel/portrait 合并、期望值独立复算、账本字段映射、三态边界）；RK-01…RK-10 责任映射；四份校准夹具 |
