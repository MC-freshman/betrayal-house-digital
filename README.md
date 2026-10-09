# 山中小屋 · 电子版（非官方粉丝实现）

《山中小屋》（Betrayal at House on the Hill）的桌面电子版：Python 3.9 + tkinter，
**全部 70 本剧本**（含原版 1–50 与扩充 51–70）均有专属机制实现——令牌、怪物特殊规则、
逐步剧本行动、独立胜负判定与进度摘要，无通用兜底脚本。

当前桌面版本 **v3.7（2026-10-09）**。从 [GitHub Releases](https://github.com/MC-freshman/betrayal-house-digital/releases/latest)
下载 Windows 便携包，解压后双击 `山中小屋.exe` 或 `启动游戏.bat`，无需安装 Python。
使用方法、相对 v3.6 的改动与验证限制见 [发布说明](docs/发布说明-v3.7.md)。本次仓库更新仅包含桌面版。

## 功能

- 本地模式：单人 / 同屏热座，可加入机器人，4–6 人
- 机器人：三档难度 × 三种风格；带同源攻击合法性判定、集火、分散、护送揭示者等策略
- 联机：主机/客户端模式（局域网或 NATFRP 隧道），支持断线重连与联机存读档
- 内置规则、卡牌与房间图鉴、骰子结果展示

## 运行

需要带 tkinter 的 Python 3.9：

```bash
git clone https://github.com/MC-freshman/betrayal-house-digital.git game
cd game
python launcher.py
```

源码目录需命名为 `game`，启动器按此包名加载模块。`python build_exe.py` 可重新构建；
在本项目完整目录布局下默认写入项目根的 `release/`，独立克隆时请用
`python build_exe.py --dist release` 显式指定输出目录。构建需要 PyInstaller，并会收集动态加载的全部剧本模块。

## 测试

```bash
python replay_golden.py            # 186 条端到端种子回放（黄金基准）
python verify_haunt_systems.py     # 177 项剧本系统专项验证（2665 条断言）
python check_core_drift.py         # 需本地完整项目的兄弟目录小程序后端；独立克隆不适用
python verify_v1.py                # 桌面 UI 层回归（需 tkinter）
```

黄金基准默认读同目录 `golden_replays.json`；换环境时可先
`GOLDEN_BASELINE_FILE=本地路径 python replay_golden.py --update` 生成"本地参考
基线"再做前后对照，不会覆盖已提交基准（基准哈希与生成它的解释器/环境绑定，
历史基准在当前环境无法复现）。2026-10-09 复核：历史基准 186 条均有差异；
改动前的本地参考基线仅 5 条差异，均来自剧本 2 / 68 的术语调整，其余 181 条一致。
`verify_haunt_systems.py` 仍在剧本 17 的杀虫剂断言失败；这些是公开记录的验证限制，
不能把本版称为全量回归通过。详见发布说明。本次未重新生成黄金基准以消除差异。

## 结构

```
game/            规则引擎、bot、桌面 UI、haunt handler 与剧本译文（本仓库根）
  haunts/        剧本模块包：共享基类 + 70 个逐剧本实现
  haunts_zh/     70 本剧本玩家手册译文（Markdown）
  net/           联机协议与序列化
  docs/          桌面版发布说明
```

## 免责声明

本项目是爱好者制作的非官方粉丝实现，与 Avalon Hill / Wizards of the Coast 无任何关联，
也不是官方产品。剧本内容改编自原版桌游规则，仅供学习交流；请购买并支持正版桌游。
未随仓库分发任何官方规则书 PDF 或扫描图。仓库内容默认保留所有权利（All Rights Reserved），
未经许可请勿商用。
