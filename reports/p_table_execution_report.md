# P 表最终收口报告（final）

- report_id：p-table-final-20261121T194105
- claim_scope：execution
- 总判定：**PASS**
- completion_claim：**attested**
- 自检（实现方，非签发口径）：见 JSON self_check 子字段
- 生成时间：2026-11-21T19:50:51；profile=final

## 结论

P 表执行完成（attested）。范围：桌面端 142 行 × 33 列的资源位登记、142/142 usable 的真实标注、145 个运行时 PNG 与 UI 取图链路。47 个美术缺口已在 run5 落实（复用 47 文件 + 130 张无损转码）；usable 不等于可发布。

### blockers

- run5 v2：47 个缺口已全部落实（0 missing / 0 partial / 142 usable），execution 侧无缺口阻断；content-release 仍待语义评审与 WCAG 抽样（见 A-30/A-32）

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
| A-04 | G1 | P 表结构 | PASS | records=142 columns=33 |
| A-05 | G1 | 可用性计数 | PASS | usable/partial/missing/corrupted/duplicate=142/0/0/0/0 |
| A-06 | G1 | 分类计数 | PASS | character/room/card_event/card_item/card_omen=12/50/45/22/13 |
| A-07 | G1 | 映射 | PASS | mapping entries=142 unresolved=0 |
| A-08 | G1 | 运行时 PNG | PASS | rooms=50 cards=80 characters=12 placeholders=3（合计 145） |
| A-09 | G1 | missing 语义 | N/A | run5 C-04 退役：0 missing 后本项失去断言对象；missing=0 pending=0 fallback=0；缺口语义由 A-30 / V07 接手 |
| A-10 | G2 | 旧自检 | PASS | verify_assets 收尾复跑 17/17（exit 0） |
| A-11 | G2 | 契约 | PASS | 契约收尾复跑 32 PASS / 0 FAIL（exit 0） |
| A-12 | G2 | 新测试 | PASS | 新测试 63/63（fail=0 error=0，基线 48）；探针 runner 63 条（fail=0 error=0 skip=0） |
| A-13 | G2 | 独立验收 P0 | PASS | P0 27/27（fail=0 not_run=0） |
| A-14 | G2 | 独立验收 P1/P2 | PASS | P1 rate=1.0（executed=22）；P2 rate=1.0（executed=5） |
| A-15 | G2 | SAFE-01 | PASS | SAFE-01=PASS |
| A-16 | G3 | 行覆盖 | PASS | 行覆盖 86.33% / 90.64%（阈值 85%） |
| A-17 | G3 | 分支覆盖 | PASS | method=condition-jump-arc；asset_pipeline.py 313/376=83.24%; asset_registry.py 196/256=76.56% |
| A-18 | G4 | 峰值 RSS | PASS | 5/5 次 --stage all；最大峰值 68.4 MiB ≤1536 MiB（verdict_basis=max） |
| A-19 | G5 | UI 100% | PASS | 100% 真实截图：room=128x128 card=240x336 window=1000x760 |
| A-20 | G5 | UI 125% | PASS | 125% 真实截图：room=160x160 card=300x420 window=1250x950；tk_scaling=1.3330 偏离参考 1.667（Tk 启动缓存，以物理尺寸断言为准） |
| A-21 | G5 | UI 150% | PASS | 150% 真实截图：room=192x192 card=360x504 window=1500x1140；tk_scaling=1.6681 偏离参考 2.000（Tk 启动缓存，以物理尺寸断言为准） |
| A-22 | G5 | 对比度 | PASS | 图形 7.85:1 ≥3:1；正文 12.65:1 ≥4.5:1（wcag-relative-luminance(ui.PALETTE design values)） |
| A-23 | G4 | 性能 15 项 | PASS | 15/15 性能有实测且达标（PT-PERF-02/03/07/08/10/13/14/15 为 run4 补测；PT-PERF-09 按 C-1 归并 qa/rss_probe.json 5 次峰值，verdict_basis=max，不重复采集） |
| A-24 | G6 | 报告一致性 | PASS | 四口径一致（报告 claim/verdict、门禁计算、独立验收 achieved） |
| A-25 | G7 | 缺陷 | PASS | 无 open 的 S1/S2；S3/S4 已全部关闭 |
| A-26 | G6 | 可复现 | PASS | 第二次干净复跑一致（对比基线 p-table-final-20261121T192918；数据哈希/测试/覆盖率/RSS 与性能判定一致；性能数值抖动 16 项，允许） |
| A-27 | G7 | 内容台账 v2 | PASS | 142/142 全覆盖（source+provenance+release 7 列齐全）；缺口 0；promotion map 47 行 / gap closure 47 行 |
| A-28 | G7 | 声明与签发 | PASS | 产品负责人已签发（2026-11-20）：scope=47 个美术缺口为内容积压，不阻断 completion_claim@execution；小程序端不在本轮范围；独立验收人由 verify_p_table_final.py 承担 |
| A-29 | G1 | WW 隔离完整 | PASS | WW 残留=0；content_ww.py=存在；导入命中=0；_ww_deferred=50；placeholders=3；assets_ww=100 |
| A-30 | G1 | 47 位 0 missing | PASS | 0 missing；47 位台账齐全；语义评审 47/47 已签字 |
| A-31 | G1 | 130 张真 PNG | PASS | 转码 130 条；像素 max diff=0；ext_mismatch=0；备份 130 个 |
| A-32 | G5 | 142 张规格 | PASS | 142/142 运行时 IHDR 精确；真 PNG；alpha 规则一致；M-13 可读性 142/142 通过 |
| X-DRIFT | G2 | check_core_drift | PASS | exit=0 |
| X-V1 | G2 | verify_v1 | PASS | exit=0 |

## 产物身份（冻结哈希）

| 文件 | 字节 | sha256 |
| --- | --- | --- |
| content.py | 71962 | `461f8aeb95e32fb31d185c1f65f46f13405d3233c5575a5c853a012e6964c147` |
| asset_pipeline.py | 69285 | `560ff7549037b1ce6ed9c8a013989e82e69f0041a4a2526805e8469d6607d82b` |
| asset_registry.py | 21654 | `07fbe4d8cdfca4554b6894914c7f6126dd98263a2c064d41bc10a2ffd17a77ab` |
| ui_asset_binding.py | 10306 | `2513a9537b1f29e96e53f17c9c800b36c062581a1d01c115aca956bca6a472ef` |
| verify_assets.py | 52228 | `c96dee9aa2b4b796f17b8b58480f3b9a7412a8ca9e681bfb27df1b513cf27da5` |
| qa/verify_assets_contract.py | 89878 | `15be573b5d3991181406a76b11f1ecd2e8a7164544aab4c78f76015bb27711bc` |
| qa/test_p_table_execution.py | 57430 | `b02fff74c272ecc0ab352afd9c9cc5bf002731a6b51eb7dc7ab16fb803cd7f82` |
| qa/coverage_probe.py | 9949 | `41a0664df4efd67bb39fbcc6c92c0154112ba423d61ab3f94ed4958b7f7d95fd` |
| qa/run_p_table_execution.py | 150773 | `e53038f734e479eae0aab650170cad9303d3e9f0e62ac717361027dbd58dcc32` |
| qa/make_fixtures.py | 6078 | `fbc85301d693513783d7b6a7e1f8ebdbc229afb016f8d9fcab7a98c3357a4ee1` |
| assets/p_table.json | 250711 | `5d459a8b82737c001f0101c3027b0fdcf5886b259dbce25c0b85177a54bcbc2f` |
| assets/p_table.csv | 105114 | `b2c811ad7af4b438b415ac111e3db10215a5fe93ebd62f4781c67ce4a093a454` |
| assets/asset_mapping.json | 57891 | `984c57d3759e38de8933c001df5d0301fa2457abd551b2fcd036bc3f0a381167` |

## 覆盖率 / RSS / UI 摘要

- 分支覆盖 asset_pipeline.py：313/376=83.24%（method=condition-jump-arc）
- 分支覆盖 asset_registry.py：196/256=76.56%（method=condition-jump-arc）
- 性能 PT-PERF-01 ptable 构建：median=193.986 ms / p95=222.931 / max=222.931（预算 5000.0 ms）→ 达标
- 性能 PT-PERF-04 registry load：median=6.332 ms / p95=19.258 / max=19.258（预算 150.0 ms）→ 达标
- 性能 PT-PERF-05 10k resolve：median=5.122 ms / p95=7.757 / max=7.757（预算 500.0 ms）→ 达标
- 性能 PT-PERF-06 verify_assets.py：median=6761.4 ms / p95=6858.0 / max=6858.0（预算 90000.0 ms）→ 达标
- 性能 PT-PERF-11 UI 房间首帧(512->128)：median=10.383 ms / p95=12.204 / max=102.125（预算 120.0 ms）→ 达标
- 性能 PT-PERF-12 UI 卡牌首帧(480x672->240x336)：median=14.731 ms / p95=15.97 / max=17.007（预算 150.0 ms）→ 达标
- 性能 PT-PERF-13 UI 缓存命中(同图重复绑定)：median=0.621 ms / p95=1.44 / max=2.499（预算 16.0 ms）→ 达标
- 性能 PT-PERF-14 一屏 12 图块批量绑定：median=133.512 ms / p95=141.423 / max=141.423（预算 400.0 ms）→ 达标
- 性能 PT-PERF-02 placeholders 构建：median=92.775 ms / p95=138.409 / max=138.409（预算 3000.0 ms）→ 达标
- 性能 PT-PERF-03 --stage all 全量构建：median=36802.161 ms / p95=36807.021 / max=36807.021（预算 240000.0 ms）→ 达标
- 性能 PT-PERF-07 契约脚本全量(含解码)：median=15248.5 ms / p95=15505.1 / max=15505.1（预算 150000.0 ms）→ 达标
- 性能 PT-PERF-08 契约脚本 --no-decode：median=3316.4 ms / p95=3377.5 / max=3377.5（预算 25000.0 ms）→ 达标
- 性能 PT-PERF-10 registry load 峰值增量 RSS：median=0.559 MiB / p95=0.633 / max=0.633（预算 80.0 MiB）→ 达标
- 性能 PT-PERF-15 冷启动到主界面：median=1447.85 ms / p95=1643.2 / max=1643.2（预算 2500.0 ms）→ 达标
- 性能 PT-PERF-09 构建峰值 RSS(--stage all)：median=68.2 MiB / p95=68.4 / max=68.4（预算 1536.0 MiB）→ 达标
- RSS：5 次 --stage all 峰值=[68.4, 67.86, 68.2, 68.39, 67.97]；max=68.4 MiB ≤1536；verdict_basis=max；pass=True
- UI 100%：status=pass（approximated=False）room=128x128 card=240x336 source/desktop/game/qa/screenshots/ui_100.png
- UI 125%：status=pass（approximated=False）room=160x160 card=300x420 source/desktop/game/qa/screenshots/ui_125.png
- UI 150%：status=pass（approximated=False）room=192x192 card=360x504 source/desktop/game/qa/screenshots/ui_150.png

## 未执行 / NOT_RUN


## 复现（A-26，§16 可复现段）

- 对比基线：p-table-final-20261121T192918（compared_at=2026-11-21T19:50:51）
- 容差口径：run4_completion_criteria.md §7.2：数据哈希/测试结果/覆盖率/RSS 与性能判定必须一致；计时/时间戳与性能中位数数值抖动可容忍；执行器/管线脚本哈希升级使两轮不构成同代码背靠背对（§7.1 R2）
- 一致性：**identical=true（数据哈希/测试/覆盖率/RSS 与性能判定全部一致）**
- 允许抖动：RSS max_peak_mib 68.43 -> 68.4（峰值波动，允许）
- 允许抖动：PT-PERF-01 中位数 278.479 -> 193.986 ms（允许抖动）
- 允许抖动：PT-PERF-02 中位数 116.468 -> 92.775 ms（允许抖动）
- 允许抖动：PT-PERF-03 中位数 48441.469 -> 36802.161 ms（允许抖动）
- 允许抖动：PT-PERF-04 中位数 9.377 -> 6.332 ms（允许抖动）
- 允许抖动：PT-PERF-05 中位数 8.005 -> 5.122 ms（允许抖动）
- 允许抖动：PT-PERF-06 中位数 8461.8 -> 6761.4 ms（允许抖动）
- 允许抖动：PT-PERF-07 中位数 19951.5 -> 15248.5 ms（允许抖动）
- 允许抖动：PT-PERF-08 中位数 4333.3 -> 3316.4 ms（允许抖动）
- 允许抖动：PT-PERF-09 中位数 68.33 -> 68.2 MiB（允许抖动）

## 声明与签发

- 未执行项不折算 PASS；approximated 不冒充真实 DPI；缺口已闭环为 0 missing；claim 绑定产物哈希，任一关键产物变化即失效。
- 失效条件：任一关键产物（p_table/映射/content.py/ui.py/ui_asset_binding.py/asset_pipeline.py/asset_registry.py/测试/探针）sha256 变化；OS/DPI 设置变化导致 UI 截图不再代表当前环境；问题日志新增 S1/S2 open 缺陷；独立验收重跑结果与本报告 verdict/claim 冲突
- 签发：实现方执行器不自签 attested；产品负责人 + 独立验收人待签发。

