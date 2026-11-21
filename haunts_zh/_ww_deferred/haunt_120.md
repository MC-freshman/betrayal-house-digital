# #120 我们来玩个游戏

原名：Let's Play a Game（官方编号 100，作者 John Borba）

## 触发

房间：Abandoned Room、Dungeon、Gymnasium、Junk Room；预兆：Letter

## 英雄手册

### 现在

预留若干属性检定令牌（三角形）。英雄目标轨道已由引擎建立：在死亡或 Turn/Damage 轨到 0 前完成自己的全部 Challenges

### 你对坏人的了解

叛徒设定：无叛徒：Hangman 猜词死亡游戏（含电影梗）

### 获胜条件

在死亡或 Turn/Damage 轨到 0 前完成自己的全部 Challenges

## 叛徒手册

### 现在

你的角色仍在游戏中，但已变为叛徒。按引擎叛徒轨道推进：无叛徒：Hangman 猜词死亡游戏（含电影梗）

### 获胜条件

无叛徒：Hangman 猜词死亡游戏（含电影梗）

## 引擎建模说明

本剧本为 Widow's Walk 骨架实现（skeleton）：双进度轨 + 检定型行动；
官方怪物：无独立怪物。
官方原文的简化建模与差异逐条登记在 haunt_rules.py 的 engine_note。
