# 山中小屋 · 电子版（非官方粉丝实现）

《山中小屋》（Betrayal at House on the Hill）的桌面电子版：Python 3.9 + tkinter。
剧本 1–70 全部为专属机制实现（令牌、怪物特殊规则、逐步剧本行动、独立胜负判定），无通用兜底脚本。

当前状态 **v3.9（2026-11-21）**：P 表 142 个资源位全部落实到真图，完成判定
`completion_claim = attested`、`verdict = PASS`（A 表 33 PASS / 0 FAIL / 0 NOT_RUN / 1 N/A，
G1–G7 全 PASS，独立验收 0 FAIL）。

Windows 便携包下载：[GitHub Releases](https://github.com/MC-freshman/betrayal-house-digital/releases/latest)。
解压后双击 `山中小屋.exe` 或 `启动游戏.bat`，无需安装 Python。

## 功能

- 本地模式：单人 / 同屏热座，可加入机器人，4–6 人
- 机器人：三档难度 × 三种风格；带同源攻击合法性判定、集火、分散、护送揭示者等策略
- 联机：主机/客户端模式（局域网或 NATFRP 隧道），支持断线重连与联机存读档
- 内置规则、道具/房间图鉴、美术预览、骰子结果展示
- 美术资源：142 个资源位全部为真实图片（角色 320×320、房间 512×512、卡牌 480×672），
  由 `photos/` 母版经 `asset_pipeline.py` 规范化生成运行时 PNG

## 从源码运行

需要带 tkinter 的 Python 3.9（例如 `D:\Various_programming_languages\pycharm\python3.9\python.exe`）：

```bat
cd source\desktop\game
python launcher.py                 :: 统一启动器：本地 / 联机客户端 / 联机主机
python launcher.py --mode local    :: 直接进本地对局
```

## 构建 EXE

```bat
cd source\desktop\game
python build_exe.py --check        :: 只检查环境（Python 3.9 + tkinter + PyInstaller）
python build_exe.py                :: 产物写到项目根 release\山中小屋.exe
```

打包要点：`--onefile --windowed`，`assets/` 以 `source/desktop/game/assets` 结构内嵌，
`haunts` 用 `--collect-submodules` 收集（剧本按名称动态加载，静态扫描发现不了）。
`photos/`（母版 830 MB）不进包，发布包只带规范化后的运行时 PNG。

发布包自检（无控制台，结果写 JSON，退出码 0 表示通过）：

```bat
release\山中小屋.exe --selftest-assets %TEMP%\selftest.json
```

校验项：清单可解析、142 条 `runtime_path` 全部命中文件、逐张可解码、尺寸与记录一致。

## 质量门禁

```bat
python verify_assets.py                          :: P 表自检 17 项
python qa\verify_assets_contract.py --json       :: 契约 32 条
python qa\test_p_table_execution.py              :: 新测试 63 条
python qa\coverage_probe.py --json qa\coverage_probe.json
python qa\run_p_table_execution.py --profile final
python qa\verify_p_table_execution.py --tk --json > qa\p_table_verify_final.json
python qa\verify_p_table_final.py --tk --json    :: 独立验收（只读）
```

最近一次实测：行覆盖 `asset_pipeline.py` 86.33% / `asset_registry.py` 90.64%；
分支覆盖 83.62% / 75.20%（阈值 75%）；15 项性能全部达标（ptable 构建中位 0.59 s，
预算 5 s）；峰值 RSS 68.3 MiB（预算 1536 MiB）；UI 三档 100% / 125% / 150% 真实截图全 PASS。

## 目录结构

```text
game/
├─ launcher.py              统一启动器（本地 / 客户端 / 主机 / 资源自检）
├─ ui.py                    主界面、美术预览、三档 DPI 缩放
├─ engine.py                规则引擎核心
├─ engine_parts/            探索、骰子、房间效果等分片
├─ content.py               基础内容：角色 / 房间 / 卡牌 / 剧本名（142 资源位基线）
├─ content_ww.py            Widow's Walk 扩充内容（已隔离，默认不导入）
├─ haunts/                  剧本 1–70 专属模块；_ww_deferred/ 为后延的扩充剧本
├─ haunts_zh/               剧本中文文案；_ww_deferred/ 同上
├─ asset_pipeline.py        photos/ → P 表 + 运行时 PNG（含探测缓存）
├─ asset_registry.py        P 表 → 运行时索引（支持源码与冻结包两种布局）
├─ ui_asset_binding.py      图片绑定与缓存、缺图兜底
├─ verify_assets.py         P 表 17 项自检
├─ build_exe.py             PyInstaller 打包
├─ assets/                  运行时 PNG（142 + 3 占位图）
├─ assets_ww/               Widow's Walk 占位图（后延）
├─ qa/                      验收与探针脚本、测试、证据 JSON
└─ reports/                 最终执行报告（JSON + Markdown）
```

## 资源管线

`photos/`（母版，不入库）分 `role/ room/ event/ item/ omen/` 五类；
`photos/_source_jpeg/` 是转码前原件备份，扫描时显式排除。

```bat
python asset_pipeline.py --stage ptable        :: 只重建 P 表与映射（有探测缓存，约 0.6 s）
python asset_pipeline.py --stage normalize     :: 重新规范化运行时 PNG
python asset_pipeline.py                       :: 全量：P 表 + 占位图 + 规范化
```

探测缓存按 `(相对路径, 字节数, mtime_ns)` 失效，文件一变立即重算；内容不变时幂等不落盘，
因此只读审计（SAFE-01）不会把它判成并发写入。

## 范围说明

- **Widow's Walk 扩充**（20 房间 / 50 剧本 / 30 卡牌 / 屋顶层）已完成调研与内容隔离，
  但按产品决策**后延**：内容位于 `content_ww.py`、`haunts/_ww_deferred/`、`assets_ww/`，
  默认不参与构建与验收（A-29 校验隔离完整性）。重新纳入时改为显式导入即可。
- **微信小程序端**不在本仓库范围。

## 声明

非官方粉丝实现，仅供学习与个人娱乐，不用于商业用途。
《Betrayal at House on the Hill》及相关角色、卡牌、房间名称版权归 Wizards of the Coast 所有。
仓库内美术资源为 AI 生成图，风格参照原作但非原作素材复制。
