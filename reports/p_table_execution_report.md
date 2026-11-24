# P 表最终收口报告（final）

- report_id：p-table-final-20261124T223702
- claim_scope：execution
- 总判定：**PASS**
- completion_claim：**attested**
- 自检（实现方，非签发口径）：见 JSON self_check 子字段
- 生成时间：2026-11-24T22:56:21；profile=final

## 结论

P 表执行完成（attested）。范围：桌面端 274 行 × 33 列的资源位登记、274/274 usable 的真实标注、277 个运行时 PNG 与 UI 取图链路。47 个美术缺口已在 run5 落实（复用 47 文件 + 130 张无损转码）；usable 不等于可发布。

### blockers

- run5 v2：47 个缺口已全部落实（0 missing / 0 partial / 274 usable），execution 侧无缺口阻断；content-release 仍待语义评审与 WCAG 抽样（见 A-30/A-32）

## 门禁 G1-G7

| 门禁 | 判据 | 状态 | 组内 FAIL | 组内 NOT_RUN |
| --- | --- | --- | --- | --- |
| G1 数据完整性 | PASS | - | - |
| G2 测试门禁 | PASS | - | - |
| G3 覆盖率 | PASS | - | - |
| G4 性能与峰值 RSS | PASS | - | - |
| G5 UI 与三档 DPI | PASS | - | - |
| G6 证据完整性 | PASS | - | - |
| G7 治理与内容台账 | PASS | - | - |

## 验收表 A-01…A-28

| ID | 门禁 | 判据 | 状态 | 说明 |
| --- | --- | --- | --- | --- |
| A-01 | G6 | claim 范围与产物身份 | PASS | claim_scope=execution；冻结哈希 全部一致（13 项） |
| A-02 | G6 | 环境冻结 | PASS | 环境九项齐全 |
| A-03 | G6 | 串行与只读 | PASS | SAFE-01=PASS |
| A-04 | G1 | P 表结构 | PASS | records=274 columns=33 |
| A-05 | G1 | 可用性计数 | PASS | usable/partial/missing/corrupted/duplicate=274/0/0/0/0 |
| A-06 | G1 | 分类计数 | PASS | character/room/event/item/omen/monster/haunt/ending/card_back/room_back/dice=12/50/45/22/13/52/70/2/3/2/3 |
| A-07 | G1 | 映射 | PASS | mapping entries=274 unresolved=0 |
| A-08 | G1 | 运行时 PNG | PASS | rooms=50 cards=80 characters=12 placeholders=3（合计 145） |
| A-09 | G1 | missing 语义 | N/A | run5 C-04 退役：0 missing 后本项失去断言对象；missing=0 pending=0 fallback=0；缺口语义由 A-30 / V07 接手 |
| A-10 | G2 | 旧自检 | PASS | verify_assets 收尾复跑 17/17（exit 0） |
| A-11 | G2 | 契约 | PASS | 契约收尾复跑 32 PASS / 0 FAIL（exit 0） |
| A-12 | G2 | 新测试 | PASS | 新测试 90/90（fail=0 error=0，基线 48）；探针 runner 90 条（fail=0 error=0 skip=0） |
| A-13 | G2 | 独立验收 P0 | PASS | P0 27/27（fail=0 not_run=0） |
| A-14 | G2 | 独立验收 P1/P2 | PASS | P1 rate=1.0（executed=22）；P2 rate=1.0（executed=5） |
| A-15 | G2 | SAFE-01 | PASS | SAFE-01=PASS |
| A-16 | G3 | 行覆盖 | PASS | 行覆盖 96.09% / 95.13%（阈值 85%） |
| A-17 | G3 | 分支覆盖 | PASS | method=condition-jump-arc；asset_pipeline.py 362/410=88.29%; asset_registry.py 222/256=86.72% |
| A-18 | G4 | 峰值 RSS | PASS | 5/5 次 --stage all；最大峰值 85.52 MiB ≤1536 MiB（verdict_basis=max） |
| A-19 | G5 | UI 100% | PASS | 100% 真实截图：room=128x128 card=240x336 window=1000x760 |
| A-20 | G5 | UI 125% | PASS | 125% 真实截图：room=160x160 card=300x420 window=1250x950；tk_scaling=1.3330 偏离参考 1.667（Tk 启动缓存，以物理尺寸断言为准） |
| A-21 | G5 | UI 150% | PASS | 150% 真实截图：room=192x192 card=360x504 window=1500x1140；tk_scaling=1.6681 偏离参考 2.000（Tk 启动缓存，以物理尺寸断言为准） |
| A-22 | G5 | 对比度 | PASS | 图形 7.85:1 ≥3:1；正文 12.65:1 ≥4.5:1（wcag-relative-luminance(ui.PALETTE design values)） |
| A-23 | G4 | 性能 15 项 | PASS | 15/15 性能有实测且达标（PT-PERF-02/03/07/08/10/13/14/15 为 run4 补测；PT-PERF-09 按 C-1 归并 qa/rss_probe.json 5 次峰值，verdict_basis=max，不重复采集） |
| A-24 | G6 | 报告一致性 | PASS | 四口径一致（报告 claim/verdict、门禁计算、独立验收 achieved） |
| A-25 | G7 | 缺陷 | PASS | 无 open 的 S1/S2；S3/S4 已全部关闭 |
| A-26 | G6 | 可复现 | PASS | 第二次干净复跑一致（对比基线 p-table-final-20261124T221735；数据哈希/测试/覆盖率/RSS 与性能判定一致；性能数值抖动 16 项，允许） |
| A-27 | G7 | 内容台账 v2 | PASS | 274/274 全覆盖（source+provenance+release 7 列齐全）；缺口 0；promotion map 47 行 / gap closure 47 行 |
| A-28 | G7 | 声明与签发 | PASS | 产品负责人已签发（2026-11-20）：scope=47 个美术缺口为内容积压，不阻断 completion_claim@execution；小程序端不在本轮范围；独立验收人由 verify_p_table_final.py 承担 |
| A-29 | G1 | WW 隔离完整 | PASS | WW 残留=0；content_ww.py=存在；导入命中=0；_ww_deferred=50；placeholders=3；assets_ww=100 |
| A-30 | G1 | 47 位 0 missing | PASS | 0 missing；47 位台账齐全；语义评审 47/47 已签字 |
| A-31 | G1 | 130 张真 PNG | PASS | 转码 130 条；像素 max diff=0；ext_mismatch=0；备份 130 个 |
| A-32 | G5 | 274 张规格 | PASS | 274/274 运行时 IHDR 精确；真 PNG；alpha 规则一致；M-13 可读性 274/274 通过 |
| A-33 | G5 | 对局美术渲染 | PASS | 对局美术渲染 16/16 项 PASS（J0/J1/J2/J3/J4/J5/J6/J7/J8/J9/J10/J11/J12/S1/S2/S3）；探针见 qa/game_art_probe.json |
| X-DRIFT | G2 | check_core_drift | PASS | exit=0 |
| X-V1 | G2 | verify_v1 | PASS | exit=0 |

## 产物身份（冻结哈希）

| 文件 | 字节 | sha256 |
| --- | --- | --- |
| content.py | 79455 | `fb3c6e71344d9157416c5e12cbcb8c7c5bf978840dcff79d8715b9abf2a4b1f5` |
| asset_pipeline.py | 79586 | `a44267a9a3f94ab6f00f6eae67271bdffef39278ce56f44be5fba5cd40abc117` |
| asset_registry.py | 21935 | `9d81609d6109b35ea4e33a6cd250e2b730bc4199aa41d23fddde08c05c4a6302` |
| ui_asset_binding.py | 10518 | `70f5f9b6c2c927571e6380a95151353e50da969578723e598f69afcb3a13db60` |
| verify_assets.py | 55123 | `79dbbec50ed3492f514ff2eb22eafb33ef762de0d3aa63f5a930787bd8a4b6f4` |
| qa/verify_assets_contract.py | 96695 | `fdfe31d70d14408418bd6eb7d44e8dfb81fdf3189150dce14ce8e132cef59a81` |
| qa/test_p_table_execution.py | 87498 | `027845390e025d12e2a8c7bc8e32030c0593fbbb57a581a32c988fb142d0f5ea` |
| qa/coverage_probe.py | 9949 | `41a0664df4efd67bb39fbcc6c92c0154112ba423d61ab3f94ed4958b7f7d95fd` |
| qa/run_p_table_execution.py | 154913 | `39ed1cc43283ab1b8cee4803165b114ec846e340670bd69e5555d6deed2c292e` |
| qa/make_fixtures.py | 6078 | `fbc85301d693513783d7b6a7e1f8ebdbc229afb016f8d9fcab7a98c3357a4ee1` |
| assets/p_table.json | 445470 | `78f8d015044fe5c6e5dceb13453f3a4e2357002d1c7e3ac6131e5525128b687f` |
| assets/p_table.csv | 177389 | `5ded30ac02b0ff9a998309f8514ba659ffa0a632e061353c29380daf2580e289` |
| assets/asset_mapping.json | 105229 | `381a23f4a229c02d7355c3c3b77a665776ac07506c32788487820e87173d1b81` |

## 覆盖率 / RSS / UI 摘要

- 分支覆盖 asset_pipeline.py：362/410=88.29%（method=condition-jump-arc）
- 分支覆盖 asset_registry.py：222/256=86.72%（method=condition-jump-arc）
- 性能 PT-PERF-01 ptable 构建：median=325.897 ms / p95=364.248 / max=364.248（预算 5000.0 ms）→ 达标
- 性能 PT-PERF-04 registry load：median=11.176 ms / p95=23.059 / max=23.059（预算 150.0 ms）→ 达标
- 性能 PT-PERF-05 10k resolve：median=6.286 ms / p95=6.659 / max=6.659（预算 500.0 ms）→ 达标
- 性能 PT-PERF-06 verify_assets.py：median=10719.8 ms / p95=10897.1 / max=10897.1（预算 90000.0 ms）→ 达标
- 性能 PT-PERF-11 UI 房间首帧(512->128)：median=10.153 ms / p95=11.637 / max=101.884（预算 120.0 ms）→ 达标
- 性能 PT-PERF-12 UI 卡牌首帧(480x672->240x336)：median=14.655 ms / p95=18.11 / max=25.47（预算 150.0 ms）→ 达标
- 性能 PT-PERF-13 UI 缓存命中(同图重复绑定)：median=0.785 ms / p95=1.476 / max=1.735（预算 16.0 ms）→ 达标
- 性能 PT-PERF-14 一屏 12 图块批量绑定：median=132.653 ms / p95=144.47 / max=144.47（预算 400.0 ms）→ 达标
- 性能 PT-PERF-02 placeholders 构建：median=84.126 ms / p95=117.339 / max=117.339（预算 3000.0 ms）→ 达标
- 性能 PT-PERF-03 --stage all 全量构建：median=88640.284 ms / p95=88967.009 / max=88967.009（预算 240000.0 ms）→ 达标
- 性能 PT-PERF-07 契约脚本全量(含解码)：median=29093.2 ms / p95=29744.1 / max=29744.1（预算 150000.0 ms）→ 达标
- 性能 PT-PERF-08 契约脚本 --no-decode：median=5733.9 ms / p95=5758.3 / max=5758.3（预算 25000.0 ms）→ 达标
- 性能 PT-PERF-10 registry load 峰值增量 RSS：median=2.117 MiB / p95=2.133 / max=2.133（预算 80.0 MiB）→ 达标
- 性能 PT-PERF-15 冷启动到主界面：median=1223.85 ms / p95=1301.5 / max=1301.5（预算 2500.0 ms）→ 达标
- 性能 PT-PERF-09 构建峰值 RSS(--stage all)：median=85.52 MiB / p95=85.52 / max=85.52（预算 1536.0 MiB）→ 达标
- RSS：5 次 --stage all 峰值=[85.52, 85.52, 85.52, 85.5, 85.39]；max=85.52 MiB ≤1536；verdict_basis=max；pass=True
- UI 100%：status=pass（approximated=False）room=128x128 card=240x336 source/desktop/game/qa/screenshots/ui_100.png
- UI 125%：status=pass（approximated=False）room=160x160 card=300x420 source/desktop/game/qa/screenshots/ui_125.png
- UI 150%：status=pass（approximated=False）room=192x192 card=360x504 source/desktop/game/qa/screenshots/ui_150.png

## 未执行 / NOT_RUN


## 复现（A-26，§16 可复现段）

- 对比基线：p-table-final-20261124T221735（compared_at=2026-11-24T22:56:21）
- 容差口径：run4_completion_criteria.md §7.2：数据哈希/测试结果/覆盖率/RSS 与性能判定必须一致；计时/时间戳与性能中位数数值抖动可容忍；执行器/管线脚本哈希升级使两轮不构成同代码背靠背对（§7.1 R2）
- 一致性：**identical=true（数据哈希/测试/覆盖率/RSS 与性能判定全部一致）**
- 允许抖动：RSS max_peak_mib 85.78 -> 85.52（峰值波动，允许）
- 允许抖动：PT-PERF-01 中位数 392.455 -> 325.897 ms（允许抖动）
- 允许抖动：PT-PERF-02 中位数 94.984 -> 84.126 ms（允许抖动）
- 允许抖动：PT-PERF-03 中位数 88462.605 -> 88640.284 ms（允许抖动）
- 允许抖动：PT-PERF-04 中位数 14.392 -> 11.176 ms（允许抖动）
- 允许抖动：PT-PERF-05 中位数 7.167 -> 6.286 ms（允许抖动）
- 允许抖动：PT-PERF-06 中位数 12648.0 -> 10719.8 ms（允许抖动）
- 允许抖动：PT-PERF-07 中位数 29072.6 -> 29093.2 ms（允许抖动）
- 允许抖动：PT-PERF-08 中位数 5690.8 -> 5733.9 ms（允许抖动）
- 允许抖动：PT-PERF-09 中位数 85.56 -> 85.52 MiB（允许抖动）

## 声明与签发

- 未执行项不折算 PASS；approximated 不冒充真实 DPI；缺口已闭环为 0 missing；claim 绑定产物哈希，任一关键产物变化即失效。
- 失效条件：任一关键产物（p_table/映射/content.py/ui.py/ui_asset_binding.py/asset_pipeline.py/asset_registry.py/测试/探针）sha256 变化；OS/DPI 设置变化导致 UI 截图不再代表当前环境；问题日志新增 S1/S2 open 缺陷；独立验收重跑结果与本报告 verdict/claim 冲突
- 签发：实现方执行器不自签 attested；产品负责人 + 独立验收人待签发。

