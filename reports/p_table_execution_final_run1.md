# P 表最终收口报告（final）

- report_id：p-table-final-20261120T151148
- claim_scope：execution
- 总判定：**FAIL**
- completion_claim：**not-attested**
- 自检（实现方，非签发口径）：见 JSON self_check 子字段
- 生成时间：2026-11-20T15:16:42；profile=final

## 结论

not-attested。阻断项与下一动作见 blockers 与 §15；47 个美术缺口为内容积压，不是本次判定的原因（若 A-27 PASS）。

### blockers

- A-03 串行与只读：独立验收快照过期：快照 2026-11-20T15:05:54 早于 assets/p_table.json
- A-13 独立验收 P0：快照过期，P0 不能归属当前产物：快照 2026-11-20T15:05:54 早于 assets/p_table.json
- A-14 独立验收 P1/P2：快照过期，P1/P2 不能归属当前产物：快照 2026-11-20T15:05:54 早于 assets/p_table.json
- A-15 SAFE-01：快照过期：快照 2026-11-20T15:05:54 早于 assets/p_table.json
- A-20 UI 125%：125% status=approximated（tk scaling 近似，pass=false）；真实 120/144 DPI 需系统改缩放后重启应用重拍
- A-21 UI 150%：150% status=approximated（tk scaling 近似，pass=false）；真实 120/144 DPI 需系统改缩放后重启应用重拍
- A-25 缺陷：S3/S4 仍 open（有责任域/关闭条件/复审日期）：PT-SCOPE-001, PT-ART-001, PT-UI-003, PT-ENV-001
- A-26 可复现：对比基线 p-table-final-20261120T145843 与本轮之间执行器/管线脚本升级（qa/run_p_table_execution.py），不构成 §7.1 同代码背靠背对；A-26 以同代码两轮复跑为准（数据哈希一致性已在 §16 记录）
- A-28 声明与签发：报告由实现方执行器生成；attested 必须由产品负责人 + 独立验收人共同签发，实现方不得自签；签发页留待外部签署
- 47 个缺口仍为 missing/占位（12 角色 / 1 房间 / 34 事件；31 缺省替代图 + 16 事件回退），不计入 usable，不阻断 completion_claim@execution、阻断 content-release

## 门禁 G1-G7

| 门禁 | 判据 | 状态 | 组内 FAIL | 组内 NOT_RUN |
| --- | --- | --- | --- | --- |
| G1 数据完整性 | PASS | - | - |
| G2 测试门禁 | NOT_RUN | - | A-13, A-14, A-15 |
| G3 覆盖率 | PASS | - | - |
| G4 性能与峰值 RSS | PASS | - | - |
| G5 UI 与三档 DPI | NOT_RUN | - | A-20, A-21 |
| G6 证据完整性 | NOT_RUN | - | A-03, A-26 |
| G7 治理与内容台账 | NOT_RUN | - | A-25, A-28 |

## 验收表 A-01…A-28

| ID | 门禁 | 判据 | 状态 | 说明 |
| --- | --- | --- | --- | --- |
| A-01 | G6 | claim 范围与产物身份 | PASS | claim_scope=execution；冻结哈希 全部一致（13 项） |
| A-02 | G6 | 环境冻结 | PASS | 环境九项齐全 |
| A-03 | G6 | 串行与只读 | NOT_RUN | 独立验收快照过期：快照 2026-11-20T15:05:54 早于 assets/p_table.json |
| A-04 | G1 | P 表结构 | PASS | records=142 columns=33 |
| A-05 | G1 | 可用性计数 | PASS | usable/partial/missing/corrupted/duplicate=0/95/47/0/0 |
| A-06 | G1 | 分类计数 | PASS | character/room/card_event/card_item/card_omen=12/50/45/22/13 |
| A-07 | G1 | 映射 | PASS | mapping entries=95 unresolved=47 |
| A-08 | G1 | 运行时 PNG | PASS | rooms=49 cards=46 placeholders=3 |
| A-09 | G1 | missing 语义 | PASS | missing=47 pending=31 fallback=16 |
| A-10 | G2 | 旧自检 | PASS | verify_assets 收尾复跑 17/17（exit 0） |
| A-11 | G2 | 契约 | PASS | 契约收尾复跑 32 PASS / 0 FAIL（exit 0） |
| A-12 | G2 | 新测试 | PASS | 新测试 48/48（fail=0 error=0）；探针 runner 48/48 |
| A-13 | G2 | 独立验收 P0 | NOT_RUN | 快照过期，P0 不能归属当前产物：快照 2026-11-20T15:05:54 早于 assets/p_table.json |
| A-14 | G2 | 独立验收 P1/P2 | NOT_RUN | 快照过期，P1/P2 不能归属当前产物：快照 2026-11-20T15:05:54 早于 assets/p_table.json |
| A-15 | G2 | SAFE-01 | NOT_RUN | 快照过期：快照 2026-11-20T15:05:54 早于 assets/p_table.json |
| A-16 | G3 | 行覆盖 | PASS | 行覆盖 87.7% / 88.96%（阈值 85%） |
| A-17 | G3 | 分支覆盖 | PASS | method=condition-jump-arc；asset_pipeline.py 263/310=84.84%; asset_registry.py 187/246=76.02% |
| A-18 | G4 | 峰值 RSS | PASS | 5/5 次 --stage all；最大峰值 68.07 MiB ≤1536 MiB（verdict_basis=max） |
| A-19 | G5 | UI 100% | PASS | 100% 真实截图：room=128x128 card=240x336 window=1000x760 |
| A-20 | G5 | UI 125% | NOT_RUN | 125% status=approximated（tk scaling 近似，pass=false）；真实 120/144 DPI 需系统改缩放后重启应用重拍 |
| A-21 | G5 | UI 150% | NOT_RUN | 150% status=approximated（tk scaling 近似，pass=false）；真实 120/144 DPI 需系统改缩放后重启应用重拍 |
| A-22 | G5 | 对比度 | PASS | 图形 7.85:1 ≥3:1；正文 12.65:1 ≥4.5:1（wcag-relative-luminance(ui.PALETTE design values)） |
| A-23 | G4 | 性能 15 项 | PASS | 15/15 性能有实测且达标（PT-PERF-02/03/07/08/10/13/14/15 为 run4 补测；PT-PERF-09 按 C-1 归并 qa/rss_probe.json 5 次峰值，verdict_basis=max，不重复采集） |
| A-24 | G6 | 报告一致性 | PASS | 四口径一致（报告 claim/verdict、门禁计算、独立验收 achieved） |
| A-25 | G7 | 缺陷 | NOT_RUN | S3/S4 仍 open（有责任域/关闭条件/复审日期）：PT-SCOPE-001, PT-ART-001, PT-UI-003, PT-ENV-001 |
| A-26 | G6 | 可复现 | NOT_RUN | 对比基线 p-table-final-20261120T145843 与本轮之间执行器/管线脚本升级（qa/run_p_table_execution.py），不构成 §7.1 同代码背靠背对；A-26 以同代码两轮复跑为准（数据哈希一致性已在 §16 记录） |
| A-27 | G7 | 内容台账 | PASS | 47 缺口 12 角色 / 1 房间 / 34 事件；31 缺省替代图 + 16 事件回退；全部 missing |
| A-28 | G7 | 声明与签发 | NOT_RUN | 报告由实现方执行器生成；attested 必须由产品负责人 + 独立验收人共同签发，实现方不得自签；签发页留待外部签署 |
| X-DRIFT | G2 | check_core_drift | PASS | exit=0 |
| X-V1 | G2 | verify_v1 | PASS | exit=0 |

## 产物身份（冻结哈希）

| 文件 | 字节 | sha256 |
| --- | --- | --- |
| content.py | 71088 | `0aff89a8483fd3c16e8aebd71edfdbf9be3a4032a3dcbe18f0d8afed3627f8d7` |
| asset_pipeline.py | 59730 | `d51f1dcd3b4a64aaeff1b77357f446695a427ef5d907bb179a09546ba940e331` |
| asset_registry.py | 20206 | `0a40b8fa4591baa5ba7fd7134483ea500491ab7f62143e13448742d3773cb4ba` |
| ui_asset_binding.py | 9633 | `9453d5da3b623e22067575cc9b704f1cd0a2e85c9bcf276eb68f3a99edadf0c8` |
| verify_assets.py | 43550 | `12f33ea651424e27c0ed65e7b712536b7090fda32a919d9f9e4389c6b130fde1` |
| qa/verify_assets_contract.py | 88831 | `0673070f19d62fdf7fcb70200bfc2bc40a32d52d3c9dd7cb8cdb342351cb67c2` |
| qa/test_p_table_execution.py | 39494 | `150a0fd49eb6aed6975570aa89da67b10d7853aadf68fab89a93d78aaa74d554` |
| qa/coverage_probe.py | 9949 | `41a0664df4efd67bb39fbcc6c92c0154112ba423d61ab3f94ed4958b7f7d95fd` |
| qa/run_p_table_execution.py | 135725 | `5715c5ac172a5afd129a62ae853cf905272d3fdb3f1c6c8021e9c2ab281c4eb1` |
| qa/make_fixtures.py | 6078 | `fbc85301d693513783d7b6a7e1f8ebdbc229afb016f8d9fcab7a98c3357a4ee1` |
| assets/p_table.json | 256902 | `c233a1f040cc857dcc8a75ce1d33da7cfbc181b2a7589e25b62c99b19f67a66c` |
| assets/p_table.csv | 110260 | `42e094ff3c30d401f27c510aad888a50e5c0b79bcea6008002ada39352d05f31` |
| assets/asset_mapping.json | 73306 | `3f0596de7f2f539a554904bbfb05b5b607b4fcaa3fc5c97e8eee49c49abff751` |

## 覆盖率 / RSS / UI 摘要

- 分支覆盖 asset_pipeline.py：263/310=84.84%（method=condition-jump-arc）
- 分支覆盖 asset_registry.py：187/246=76.02%（method=condition-jump-arc）
- 性能 PT-PERF-01 ptable 构建：median=2820.397 ms / p95=2916.509 / max=2916.509（预算 5000.0 ms）→ 达标
- 性能 PT-PERF-04 registry load：median=5.782 ms / p95=23.653 / max=23.653（预算 150.0 ms）→ 达标
- 性能 PT-PERF-05 10k resolve：median=4.958 ms / p95=7.851 / max=7.851（预算 500.0 ms）→ 达标
- 性能 PT-PERF-06 verify_assets.py：median=1326.5 ms / p95=1367.3 / max=1367.3（预算 90000.0 ms）→ 达标
- 性能 PT-PERF-11 UI 房间首帧(512->128)：median=8.952 ms / p95=11.5 / max=18.134（预算 120.0 ms）→ 达标
- 性能 PT-PERF-12 UI 卡牌首帧(480x672->240x336)：median=12.204 ms / p95=14.239 / max=14.474（预算 150.0 ms）→ 达标
- 性能 PT-PERF-13 UI 缓存命中(同图重复绑定)：median=0.575 ms / p95=1.139 / max=1.73（预算 16.0 ms）→ 达标
- 性能 PT-PERF-14 一屏 12 图块批量绑定：median=117.855 ms / p95=126.774 / max=126.774（预算 400.0 ms）→ 达标
- 性能 PT-PERF-02 placeholders 构建：median=81.91 ms / p95=105.826 / max=105.826（预算 3000.0 ms）→ 达标
- 性能 PT-PERF-03 --stage all 全量构建：median=22416.514 ms / p95=22509.781 / max=22509.781（预算 240000.0 ms）→ 达标
- 性能 PT-PERF-07 契约脚本全量(含解码)：median=3572.6 ms / p95=3608.3 / max=3608.3（预算 150000.0 ms）→ 达标
- 性能 PT-PERF-08 契约脚本 --no-decode：median=1017.0 ms / p95=1032.9 / max=1032.9（预算 25000.0 ms）→ 达标
- 性能 PT-PERF-10 registry load 峰值增量 RSS：median=1.438 MiB / p95=1.465 / max=1.465（预算 80.0 MiB）→ 达标
- 性能 PT-PERF-15 冷启动到主界面：median=1057.55 ms / p95=1214.0 / max=1214.0（预算 2500.0 ms）→ 达标
- 性能 PT-PERF-09 构建峰值 RSS(--stage all)：median=67.5 MiB / p95=68.07 / max=68.07（预算 1536.0 MiB）→ 达标
- RSS：5 次 --stage all 峰值=[67.5, 67.49, 67.33, 67.8, 68.07]；max=68.07 MiB ≤1536；verdict_basis=max；pass=True
- UI 100%：status=pass（approximated=False）room=128x128 card=240x336 source/desktop/game/qa/screenshots/ui_100.png
- UI 125%：status=approximated（approximated=True）room=160x160 card=300x420 source/desktop/game/qa/screenshots/ui_125_approx.png
- UI 150%：status=approximated（approximated=True）room=192x192 card=360x504 source/desktop/game/qa/screenshots/ui_150_approx.png

## 未执行 / NOT_RUN

- A-03（串行与只读）：独立验收快照过期：快照 2026-11-20T15:05:54 早于 assets/p_table.json
- A-13（独立验收 P0）：快照过期，P0 不能归属当前产物：快照 2026-11-20T15:05:54 早于 assets/p_table.json
- A-14（独立验收 P1/P2）：快照过期，P1/P2 不能归属当前产物：快照 2026-11-20T15:05:54 早于 assets/p_table.json
- A-15（SAFE-01）：快照过期：快照 2026-11-20T15:05:54 早于 assets/p_table.json
- A-20（UI 125%）：125% status=approximated（tk scaling 近似，pass=false）；真实 120/144 DPI 需系统改缩放后重启应用重拍
- A-21（UI 150%）：150% status=approximated（tk scaling 近似，pass=false）；真实 120/144 DPI 需系统改缩放后重启应用重拍
- A-25（缺陷）：S3/S4 仍 open（有责任域/关闭条件/复审日期）：PT-SCOPE-001, PT-ART-001, PT-UI-003, PT-ENV-001
- A-26（可复现）：对比基线 p-table-final-20261120T145843 与本轮之间执行器/管线脚本升级（qa/run_p_table_execution.py），不构成 §7.1 同代码背靠背对；A-26 以同代码两轮复跑为准（数据哈希一致性已在 §16 记录）
- A-28（声明与签发）：报告由实现方执行器生成；attested 必须由产品负责人 + 独立验收人共同签发，实现方不得自签；签发页留待外部签署

## 复现（A-26，§16 可复现段）

- 对比基线：p-table-final-20261120T145843（compared_at=2026-11-20T15:16:42）
- 容差口径：run4_completion_criteria.md §7.2：数据哈希/测试结果/覆盖率/RSS 与性能判定必须一致；计时/时间戳与性能中位数数值抖动可容忍；执行器/管线脚本哈希升级使两轮不构成同代码背靠背对（§7.1 R2）
- 一致性：**identical=false（存在硬差异，见下）**
- 差异：脚本哈希更新（执行器/管线升级，非 §7.2 数据哈希清单）：qa/run_p_table_execution.py
- 允许抖动：RSS max_peak_mib 68.17 -> 68.07（峰值波动，允许）
- 允许抖动：PT-PERF-01 中位数 2940.273 -> 2820.397 ms（允许抖动）
- 允许抖动：PT-PERF-02 中位数 76.329 -> 81.91 ms（允许抖动）
- 允许抖动：PT-PERF-03 中位数 22682.498 -> 22416.514 ms（允许抖动）
- 允许抖动：PT-PERF-04 中位数 5.225 -> 5.782 ms（允许抖动）
- 允许抖动：PT-PERF-05 中位数 5.389 -> 4.958 ms（允许抖动）
- 允许抖动：PT-PERF-06 中位数 1367.1 -> 1326.5 ms（允许抖动）
- 允许抖动：PT-PERF-07 中位数 3642.4 -> 3572.6 ms（允许抖动）
- 允许抖动：PT-PERF-08 中位数 1055.1 -> 1017.0 ms（允许抖动）
- 允许抖动：PT-PERF-09 中位数 67.81 -> 67.5 MiB（允许抖动）

## 声明与签发

- 未执行项不折算 PASS；approximated 不冒充真实 DPI；47 个缺口保持 missing；claim 绑定产物哈希，任一关键产物变化即失效。
- 失效条件：任一关键产物（p_table/映射/content.py/ui.py/ui_asset_binding.py/asset_pipeline.py/asset_registry.py/测试/探针）sha256 变化；OS/DPI 设置变化导致 UI 截图不再代表当前环境；问题日志新增 S1/S2 open 缺陷；独立验收重跑结果与本报告 verdict/claim 冲突
- 签发：实现方执行器不自签 attested；产品负责人 + 独立验收人待签发。

