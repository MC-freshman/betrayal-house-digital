# #74 怪物舞会

原名：Monster Mash（官方编号 54，作者 Bruce Glassco）

## 触发

房间：Dining Room、Gallery、Master Bedroom、Servants' Quarters；预兆：Letter

## 英雄手册

### 现在

预留若干属性检定令牌（三角形）。英雄目标轨道已由引擎建立：按弱点驱逐不低于探索者数一半（向上取整）的怪物；每只怪物对应一张特定预兆牌

### 你对坏人的了解

叛徒设定：舞会主人（不可被攻击），召集经典怪物

### 获胜条件

按弱点驱逐不低于探索者数一半（向上取整）的怪物；每只怪物对应一张特定预兆牌

## 叛徒手册

### 现在

你的角色仍在游戏中，但已变为叛徒。按引擎叛徒轨道推进：舞会主人（不可被攻击），召集经典怪物

### 获胜条件

舞会主人（不可被攻击），召集经典怪物

## 引擎建模说明

本剧本为 Widow's Walk 骨架实现（skeleton）：双进度轨 + 检定型行动；
官方怪物：Banshee(弱: Spirit Board)、Crimson Jack(弱: Photograph)、Demon Lord(弱: Holy Symbol)、Dracula(弱: Spear)、Frankenstein's Monster(弱: Girl)、Mummy(弱: Book)、Witch(弱: Cat)、Zombie Lord(弱: Vial)。
官方原文的简化建模与差异逐条登记在 haunt_rules.py 的 engine_note。
