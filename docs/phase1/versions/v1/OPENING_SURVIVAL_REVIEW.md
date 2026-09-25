# 开局生存核验报告

当前年度专项核验未通过。最初几天存在可行生存路径，但当前无群体分享、无经济交换的模型下，中期和年度食物获取出现决定性缺口。

试运行只测试角色已经定义的基础生存行为，不作为正式世界历史，也不代表已经实现可信的人类社会模拟。

## 时间窗

| 时间窗 | 结果 | 瓶颈 | 平均食物满足率 | 最低食物满足率 | 最低饮水满足率 | 最可能失败 |
| --- | --- | --- | ---: | ---: | ---: | --- |
| `initial_days` | evaluated | shelter, fire, and storage timing | 0.9833 | 0.9803 | 1.0 | food shortfall and care-related labor loss |
| `initial_weeks` | failed | food acquisition | 0.735 | 0.4678 | 1.0 | food shortfall and care-related labor loss |
| `first_season_transition` | failed | food acquisition | 0.2413 | 0.1712 | 1.0 | food shortfall and care-related labor loss |
| `first_year_plus` | failed | food acquisition | 0.2742 | 0.1663 | 1.0 | food shortfall and care-related labor loss |

## 可行获取路径

| 需求链 | 结果 | 路径或失败原因 |
| --- | --- | --- |
| `water` | evaluated | direct lakeshore drinking plus caregiver-assisted daily delivery |
| `food` | failed | available labor and processing throughput cannot cover demand |
| `shelter` | failed | material access or labor timing delays shelter |
| `fire` | evaluated | skilled friction attempts and repeated maintenance using dry wood |
| `tools` | evaluated | expedient stone edges improved by stone and wood working |
| `stable_supply` | failed | annual storage, regeneration, or labor creates a survival gap |

## 已确认的可行部分

- 淡水位点可从投放区到达。
- 无容器时可以直接饮用；照护者能够为不能自行取水的人送水。
- 最初三天可通过浆果、榛子、橡子、香蒲、慈姑和鱼类建立食物链。
- 木质和纤维材料足以开始搭建遮蔽。
- 有实际操作技能的人可以尝试摩擦取火，失败后仍可继续尝试。
- 石、木原料支持渐进式工具制作，缺少关键工匠不会被自动补齐。

## 主要瓶颈

- 当前没有定义人物之间的食物再分配、交换或互助决策。试运行不假设家庭自动共享，因此掌握橡子加工等技能的少数家庭会先取得高热量库存，没有技能的家庭持续失败。
- 4000 人在 50 平方公里内的局部采集速度超过家庭自行探索和迁移的恢复速度。
- 家庭照护会显著削减可劳动时间；幼儿、老人和行动受限者集中于部分家庭时，这些家庭的获取能力明显更低。
- 食物储存需要处理、干燥和保存安排，现有基础行为只保留按物种腐败率计算的简化仓库。

## 最可能失败环节

年度检查的最差日为第 `194` 天，首要风险是食物而不是饮水。

在补齐食物分配、劳动交换、信任形成与家庭间决策前，不能通过扩大资源产量来宣布年度生存可行。该缺口是需求缺口，不是可由试运行隐藏的参数问题。

## 探索与迁移

- 初始家庭营地：`231` 个不同单元。
- 发生迁移的家庭：`73`。
- 迁移事件：`73`。
- 年度结束时探索半径上限：`5.0 km`。
- 探索知识按家庭分别维护；没有全体共享地图。
- 搬迁不等于形成政权，也不自动建立新群体认同。

## 必须修正的需求缺口

1. 定义家庭之间在食物、火种、照护和知识上的交换或拒绝规则。
2. 定义信任形成速度与信息传播范围，避免依赖全知指挥。
3. 明确个人和家庭迁移决策所需的有限信息，以及出发、返程和放弃规则。
4. 明确伤害、疾病、体力消耗和死亡如何影响后续劳动能力。
5. 明确储存、加工场地和食品保质条件，尤其是橡子、鱼和肉类。
