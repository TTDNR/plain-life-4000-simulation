# v3 人物与家庭短场景报告

本报告只验证过程一致性、时间与身体代价、知识来源和可追溯性。它不是唯一正确结局，也不代表完整人类行为模型。

全部场景检查通过：`True`。

## 照护者外出找食物

场景：`caregiver_outing`，检查：`True`。

### 检查项

- `care_considered`: `True`
- `time_not_double_booked`: `True`
- `alternative_or_abandonment_path_explicit`: `True`
- `resume_capacity_is_reduced`: `True`

### 决定链

- `caregiver-food-plan` 第 1 日 480 分钟：personal_hunger_and_dependent_care_need
  可见信息：['near cattail patch observed', 'alternative caregiver present=True', 'far fish location not known']
  想到的办法：['take_dependent_to_near_patch', 'ask_alternative_caregiver_and_search_food', 'go_to_far_patch_alone', 'postpone_search_and_provide_care']
  选择：ask_alternative_caregiver_and_search_food；理由：['hunger=0.72', 'fatigue=0.45', 'child care cannot be skipped', 'alternative caregiver is present and trusted for care']
  实际结果：search scheduled after care arrangement

### 关键事件

- 第 1 日 480 分钟 `decision`: {'trigger': 'personal_hunger_and_dependent_care_need', 'chosen_option': 'ask_alternative_caregiver_and_search_food', 'work_scheduled': True, 'care_arrangement_accepted': True}

### 说明

- 该场景由照护责任和可信替代照护者决定，而不是固定服从户主。
- 若没有可信替代照护者，路径转为携带儿童或推迟。

## 邻居请求食物

场景：`neighbor_request`，检查：`True`。

### 检查项

- `request_has_actor_and_target`: `True`
- `donor_reserve_considered`: `True`
- `refusal_or_debt_path_available`: `True`
- `no_global_market_search`: `True`

### 决定链

- `neighbor-food-request` 第 2 日 600 分钟：neighbor_requested_food_after_household_shortage
  可见信息：['donor_surplus_days=7.83', 'requestor admits uncertainty about repayment', 'other distant households and prices are unknown']
  想到的办法：['give', 'exchange_labour', 'loan_with_repayment', 'refuse']
  选择：loan_with_repayment；理由：['household reserve=7.83 days', 'repayment trust=0.58', 'no uniform market price is assumed']
  实际结果：transferred_kcal=3000.0

### 关键事件

- 第 2 日 600 分钟 `request_response`: {'requestor_id': 'p000002', 'chosen_option': 'loan_with_repayment', 'transferred_kcal': 3000.0}

### 说明

- 该场景不是价格结算，只记录请求、赠与或借贷的具体条件。
- 一次借贷不会永久改变关系，也不自动建立市场。

## 发现新食物但未交流

场景：`personal_knowledge`，检查：`True`。

### 检查项

- `uncommunicated_relative_does_not_know`: `True`
- `communication_creates_location_knowledge`: `True`
- `communication_does_not_create_processing_skill`: `True`

### 决定链

### 关键事件

- 第 1 日 720 分钟 `knowledge_observed`: {'subject': 'resource.oak_acorn/known_patch', 'stage': 'independent'}
- 第 1 日 721 分钟 `knowledge_check`: {'subject': 'resource.oak_acorn/known_patch', 'knows': False}
- 第 1 日 780 分钟 `knowledge_told`: {'listener_id': 'p000322', 'subject': 'resource.oak_acorn/known_patch', 'stage': 'rough_route', 'certainty': 0.6}

### 说明

- 地点知识不等于加工技能。

## 教授加工方法

场景：`teaching_processing`，检查：`True`。

### 检查项

- `teaching_needs_contact_time`: `True`
- `practice_started_before_independent`: `True`
- `independent_requires_practice`: `True`
- `teacher_time_is_reserved`: `True`

### 决定链

### 关键事件

- 第 2 日 600 分钟 `teaching`: {'learner_id': 'p000322', 'subject': 'skill.acorn_processing', 'teacher_hours': 1.5, 'learner_hours': 1.5}
- 第 3 日 540 分钟 `guided_practice`: {'subject': 'skill.acorn_processing', 'practice_count': 1, 'stage': 'guided_practice'}
- 第 4 日 540 分钟 `guided_practice`: {'subject': 'skill.acorn_processing', 'practice_count': 2, 'stage': 'guided_practice'}
- 第 5 日 540 分钟 `guided_practice`: {'subject': 'skill.acorn_processing', 'practice_count': 3, 'stage': 'independent'}

### 说明

- 一次演示只能到达 `demonstrated`，独立操作需要三次实践。

## 持续吃不饱

场景：`persistent_hunger`，检查：`True`。

### 检查项

- `deficit_persists`: `True`
- `hunger_increases`: `True`
- `work_capacity_decreases`: `True`
- `family_care_burden_increases`: `True`
- `death_threshold_not_invented`: `True`

### 决定链

### 关键事件

- 第 1 日 1200 分钟 `daily_body_update`: {'ration_kcal': 1200.0, 'deficit_kcal': 1100.0, 'energy_balance_kcal': -1100.0, 'hunger': 0.47, 'work_capacity': 0.6555999999999998}
- 第 2 日 1200 分钟 `daily_body_update`: {'ration_kcal': 1200.0, 'deficit_kcal': 1100.0, 'energy_balance_kcal': -2200.0, 'hunger': 0.69, 'work_capacity': 0.552}
- 第 3 日 1200 分钟 `daily_body_update`: {'ration_kcal': 1200.0, 'deficit_kcal': 1100.0, 'energy_balance_kcal': -3300.0, 'hunger': 0.9099999999999999, 'work_capacity': 0.4596}
- 第 4 日 1200 分钟 `daily_body_update`: {'ration_kcal': 1200.0, 'deficit_kcal': 1100.0, 'energy_balance_kcal': -4400.0, 'hunger': 1.0, 'work_capacity': 0.41059999999999997}
- 第 5 日 1200 分钟 `daily_body_update`: {'ration_kcal': 1200.0, 'deficit_kcal': 1100.0, 'energy_balance_kcal': -5500.0, 'hunger': 1.0, 'work_capacity': 0.41059999999999997}
- 第 6 日 1200 分钟 `daily_body_update`: {'ration_kcal': 1200.0, 'deficit_kcal': 1100.0, 'energy_balance_kcal': -6600.0, 'hunger': 1.0, 'work_capacity': 0.3994}
- 第 7 日 1200 分钟 `daily_body_update`: {'ration_kcal': 1200.0, 'deficit_kcal': 1100.0, 'energy_balance_kcal': -7700.0, 'hunger': 1.0, 'work_capacity': 0.3994}
- 第 8 日 1200 分钟 `daily_body_update`: {'ration_kcal': 1200.0, 'deficit_kcal': 1100.0, 'energy_balance_kcal': -8800.0, 'hunger': 1.0, 'work_capacity': 0.3882}
- 第 9 日 1200 分钟 `daily_body_update`: {'ration_kcal': 1200.0, 'deficit_kcal': 1100.0, 'energy_balance_kcal': -9900.0, 'hunger': 1.0, 'work_capacity': 0.3882}
- 第 10 日 1200 分钟 `daily_body_update`: {'ration_kcal': 1200.0, 'deficit_kcal': 1100.0, 'energy_balance_kcal': -11000.0, 'hunger': 1.0, 'work_capacity': 0.377}
- 第 11 日 1200 分钟 `daily_body_update`: {'ration_kcal': 1200.0, 'deficit_kcal': 1100.0, 'energy_balance_kcal': -12100.0, 'hunger': 1.0, 'work_capacity': 0.377}
- 第 12 日 1200 分钟 `daily_body_update`: {'ration_kcal': 1200.0, 'deficit_kcal': 1100.0, 'energy_balance_kcal': -13200.0, 'hunger': 1.0, 'work_capacity': 0.3658}
- 另有 `2` 个事件保存在机器结果中。

### 说明

- 身体状态连续累积，没有在换日时清零。
- 本轮不指定死亡阈值；疾病机制仍未建模。

## 家庭食物分配差异

场景：`family_food_allocation`，检查：`True`。

### 检查项

- `claims_are_individual`: `True`
- `allocation_varies_by_need_and_claim`: `True`
- `food_limited_by_stock`: `True`
- `objection_recorded`: `True`
- `no_permanent_formula`: `True`

### 决定链

- `household-ration` 第 4 日 1080 分钟：household_food_store_cannot_cover_all_claims
  可见信息：['available_kcal=6000.0', 'child and nursing claims were raised first', 'worker offered to accept less', 'other adult considers equal shares fair']
  想到的办法：['equal_shares', 'prioritize_children', 'prioritize_workers', 'custodian_decides', 'temporary_priority_under_negotiation']
  选择：temporary_priority_under_negotiation；理由：['this is a current shortage, not a permanent rule', 'dependency and care needs differ', 'the other adult objects to the result']
  实际结果：allocations={'p000863': 1249.4793835901708, 'p000861': 1954.1857559350271, 'p000862': 1724.2815493544356, 'p000864': 1072.0533111203665}; underfed_person_ids=['p000862', 'p000864']

### 关键事件

- 第 4 日 1080 分钟 `food_allocated`: {'claim': ('nursing_priority', 0.85), 'allocated_kcal': 1954.1857559350271, 'need_kcal': 2300.0, 'hunger_after': 0.3251770095793419}
- 第 4 日 1080 分钟 `food_allocated`: {'claim': ('labor_priority', 0.75), 'allocated_kcal': 1724.2815493544356, 'need_kcal': 2300.0, 'hunger_after': 0.3751561849229488}
- 第 4 日 1080 分钟 `food_allocated`: {'claim': ('dependent_priority', 1.0), 'allocated_kcal': 1249.4793835901708, 'need_kcal': 1250.0, 'hunger_after': 0.2502082465639317}
- 第 4 日 1080 分钟 `food_allocated`: {'claim': ('equal_claim', 0.65), 'allocated_kcal': 1072.0533111203665, 'need_kcal': 1650.0, 'hunger_after': 0.42513536026655563}

### 说明

- 分配结果取决于本次缺口、照护责任和协商，不是永久公式。
- 不满与实际分配都单独记录；工人可以主动少取，其他人也可以反对。

## 家庭间共享火与临时住所

场景：`shared_fire_and_shelter`，检查：`True`。

### 检查项

- `request_has_specific_resource`: `True`
- `carrying_time_affects_fire`: `True`
- `trust_is_domain_specific`: `True`
- `shelter_measured_as_protection`: `True`
- `donor_not_forced`: `True`

### 决定链

- `share-fire-and-shelter` 第 6 日 1020 分钟：neighbor_has_no_fire_and_weak_shelter_before_rain
  可见信息：['transport_minutes=1', 'neighbor has previously handled fire carefully', 'donor has enough fuel and temporary space', 'return or reciprocal labor is not guaranteed']
  想到的办法：['share_burning_ember', 'teach_fire_making', 'offer_temporary_shelter', 'exchange_ember_for_labor', 'refuse']
  选择：share_burning_ember；理由：['compatible fire-handling trust', 'request can be served without exhausting donor fire', 'temporary shelter avoids sending vulnerable household back into rain']
  实际结果：ember_survived=True, shared_shelter=True

### 关键事件

- 第 6 日 1020 分钟 `request_response`: {'request_type': 'fire_and_shelter', 'chosen_option': 'share_burning_ember', 'transport_minutes': 1, 'ember_survived': True, 'shared_shelter': True}

### 说明

- 共享火种需要携带时间、容器和适合的受托人。
- 遮蔽按获得保护衡量，不要求求助家庭独立建房。

## 高速运行后回看人物

场景：`trace_replay`，检查：`True`。

### 检查项

- `factual_events_preserved`: `True`
- `self_account_uses_event_explanation`: `True`
- `summary_marked_as_generated`: `True`
- `no_fabricated_dialogue`: `True`

### 决定链

### 关键事件

- 第 1 日 480 分钟 `observed_resource`: {'resource': 'cattail', 'cell': 3350}
- 第 1 日 540 分钟 `attempted_processing`: {'success': False, 'reason': 'not_enough_practice'}

### 说明

- 事实、人物自述和阅读摘要分开保存。
- 没有实际交谈时不会输出对白。

## 边界

- 情绪、信任、承诺、教学和跨家庭协作只实现短场景基础，不扩展为长期社会模拟。
- 身体后果使用连续状态和劳动能力变化；本轮没有凭空指定死亡阈值。
- 疾病机制尚未实现，状态必须明确显示 `health_mechanism_modeled=false`。
- 叙述视图只使用事件发生时人物已知的信息，不补写未发生的对白。
