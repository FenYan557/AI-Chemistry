# 新 Schema v2 初版实施记录

2026-10-20；LOCAL_ONLY。用户已授权直接执行前述八步计划，控制主模型与可报销模型消耗。旧版及讨论只读，工作范围为本目录。默认不提交、不推送。

## 当前交付（2026-10-20，v0.4计划已实施，schema v4）

用户已授权按计划重建，并澄清按A2lab-key较便宜模型的能力下限设计，最终模型未定。当前实现4.0.0-draft，说明见[v4重建说明](v4重建说明.md)，计划见[实施计划_v0.4](实施计划_v0.4.md)。

- [x] T1：任务/模型能力下限与结构取舍，见重建说明§1；实际模型未知不阻塞重建。
- [x] T2：4项必填精简抽取契约；内部事实17→6项必填；治理与证据状态分开，类型目录留后台。
- [x] T3：按角色投影，修复反向边、伪造基准与null/表格异常；开放事实不强行成边。
- [x] T4：自然语言证据卡、S式引用、代码侧references及显式audit；允许背景知识/推断/库外候选。
- [x] T5：88测试通过；两个bundle无block；来源快照对齐与预算通过；生成文档及模型实测记录。

样例3篇4块14事实，9条登记关系，27实体8规范边；另有1条真实模型抽取导入示例。不是全库或金标。没有修改旧版本/讨论/清洗原材料，未提交推送。

分工实际结果：A2lab qwen3.6-flash工具型校验子任务exit=0但无产物，未验收、主侧接管。另3次有界无文件任务用于12条批量三路烟雾回答、修订后4条回答及1条抽取；后者实际写了文件，主侧核实后移入examples并导入。完整元数据及失败见reports/model_probe_v4.json。

局限：批量三路不隔离，不能证明参数知识或图谱收益。修正字段泄露后仍有引用错配/推断过实/JSON转义不稳定，未声称领域回答验收通过。最终接入模型与正式问答入口均未完成接入；这些不是本目录schema实现未完成。后续只针对选定模型和实际应用接入验证，不自动全库重抽。

## 最新已实现范围（v0.3）：schema 按九项重构，只做 schema 不做全库图谱

用户口径：README 与 schema 都按九项（实体类型/关系签名/标识合并/属性边界/词表/约束处置/上下文 n-ary/溯源/治理 + 消费端契约 + 复用标准）组织；本轮只交付 schema 与少量真实片段事例，不建全库图谱。之前"物化层 + 三档 + 治理文档"的待办并入本轮完成。

已完成：

- `schema/records.schema.json` → `3.0.0-draft`：新增 `entities`、`edges`（可重建物化层）、`identity_merges`（合并/拆分/拒并留痕）、`outcome.magnitude`（程度限定）、`outcome.comparison`（比较基准）、`facts.cited_work`（转述目标）；`condition`/`outcome`/`relation_ref` 提为 `$defs`。
- 新登记表：`registry/entity_types.json`（39 类，17 core 带判据/正反例/边界，22 proposed 写明不能实例化的原因）；`registry/relations.json`（14 关系补域/值域/方向/基数，core 2）；`registry/vocab.json`（封闭集、指标/参数/单位、晋升流程、属性表示边界）；`registry/identity_rules.json`（ID 规则、合并协议、跨源对齐）；`registry/consumer_contract.json`（10 个检索键 + A–E 排序档）；`registry/standards_mapping.json`（PROV-O/SOSA/QUDT/ChEBI 字段映射）；`schema/constraints.json`（94 码三档 + 复杂度预算）。
- `scripts/materialize.py` v2：实体/边确定性派生，只有 reviewed 身份才写入 `identity_id`，新增 `retrieval_keys()`。
- `scripts/validate.py`：三档处置（`valid` = 无 block），新增实体/边/合并/程度/基准/转述目标检查；每个码必须在约束目录登记，否则报 `CONSTRAINT_CATALOG_GAP`。
- `scripts/render_schema.py` 重写：`schema/schema.md` 按九项 + 消费端契约 + 标准映射组织（14 节，正好卡在预算上限）。
- 新脚本 `scripts/check_budget.py`；测试扩到 72 项（新增物化确定性、检索键、三档覆盖、预算强制、词表与枚举一致、九项导航落点存在性）；`records.schema.json` 用 `x-nine-items` 声明九项与落点，render 从它生成总览表。
- 事例（真实片段，非全库）：`examples/hard_cases.json` 补程度限定、显式比较基准、晶面/织构三条身份与两条合并记录、r11 签名正例；两个 bundle 均 `valid`、block 0。

未做 / 不在本轮：聚合层（冲突/共识/推荐窗口）、真实转述片段验证、单位换算、全库事实抽取、别名与结构消歧（仍按用户要求暂缓）。不报准确率。

模型调用：本轮 0 次，未调用任何外部模型。

## 最新范围（v0.2，优先于下方早期计划）
用户指定混合精简方案并要求先给新计划：以[实施计划_v0.2](实施计划_v0.2.md)为当前依据。保留五层逻辑骨架，L2角色采用带条件、证据、其他/未知项的枚举多选；物质别名和结构消歧、外部资源查询暂缓。旧版Role已为枚举、Parameter已为注册表；不合并Feature与Indicator，不因小样本低频直接删类。

## 已完成（2026-10-20）

- `schema/records.schema.json`：L0–L4 记录契约；新增 `role_assignments`（受控多选、绑定事实与条件）。
- `registry/roles.json`：7 个角色选项与作答规则；`registry/candidates.json`：39 类型/14 关系候选（未冻结）。
- `scripts/profile_corpus.py`：48 篇清单（哈希、块/表计数、主题线索，明确非精读）。
- `scripts/build_examples.py`：3 篇 4 块 → 9 提及、6 事实、5 角色记录；`reports/source_alignment.json` 全部文本与当前清洗产物逐字一致。
- `scripts/validate.py`：结构（jsonschema）+ 引用/偏移/条件归属/身份/角色规则；样例 0 错误、11 警告。
- `scripts/map_pilot.py`：旧试跑 58 提及全部逐字可定位；18 事实引用均在快照；3 条 `relation_raw` 省略号拼接、6 条需拆分。
- `tests/test_validate.py`：14 项测试通过（含引用篡改、名称相似合并、单位状态矛盾、角色 other/unknown 缺依据、角色主体非参与者、重复角色）。
- 角色选择题探测：见 `reports/role_probe_20261020.json`。
- 协议表达力验证（零模型调用）：`examples/hard_cases.json` 12 条真实片段事实 + `scripts/review_protocol.py`；结果 `reports/protocol_review.json`：支持 9 项、部分 2 项、缺失 4 项。
- 验证过程中发现并修复一个真实缺陷：定性结果无处表达（原 quantity 只有字符串值，迫使我用占位串冒充数值）。已加 `value_kind = numeric/qualitative/ordinal/absent`，定性/缺失值不再要求逐字出现在证据中。

## 模型调用记录

- `kimi-for-coding`：一次调用，429（7 日额度耗尽），input/output token 均 0，无产物。
- 按用户授权改用同 key 已登记备用模型 `qwen3.6-flash`：一次调用成功，5879 输入 / 326 输出 token，num_turns=1。
- 探测发现三处协议漏洞：条件未拆分、CMP inhibitor 被并入电沉积 suppressor、无依据时输出空数组而非 unknown。已写入报告，未据此宣称模型能力或准确率。

## 已验证的缺口（已处理）

2026-10-20 补齐三项：表格单元格锚点（`evidence.kind=table_cell`，对真实 CSV 逐格校验）、Experiment/Run 与条件继承（inherited 条件必须能在所属 Run 找到同参数同值）、样品与处理前后状态（`samples` + `derived_from_sample_id` + `outcome.sample_id`）。

复核 `reports/protocol_review.json`：支持 12 项、部分 2 项（程度限定、被引目标）、缺失 1 项（聚合层）。测试 22 项通过，两个样例 bundle 均 0 错误。

## 可读 schema

`schema/schema.md` 由 `scripts/render_schema.py` 从 `records.schema.json`、`registry/roles.json` 与 `validate.py` 生成：11 类记录、字段表、受控词表、48 个错误码与 10 个警告码。改契约后需重新渲染，避免文档与实现漂移。

## 未完成

全库事实抽取、消歧与外部合并（按用户要求暂缓）、Conflict/KnowledgeUnit/推荐窗口、抽取准确率与问答效果验证。未提交 Git。

## 早期范围与复用决定（以下原计划保留追溯，冲突处以v0.2为准）
- 完成通用记录协议、候选字典、化学身份映射、48篇范围清单、真实片段映射与校验；不全库调用LLM、不训练BERT、不做全面框架对照。
- 用 JSON Schema Draft 2020-12 / python-jsonschema（本机已装4.26.0）验证格式；不自行实现结构验证引擎。领域校验是小型适配层。
- 已核查 AutoSchemaKG、EDC、iText2KG、SAC-KG 等资料，复用前序选型结论。它们不提供本项目全部条件/证据记录；本轮不克隆改写上游、不宣称复现这些论文。
- PubChem、ChEBI只作身份和分类候选，保存证据与版本；本轮有限查询，失败留记录，不批量导入百科。
- 外部核对来源：PubChem PUG REST、ChEBI、OPSIN、QUDT 的官方文档已在前序讨论核对。
- 结构、字典、实例分离，原始候选可保存，不能仅因缺单位/条件或新标签拒收；未核验信息不获比较/推荐资格。
- 身份边界、条件作用范围、作者语气需语义核对；格式检查不作准确率证明。

## 任务与验收
- [x] P0/S：语料清单与分类线索，48篇文件哈希可追溯，明确不是48篇精读。
- [x] P0/M：通用Schema与候选字典，新增类型/关系候选合法，样例/反例有依据。
- [x] P0/M：实体提及与规范身份分离（结构层面；消歧延后）；同名/同缩写不自动跨文献合并，盐型与电荷保留。
- [x] P0/M：引用/映射/条件归属校验与使用状态报告，真实样本通过，注入错误被拦截。
- [ ] P0/S：外部资源查询（用户已要求暂缓，本轮不执行），确认结果不覆盖文献断言。
- [x] P0/S：使用说明、限制、样例审查与调用用量记录。

依赖：语料→Schema/字典→样例与校验→验收。不做跨文件并行写入。
执行分工：主智能体实现/验收；可报销模型一次固定短提示评议，无文件读取、工具或递归代理要求。

## 当前状态
已建立目录及计划。一次kimi-for-coding精简评议已发出；额度不足或失败不自动重试、不切自费凭据。不存在API级硬token预算开关，采用单任务、固定输入、短输出控制。
机器检查→主侧读产物与失败案例；没有独立人工金标、无需预制QA。未完成全库语义覆盖和问答效用验证。

## 进度与偏差
| 阶段 | 状态 | 实际依据 |
| --- | --- | --- |
| 范围/分析/计划 | 完成 | 复用本轮前序讨论；机器结构与实际事实分开 |
| 实施 | 完成 | 契约、角色字典、样例、校验、映射、测试 |
| 验收 | 完成 | 14 项测试通过；样例 0 错误 11 警告；48 篇清单一致 |
| 归档/交付 | 待执行 | 完成后保存实际报告 |

目前无范围漂移；S.U.P.E.R检查采用职责分离、标准依赖、可撤销映射、少量文件，不使用无依据数值评分。
