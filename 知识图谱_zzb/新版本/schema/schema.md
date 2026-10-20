# 文献事实记录协议 v4：可读 schema（按九项组织）

本文由 `scripts/render_schema.py` 从 `schema/records.schema.json`、`schema/constraints.json` 与 `registry/*.json` 生成；字段说明为人工注解。**改契约或登记表后重新渲染，不要手改本文。**

状态：`4.0.0-draft`，未冻结。校验通过只表示结构与出处自洽，不表示化学结论正确，也不构成准确率。

## 九项覆盖（总览）

| # | 项 | 落点 | 判定机制 |
| --- | --- | --- | --- |
| 1 | 实体类型（节点类） | registry/entity_types.json | 判据/正例/反例/边界；无判据不可实例化（ENTITY_TYPE_UNDERSPECIFIED） |
| 2 | 关系定义域与值域（签名） | registry/relations.json | 只有启用且角色签名明确的关系生成边；开放关系保留事实用于检索 |
| 3 | 标识与唯一性 | registry/identity_rules.json + identity_merges | ID 规则；合并/拆分/拒并留痕；pending 合并不生效 |
| 4 | 属性表示边界 | registry/vocab.json#representation_policy | 何时升节点、何时留属性；跨实验比较须先值化 |
| 5 | 受控词表与枚举 | registry/vocab.json + registry/roles.json | 封闭取值与 schema 枚举逐项一致；候选晋升需依据 |
| 6 | 约束与处置 | schema/constraints.json | block/review/warn 三档 × 执行点；未登记码报 CONSTRAINT_CATALOG_GAP |
| 7 | 上下文与 n-ary | facts（文献陈述）+ edges（角色投影视图）+ outcome.magnitude/comparison | 条件挂事实；程度与比较基准显式；边不得自带新语义 |
| 8 | 溯源与可信度 | facts 的 statement_type/source_scope/polarity/modality/cited_work/extraction | 陈述归属与人工审核分开；pending不自动禁止忠实引用 |
| 9 | 演化与治理 | schema/constraints.json#budget + registry/vocab.json#promotion | 预算上限、迁移规则、晋升流程、命名与审计 |
| 补1 | 消费端契约 | registry/consumer_contract.json | 事实级检索；引用、数值比较、候选建议分别判断，不用A–E总档 |
| 补2 | 复用成熟标准 | registry/standards_mapping.json | PROV-O/SOSA/QUDT/ChEBI 字段映射；未核对术语留 null |

原则：为可判定性设计，不为完整性设计；任何类型、关系、约束都要能被实例检验。复杂度有显式预算，超预算必须先删再增。

模型输入使用schema/extraction.schema.json：每事实仅subject/relation/statement/quote四项必填；内部ID、偏移、审核和图视图由代码处理。后台39类不整包作为模型任务。

## 1 实体类型（节点类）

实例化规则：只有 status=core 且 criteria 非空的类型可以实例化；其余类型落到实体上只记为候选，并触发 review 档提示。

层级：类型层级暂不建立：candidates 的 unresolved 已记录电沉积/化学镀/超共形填充/CMP 可能构成上下位，但原文未明示。宁可 parent_type_id 留空，也不编造层级。

| 类型 | 名称 | 状态 | 判据/正例要点 | 未实例化原因 |
| --- | --- | --- | --- | --- |
| `t1` | 有机分子物种 | core | 提及可指称一个分子组成确定的有机化合物或其离子/盐/水合物形式；功能角色（整平剂、抑制剂、光亮剂等）不参与类型判定，作为 role_assignments 记录 | — |
| `t2` | 金属离子物种 | core | 提及写明电荷或价态（如 Co 2+、Cu2+）且处于溶液相；金属镀层、晶体、晶面不是本类型 | — |
| `t3` | 电解液/镀液 | core | 提及指称用于沉积的液体介质整体，可带组成限定；单一组分（如某添加物）不是介质整体 | — |
| `t5` | 固体表面/界面 | core | 提及指称固体材料的表面区域而非材料整体；可带材料限定（cobalt surface）或几何限定（dense crystal plane） | — |
| `t6` | 镀层/薄膜材料 | core | 提及指称沉积形成的材料层整体；厚度、组织、性质是其属性，不升为独立类型 | — |
| `t7` | 表面膜/表面吸附层 | core | 提及指称在固体表面形成的覆盖层（钝化膜、吸附层）；须与基底表面（t5）区分：膜是形成物，表面是发生面 | — |
| `t9` | 晶面（晶体学平面） | core | 提及带密勒指数且指称原子平面（plane/facet/crystalline plane）；多晶取向分布属 t12，堆垛序列属 t11，晶相属候选 t10 | — |
| `t11` | 原子层堆垛方式 | core | 提及描述原子层的周期序列（如 abc stacking）；晶面、织构、晶相不属本类型 | — |
| `t12` | 织构/择优取向 | core | 提及描述多晶取向的分布或占优取向（texture / preferred orientation）；单一晶面提及不判为 t12 | — |
| `t13` | 表面形貌/组织形态 | core | 提及指称可观察的表面几何形态或组织状态（honeycomb、stone forest 等）；尺寸参数属 t14，取向属 t12，晶面属 t9 | — |
| `t14` | 晶粒尺寸（微结构参数） | core | 提及指称晶粒尺寸这一可测量参数（grain size / 晶粒尺寸）；“晶粒细化”作为效应描述属候选 t34，不属本类型 | — |
| `t16` | 镀层纯度/成分 | core | 提及指称纯度或成分水平（purity / composition）；电阻率、形貌、织构不属本类型 | — |
| `t19` | 电化学测量量 | core | 提及指称电化学测试中的物质量（deposition potential 等）；曲线中的峰特征属候选 t20，整条曲线属候选 t21 | — |
| `t22` | 计算方法/计算分析 | core | 提及指称计算方法或计算分析（DFT、MD、interaction region indicator 等）；实验表征方法属 t23 | — |
| `t23` | 实验表征方法 | core | 提及指称实验测量手段（E-FTIR、CV 等）；计算方法属 t22 | — |
| `t29` | 沉积后热处理（退火） | core | 提及指称沉积后的热处理步骤（annealing treatment）；处理前后状态由 samples.derived_from_sample_id 表达，不写在类型里 | — |
| `t30` | CMP 后清洗步骤 | core | 提及指称 CMP 之后的清洗工序（post CMP cleaning）；CMP 工艺本体属候选 t27 | — |
| `t4` | 浆料组成（配方属性） | proposed | — | 配方属性与实体边界未定：同一组配比既可以是属性也可以是构成关系，判据未写成。 |
| `t8` | 吸附位点 | proposed | — | c-sites 原文未定义结构，无法给出可检验的实例化判据；暂不实例化。 |
| `t10` | 晶体结构/晶相 | proposed | — | 与 t11 堆垛方式、t12 织构的边界待定：hcp 既可指晶相也可指堆垛，判据未定。 |
| `t15` | 电学性质 | proposed | — | 性质值是属性还是指标节点未定；电阻率目前只作 outcomes 指标，未立实体类型。 |
| `t17` | 吸附性质/吸附强度 | proposed | — | 性质与过程（t39）边界未写成判据；且吸附强度缺统一量纲。 |
| `t18` | 材料微观性质（泛称） | proposed | — | 泛称占位类型，按定义不可实例化为确定类型；只保留为属性占位文本。 |
| `t20` | 电化学响应特征（峰） | proposed | — | 峰位/峰高/峰形是否为同一实体未定；暂只作 outcomes 指标名。 |
| `t21` | 测量曲线/测量数据对象 | proposed | — | 数据对象当前无存储层承载（未实现曲线/表格文件级锚点）。 |
| `t24` | 超共形填充工艺 | proposed | — | 与 t25 电沉积过程可能构成上下位，原文未明示，暂不建层级、不实例化。 |
| `t25` | 钴电沉积过程 | proposed | — | 过程类型需要在事实层作事件参与者；事件型实体的标识规则未定。 |
| `t26` | 化学镀钴工艺 | proposed | — | 与 t25 的边界（外电流与否）可判，但过程实体标识规则未定，暂不实例化。 |
| `t27` | 化学机械抛光工艺 | proposed | — | 过程实体标识规则未定；当前只作事实背景文本。 |
| `t28` | 集成电路制造流程（应用背景） | proposed | — | 背景性指称缺少可检验的实例化判据，易被误当研究对象。 |
| `t31` | 基底结构特征（通孔几何） | proposed | — | 通孔几何与样品（samples）的分工未定：几何是样品属性还是实体。 |
| `t32` | 工艺功能角色 | proposed | — | 角色已由 role_assignments 记录并在受控词表取值；暂不建角色实体，避免同义重复。 |
| `t33` | 浓度依赖的加速-抑制效应 | proposed | — | 效应是跨两条事实的聚合，不是单条事实里的实体；需消费层设计。 |
| `t34` | 晶粒细化效应 | proposed | — | 效应与 t14 参数的分工未写死：细化本身是变化，不是尺寸值。 |
| `t35` | 缓蚀剂去除效果 | proposed | — | 效果值缺统一指标与量纲，只能作 outcomes 指标名。 |
| `t36` | 机制假设 | proposed | — | 假设已由 facts.statement_type=author_interpretation 承载；是否需独立节点待定。 |
| `t37` | 协同效应假设（研究展望） | proposed | — | 展望性陈述由 statement_type=future_work 承载；独立节点会与模态字段重复。 |
| `t38` | 分子结构基团/官能团 | proposed | — | 基团在原文常以复合指称出现（nucleoside and adenine groups），拆分规则未定。 |
| `t39` | 吸附行为/吸附过程 | proposed | — | 过程类型作参与者的标识规则未定；当前由关系 r11 表达。 |

后台共 39 类，其中 core 17 类（有判据、可实例化），其余为 proposed（落上去只记候选）。判据均为本轮新写、`review=pending`，未做标注一致性检验。

## 2 关系签名

以投影角色决定端点；只有core且projection完整的关系可生成图边。未规范事实仍可按原文检索引用。

基数指一条事实的参与者数量上下界；超界只进 review 档，不丢记录。

| 关系 | 含义 | 状态 | 域 → 值域 | 基数 | 未实例化原因 |
| --- | --- | --- | --- | --- | --- |
| `r7` | 添加物对沉积过程、组织或性质的影响 | core | t1, t2 → t6, t9, t12, t13, t14, t15, t16, t19, t25, t26, t34 | 2–4 | — |
| `r11` | 物质吸附于固体表面（可带位点或晶面限定） | core | t1, t2 → t5, t7, t8, t9 | 2–3 | — |
| `r1` | 物质被选作或被建议用作某工艺的功能角色 | proposed | t1, t2, t3 → t32 | 2–3 | 值域 t32 目前不可实例化（见 entity_types），签名无法在真实数据上验证。 |
| `r2` | 电化学测量量发生变化 | proposed | t1, t3 → t19, t20 | 2–3 | 参照（baseline）在该关系下的统一写入方式未验证。 |
| `r3` | 电化学响应中出现新特征（峰） | proposed | t1, t3 → t20 | 2–2 | 值域类型未实例化；峰位/峰高未作为结构化结果字段。 |
| `r4` | 采用方法研究物质在固体表面的吸附行为 | proposed | t22, t23 → t39, t5 | 3–4 | 参与者顺序与“研究对象/手段/现象”三元的边展开规则未定，成对边会丢手段信息。 |
| `r5` | 计算模拟金属离子与有机分子的配位作用 | proposed | t22 → t2, t1 | 3–3 | 配位复合物是否另立类型未定，值域暂借 t1/t2。 |
| `r6` | 提出机制或因素以解释效应 | proposed | t36, t1, t2 → t33, t34, t39, t12 | 2–3 | 域或值域多数类型为候选，签名无法在真实数据上验证。 |
| `r8` | 择优取向/织构的形成或保持 | proposed | t1, t2, t6 → t12 | 2–3 | 观察层与镀层/基底的关系未统一，暂只登记织构一侧。 |
| `r9` | 材料或样品的性质测量 | core | t6, t12, t14, t16 → t14, t15, t16, t19 | 2–2 | — |
| `r10` | 热处理引起镀层性质变化 | proposed | t29 → t6, t15, t16, t13 | 2–4 | 处理步骤作为事实参与者还是条件尚未统一。 |
| `r12` | 选择性抑制或诱导堆垛生长方式 | proposed | t1, t2 → t11 | 2–3 | 极性与效应方向的双重表达未在样例上验证。 |
| `r13` | 研究结果为后续优化或研究提供依据（论述关系） | proposed | t6, t7, t19 → t28, t30 | 2–3 | 值与域都是背景性类型，判据不足，暂不实例化。 |
| `r14` | 吸附行为有利于改善后续清洗中的去除效果 | proposed | t7, t1 → t30, t35 | 2–3 | 效果值类型 t35 与清洗步骤 t30 的实例化判据未写。 |

签名检查只对已登记关系且两侧类型可判的边生效；不匹配进 review 档，保留记录不丢。

## 3 标识、合并与拆分

标识与合并规则；目标不是一次性消歧，而是让每次合并/拆分都可追溯、可撤销。别名与结构消歧本体仍暂缓。

| 记录 | ID 形式 | 说明 |
| --- | --- | --- |
| `documents` | `doc:<清洗产物文件名主干>` | 与 corpus_manifest 的 document_id 一致，不随标题改。 |
| `blocks` | `blk:<源文件块ID>` | 直接沿用清洗产物 block_id。 |
| `mentions` | `m:<语义短名> 或 m:<doc略写>:<短名>` | 篇内唯一即可；跨篇重名不构成同一性。 |
| `identities` | `identity:<document|global>:<slug>` | global 身份须有已核证据；篇内身份带 doc 前缀。 |
| `facts` | `f:<主题>:<判别后缀>` | 事实 id 不复用；条件不同的同主题事实用不同后缀。 |
| `role_assignments` | `role:<主体>:<角色>[:<条件>]` | 同事实同主体同角色只允许一条。 |
| `entities` | `ent:<mention_id>` | 物化层派生 id，不独立编辑；由事实层重建。 |
| `edges` | `edge:<fact_id>:<序号>` | 序号按 participants 顺序，保证同输入同输出。 |

- 身份只在篇内由作者显式措辞或结构证据建立；跨篇合并必须另有 reviewed 依据，不得用同名/同缩写自动合并。
- 盐型、电荷、水合物、立体化学、规格是 distinctions，任一项不同即不得合并为同一身份。
- 不把 InChIKey 或外部数据库 ID 当作全局身份的等价物；只作 external_ref 与候选依据。
- 提及与身份分离：mention 保留原文表面串，identity 才承载规范名；合并/拆分只作用于 identity。
- 任何合并必须先写 identity_merges 记录再物化：pending 的合并不改变实体指向，reviewed 的合并才影响 identities 与 entities。
- 拆分不删除旧身份：旧身份保留并标 status=unresolved，新增身份与之建立 distinct_from 记录。
- 身份 id 一经使用不复用；写错只能标 deprecated 并留映射，不重命名历史记录。
- 跨来源对齐（PubChem/ChEBI）只产生 candidate 记录；reviewed 需要人工核对并给 match_status=reviewed。

合并/拆分记录 `identity_merges`：same_as 需 review=reviewed、basis in {author_explicit, structure}、evidence 非空、两侧 identity.status=reviewed；distinct_from 需 evidence 非空。

禁止：
- basis=name_candidate 且 review=reviewed 的 same_as
- document 作用域的两个不同文献身份直接 same_as（须先取得 global 依据）
- 同一对身份同时存在 same_as 与 distinct_from
- 只改 identities.status 而不写 identity_merges 的静默合并

## 4 属性表示边界

什么存成属性、什么必须升成节点

- 需要被独立引用、独立参与关系、或被反复按名查询的对象，升成节点（entities/mentions）。
- 浓度、温度、时间、用量等带单位与归属的量，作为条件的结构化属性（conditions[].value），不升节点。
- 指标值（电阻率、晶粒尺寸、纯度等）作为 outcomes 的结构化属性；一旦要跨实验比较，必须先值化：value_kind=numeric + unit_status=reported。
- 无法值化的量保留原串并标定性/缺失，不造占位数值。
- 角色不是节点，是事实内的受控多选取值（role_assignments），因为角色随条件变化。
- 属性要升节点必须给出理由：会被独立引用/参与关系/反复查询；否则一律留作属性。

## 5 受控词表与晋升

封闭取值（与 `schema/records.schema.json` 的枚举逐项一致，测试会核对）：

| 字段 | 取值 |
| --- | --- |
| `fact.statement_type` | observation / calculation_result / author_interpretation / future_work / reported_claim / unknown |
| `fact.source_scope` | this_study / cited_study / review_summary / unknown |
| `fact.polarity` | asserted / negated / no_effect / unknown |
| `fact.modality` | explicit / hedged / speculative / unknown |
| `outcome.direction` | increase / decrease / no_effect / mixed / unknown |
| `outcome.magnitude.qualifier` | slight / moderate / marked / unknown |
| `outcome.comparison.status` | not_stated / raw_only / explicit |
| `quantity.value_kind` | numeric / qualitative / ordinal / absent |
| `quantity.unit_status` | reported / not_reported / not_applicable / unresolved |
| `identity.status` | unresolved / candidate / reviewed |
| `identity_merge.relation` | same_as / distinct_from |
| `identity_merge.basis` | author_explicit / structure / database / name_candidate |
| `review` | pending / reviewed |

功能角色（`role_assignments.functional_role`）：

| 选项 | 中文 | 定义 |
| --- | --- | --- |
| `accelerator` | 加速剂 | 原文或实验结果指明其促进沉积、填充或相关指标的作用方向 |
| `suppressor` | 抑制剂 | 原文或实验结果指明其抑制沉积、填充或相关指标的作用方向 |
| `leveler` | 整平剂 | 原文明确以整平为功能定位 |
| `carrier` | 载体类功能角色 | 原文明确以 carrier/载体作为功能性角色；不因它是主介质就自动选中 |
| `brightener` | 光亮剂 | 原文明确以光亮或晶粒细化等表面外观功能定位 |
| `other` | 其他已明确角色 | 原文明确给出角色，但不在上述清单；必须保留role_raw |
| `unknown` | 无法判断 | 证据不足或原文未说明角色；不得与已确定选项混填 |

| 指标 | 中文 | 家族 | 状态 | 单位提示 |
| --- | --- | --- | --- | --- |
| `resistivity` | 电阻率 | electric_property | approved | μΩ·cm |
| `surface_morphology` | 表面形貌 | microstructure | approved | — |
| `texture` | 织构/择优取向 | microstructure | approved | — |
| `grain_size` | 晶粒尺寸 | microstructure | approved | nm |
| `purity` | 纯度 | composition | approved | — |
| `deposition_potential` | 沉积电位 | electrochemical_quantity | approved | mV |
| `stripping_peak` | 溶出峰 | electrochemical_quantity | proposed | mV |
| `thickness` | 厚度 | microstructure | proposed | nm |
| `roughness` | 粗糙度 | microstructure | proposed | nm |

| 参数 | 中文 | 家族 | 状态 | 是否升实体 |
| --- | --- | --- | --- | --- |
| `concentration` | 浓度 | process_condition | approved | 否 |
| `amount_of_additive` | 添加物用量 | process_condition | approved | 否 |
| `temperature` | 温度 | process_condition | approved | 否 |
| `duration` | 时间 | process_condition | proposed | 否 |
| `pH` | pH | process_condition | proposed | 否 |
| `current_density` | 电流密度 | process_condition | proposed | 否 |
| `agitation` | 搅拌/流场 | process_condition | proposed | 否 |

| 单位原文 | 量纲 | 状态 | 标准 |
| --- | --- | --- | --- |
| `mg·L–1` | concentration | approved | QUDT（term=null, unchecked） |
| `μΩ·cm` | resistivity | approved | QUDT（term=null, unchecked） |
| `°C` | temperature | approved | QUDT（term=null, unchecked） |
| `min` | time | approved | QUDT（term=null, unchecked） |
| `mV` | potential | proposed | QUDT（term=null, unchecked） |
| `A·dm–2` | current_density | proposed | QUDT（term=null, unchecked） |
| `nm` | length | proposed | QUDT（term=null, unchecked） |

晋升：candidate / proposed / approved / deprecated。

- candidate/proposed/approved/deprecated管理术语映射，不管理文献结论强弱。
- 单篇明确原文与清楚定义即可支持登记；无统一至少两篇门槛。
- 晋升或合并仍须记录依据并保留旧id；多来源代表支持广度，不自动代表真值。
- 别名只用于召回；身份合并另按identity_rules执行。

别名用于召回提示，不构成同一性；别名跨篇不复用，除非 identity 已 reviewed。

## 6 约束与三档处置

| 档 | 含义 | 执行点 | 效果 |
| --- | --- | --- | --- |
| **block** | 入库拒绝 | ingest | 记录不进入可用集合；说明结构与出处自相矛盾，或会造成不可撤销的错误合并。 |
| **review** | 保留待审 | review | 记录保留，提示针对性核查；不因pending或未规范统一禁止引用/分析，具体用途由consumer_contract判断。 |
| **warn** | 事后统计 | audit | 只报告，不改变记录资格；用于质量与覆盖统计。 |

一个错误码只能属于一档。结构/引用/出处矛盾进 block；语义可疑但可保留进 review；覆盖与抽样提示进 warn。降档必须同时改本文件与测试，不能只在代码里放宽。

| 约束 | 类别 | 档 | 陈述 |
| --- | --- | --- | --- |
| `C1-evidence-literal` | structure | block | 所有引用必须在来源块或表格单元格中逐字命中；提及表面串必须等于其引文。 |
| `C2-referential-integrity` | structure | block | 所有外键指向的记录必须存在、同文献、且唯一；参与者/条件归属/角色主体必须在事实内闭合。 |
| `C3-quantity-state` | semantic | block | 取值形态与取值/单位状态必须自洽：数值型须有原值，缺失型不得带原值，未报告单位不得有单位串。 |
| `C4-identity-safety` | semantic | block | 跨篇/全局同一性必须有已核证据；仅名称相似不得 reviewed；合并记录不得自相矛盾。 |
| `C5-inheritance` | semantic | block | 标记为继承的条件必须能在所属 Run 找到同名参数且取值一致。 |
| `C6-graph-derivation` | structure | block | 物化层必须由记录层派生：实体指向存在的提及，边指向存在的事实与实体，边不得改写事实的陈述性质、极性、模态、条件或证据。 |
| `C7-role-completeness` | semantic | review | 选择了角色就应有支撑：other/author_explicit 须有原文措辞，角色与依据不得互相矛盾。 |
| `C8-role-candidacy` | semantic | review | 仅由效果反推的角色、未逐字出现在证据中的角色措辞，只能作候选。 |
| `C9-open-vocab` | semantic | review | 未登记类型/关系保留供检索，不能自动作为规范图断言；不禁止原文概括。 |
| `C10-context-and-provenance` | semantic | review | 程度限定、比较基准、转述目标必须显式：程度非 unknown 时须有原串，比较状态非 not_stated 时须有基准，转述须能指向被引目标。 |
| `C11-magnitude-baseline` | structure | block | 程度与比较基准的字段不能自相矛盾：有程度必有原串，有基准状态必有基准串，基准提及必须存在。 |
| `C12-coverage-audit` | semantic | warn | 覆盖与抽样提示：未定类型的实体、缺边的事实、未核页码、缺表格 CSV、待核身份、条件值未逐字出现、角色绑定未来工作或缺条件。 |
| `C13-catalog-selfcheck` | structure | block | 校验器产生的每个错误码都必须在本目录中登记档位；未登记的码按 block 处理并报错。 |

复杂度预算（`scripts/check_budget.py` 超限即失败）：

| 指标 | 上限 |
| --- | --- |
| max_entity_types | 60 |
| max_core_entity_types | 24 |
| max_relations | 30 |
| max_record_types | 20 |
| max_top_level_fields | 20 |
| max_fields_per_record | 30 |
| max_defs | 24 |
| max_error_codes | 120 |
| max_registry_files | 12 |
| max_doc_sections | 14 |

## 7 上下文与 n-ary

一条 `facts` 是有来源的文献陈述（参与者＋条件＋结果＋陈述性质），不等同于一次实际实验，只有已登记且角色签名明确的关系生成 `edges` 视图；端点方向由角色决定。条件挂在事实上，用 `about_mention_ids` 指明作用对象；需要限定到具体测量的，用 `outcomes`。

程度限定（`outcome.magnitude`）：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `raw` | string | null | 是 | 程度原措辞；qualifier 非 unknown 时必填 |
| `qualifier` | 枚举（slight / moderate / marked / unknown） | 是 | 程度档：slight / moderate / marked / unknown |

比较基准（`outcome.comparison`）：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `status` | 枚举（not_stated / raw_only / explicit） | 是 | 比较基准状态：not_stated（未给）/ raw_only（只有文字）/ explicit（有数值） |
| `baseline_raw` | string | null | 是 | 基准值原文（如退火前的 14.4 μΩ·cm） |
| `baseline_mention_id` | string | null | 是 | 基准提及；须为本事实参与者 |
| `basis_raw` | string | null | 是 | 基准口径原文（未给出时为 null） |
| `evidence` | array[→ evidence] | 否 | 证据：块内偏移或表格单元格 |

边不得自带新语义：`qualifiers` 与 `evidence`、`review` 必须与来源事实完全一致，不一致即 block（`EDGE_SEMANTICS_DRIFT`）。

## 8 溯源与可信度

| 维度 | 字段 | 说明 |
| --- | --- | --- |
| 来源文档 | `documents.sha256 / blocks.text` | 引用必须逐字命中块内片段或表格单元格 |
| 陈述性质 | `facts.statement_type` | 观测/计算结果/作者解释/未来工作/转述/未知 |
| 来源范围 | `facts.source_scope` | 本研究/引用他人/综述归纳/未知 |
| 肯定与否定 | `facts.polarity` | 含 negated / no_effect，不把“无效应”写成缺失 |
| 语气 | `facts.modality` | explicit / hedged / speculative / unknown |
| 转述目标 | `facts.cited_work` | 指称＋可解析文献；未转述时显式 null |
| 抽取方式 | `facts.extraction` | 方法/模型/协议版本，规则映射时 model=null |
| 未报告 | `value_kind=absent / unit_status=not_reported` | 用状态表示缺失，不用空值或占位串 |
| 不确定 | `value_kind=qualitative / magnitude=unknown / comparison=not_stated` | 不确定本身可被查询 |

pending仅代表尚未人工审核，不自动禁止引用或候选分析；具体数值操作另核对对象、单位与口径。

## 9 演化与治理

- 版本号：`schema_version` 为 `4.0.0-draft`；改契约同时改 `$id` 与 `schema_version`，旧记录先迁移再入库。

- 迁移：只增字段先发新 schema 版本；删除/改名必须走 `deprecated` 状态并保留映射，不重命名历史 id。
- 晋升：候选只能在 `vocab.promotion` 的四个状态间前进，晋升需依据（原文偏移或核验记录），只改 status 不算晋升。
- 预算：任何一项超预算必须先删/并，再增加；复杂度只能靠删减换。；超预算先删再增。
- 审计：`scripts/check_budget.py` 查预算与档位；`tests/` 查枚举一致性、档位覆盖、物化确定性；`scripts/render_schema.py` 保证文档与实现同步。
- 命名：按 `registry/identity_rules.json` 的 id_scheme；物化 id 一律派生，不手工编辑。

## 消费端契约

检索键（`scripts/materialize.py` 的 `retrieval_keys()` 生成）：

| 键 | 来源 | 说明 |
| --- | --- | --- |
| `entity` | entities.id / edges.from_entity_id | 起点实体（由 mention 物化，id=ent:<mention_id>） |
| `entity_type` | entities.type_id | 实体类型；null 表示未定类型，不可用于类型过滤后的断言 |
| `identity` | entities.identity_id | 已核身份；pending 合并不写入 |
| `relation` | edges.relation.candidate_relation_id | 关系编号；null/未登记表示开放候选 |
| `indicator` | facts.outcomes[].indicator_raw / edges.qualifiers | 结果指标名 |
| `parameter` | facts.conditions[].parameter_raw | 条件参数名 |
| `sample` | facts.outcomes[].sample_id | 结果归属样品（处理前后由此区分） |
| `document` | documents.id | 来源文献 |
| `statement` | facts.statement_type + source_scope | 陈述性质，用于区分观测/解释/展望/转述 |
| `review` | facts.review / edges.review | 人工核验状态 |

按用途独立判断：

| 用途 | 规则 |
| --- | --- |
| cite | 来源可定位且无block即可提供事实及原文；pending/开放关系本身不阻止引用。 |
| numeric_comparison | 按本次对象、指标、数值、单位、条件与基准分别核对；绝对值无需比较基准，百分比变化需要基准。 |
| candidate_advice | 允许文献依据加模型知识提出待验证候选，包括库外类比；不得冒充已报告有效性。 |
| mechanism_analysis | 允许作者解释、模型背景知识与助手推断；正文自然区分依据，不逐句贴治理标签。 |
## 复用成熟标准

只借字段语义，不引入整本体；未离线核对的术语一律留 null，不编造 IRI。

| 标准 | 用到部分 | 我们的字段 | 状态 |
| --- | --- | --- | --- |
| PROV-O | Entity / Activity / wasGeneratedBy / wasDerivedFrom | `documents`, `blocks`, `facts.extraction`, `facts.evidence` | mapped_partial |
| SOSA | Observation / observedProperty / hasResult / madeBySensor | `facts.outcomes`, `value_kind`, `unit_status`, `facts.statement_type` | mapped_partial |
| QUDT | Unit / QuantityKind | `quantity.unit_raw`, `quantity.unit_status`, `registry/vocab.json units` | unchecked |
| ChEBI | Molecule / Class | `identities.external_refs`, `external_records` | deferred |
| PubChem | CID / InChIKey | `external_records`, `identity_links.basis=database` | deferred |

先复用成熟标准的字段语义，再考虑自建；自建部分必须在 entity_types/relations/vocab 里给出判据与候选状态，否则视为未完成。

## 记录定义

| 记录 | 说明 | 必填 |
| --- | --- | --- |
| `documents` | L0 文献 | 是 |
| `blocks` | L0 文本块（表格/图/公式以此定位） | 是 |
| `mentions` | L3 原文提及（保留表面串） | 是 |
| `identities` | L3 规范身份（篇内或跨篇） | 否 |
| `identity_links` | L3 提及→身份映射及其依据 | 否 |
| `identity_merges` | L3 身份合并/拆分/拒并记录 | 否 |
| `external_records` | 外部资源查询缓存记录 | 否 |
| `facts` | L2/L4 事实（事件实体：参与者＋条件＋结果＋陈述性质） | 是 |
| `experiments` | L2 实验系列 | 否 |
| `runs` | L2 一次条件组合 | 否 |
| `samples` | L3 样品与处理前后状态 | 否 |
| `role_assignments` | L2 功能角色选择（受控多选） | 否 |
| `entities` | 物化层实体（由 mention 派生，id=ent:<mention_id>） | 否 |
| `edges` | 物化层边（由事实派生，边不新增语义） | 否 |

### `documents`（`$defs/document`）

L0 文献

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 记录唯一标识 |
| `title` | string | 是 | 文献标题 |
| `source_file` | string | 是 | 清洗产物中的块文件路径 |
| `sha256` | string | 是 | 来源文件哈希，用于追溯快照 |
| `source_kind` | 枚举（cleaned_text / original_pdf / other） | 是 | 来源类型：cleaned_text / original_pdf / other |

### `blocks`（`$defs/block`）

L0 文本块（表格/图/公式以此定位）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 记录唯一标识 |
| `document_id` | string | 是 | 所属文献；跨文献引用视为错误 |
| `page` | integer | null | 是 | 页码；未知时为 null 并告警 |
| `section` | string | null | 是 | 章节标题原文 |
| `text` | string | 是 | 块正文，引用必须逐字取自这里 |

### `mentions`（`$defs/mention`）

L3 原文提及（保留表面串）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 记录唯一标识 |
| `document_id` | string | 是 | 所属文献；跨文献引用视为错误 |
| `surface` | string | 是 | 原文提及的字面写法 |
| `evidence` | → evidence | 是 | 证据：块内偏移或表格单元格 |
| `candidate_type_ids` | array[string] | 否 | 候选类型编号；未登记类型只进候选 |

### `identities`（`$defs/identity`）

L3 规范身份（篇内或跨篇）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 记录唯一标识 |
| `canonical_label` | string | 是 | 规范名称（篇内或全局） |
| `scope` | 枚举（document / global） | 是 | 身份作用域：document（篇内）或 global（跨篇） |
| `document_id` | string | null | 是 | 所属文献；跨文献引用视为错误 |
| `status` | 枚举（unresolved / candidate / reviewed） | 是 | 身份核验状态：unresolved / candidate / reviewed |
| `external_refs` | array[string] | 是 | 关联的外部记录编号 |
| `distinctions` | object | 是 | 电荷/盐型/水合物/立体化学/规格等不可合并差别 |

### `identity_links`（`$defs/identity_link`）

L3 提及→身份映射及其依据

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `mention_id` | string | 是 | 指向的原文提及 |
| `identity_id` | string | 是 | 指向的规范身份 |
| `basis` | 枚举（author_explicit / structure / database / name_candidate） | 是 | 依据：作者明确/结构/数据库/仅名称候选 |
| `review` | 枚举（pending / reviewed） | 是 | 后台人工审核状态；pending不自动禁止引用/分析 |
| `evidence` | array[→ evidence] | 是 | 证据：块内偏移或表格单元格 |
| `external_ref` | string | null | 是 | 引用的外部记录 |

### `identity_merges`（`$defs/identity_merge`）

L3 身份合并/拆分/拒并记录

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 记录唯一标识 |
| `from_identity_id` | string | 是 | 合并/拆分记录的起点身份 |
| `to_identity_id` | string | 是 | 合并/拆分记录的终点身份 |
| `relation` | 枚举（same_as / distinct_from） | 是 | 同一性操作：same_as（合并）或 distinct_from（拆分/拒并） |
| `basis` | 枚举（author_explicit / structure / database / name_candidate） | 是 | 依据：作者明确/结构/数据库/仅名称候选 |
| `review` | 枚举（pending / reviewed） | 是 | 后台人工审核状态；pending不自动禁止引用/分析 |
| `evidence` | array[→ evidence] | 是 | 证据：块内偏移或表格单元格 |
| `rationale` | string | 是 | 合并或拒并的理由（必填，供审计） |
| `note` | string | null | 是 | 单条记录备注 |

### `external_records`（`$defs/external`）

外部资源查询缓存记录

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 记录唯一标识 |
| `resource` | string | 是 | 外部资源名（pubchem/chebi 等） |
| `resource_id` | string | 是 | 外部资源标识 |
| `retrieved_at` | string | 是 | 查询时间 |
| `response_sha256` | string | 是 | 缓存响应哈希 |
| `cache_file` | string | 是 | 缓存文件位置 |
| `match_status` | 枚举（candidate / reviewed） | 是 | 外部匹配状态 |
| `identity_basis` | string | 是 | 匹配依据说明 |

### `facts`（`$defs/fact`）

L2/L4 事实（事件实体：参与者＋条件＋结果＋陈述性质）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 记录唯一标识 |
| `document_id` | string | 是 | 所属文献；跨文献引用视为错误 |
| `group_id` | string | null | 否 | 同一研究的记录分组；不能代替 Run |
| `relation` | → relation_ref | 是 | 关系：原始表达＋定义＋候选编号 |
| `participants` | array[object] | 是 | 参与者：提及＋语义角色 |
| `conditions` | array[→ condition] | 否 | 条件；可标记从 Run 继承 |
| `outcomes` | array[→ outcome] | 否 | 结果；可绑定样品 |
| `cited_work` | object | 否 | 转述对象：原文指称＋可解析到的文献；未转述时三字段均为 null |
| `statement_type` | 枚举（observation / calculation_result / author_interpretation / future_work / reported_claim / unknown） | 是 | 陈述性质：观察/计算/作者解释/未来工作/转述/未知 |
| `source_scope` | 枚举（this_study / cited_study / review_summary / unknown） | 否 | 来源范围：本研究/引用他人/综述归纳/未知 |
| `polarity` | 枚举（asserted / negated / no_effect / unknown） | 否 | 肯定/否定/无效应/未知 |
| `modality` | 枚举（explicit / hedged / speculative / unknown） | 否 | 语气：明确/保留/推测/未知 |
| `evidence` | array[→ evidence] | 是 | 证据：块内偏移或表格单元格 |
| `review` | 枚举（pending / reviewed） | 否 | 后台人工审核状态；pending不自动禁止引用/分析 |
| `extraction` | object | 否 | 抽取方法、模型与协议版本 |
| `notes` | array[string] | 否 | 人工备注，不参与校验 |
| `run_id` | string | null | 否 | 所属 Run；继承条件时必填 |

### `experiments`（`$defs/experiment`）

L2 实验系列

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 记录唯一标识 |
| `document_id` | string | 是 | 所属文献；跨文献引用视为错误 |
| `label` | string | 是 | 原文标签或简述 |
| `shared_note` | string | null | 是 | 系列共享条件说明（自由文本，不参与求交） |
| `evidence` | array[→ evidence] | 是 | 证据：块内偏移或表格单元格 |

### `runs`（`$defs/run`）

L2 一次条件组合

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 记录唯一标识 |
| `document_id` | string | 是 | 所属文献；跨文献引用视为错误 |
| `experiment_id` | string | null | 是 | 所属实验系列 |
| `label` | string | 是 | 原文标签或简述 |
| `conditions` | array[→ quantity_condition] | 是 | 条件；可标记从 Run 继承 |
| `evidence` | array[→ evidence] | 是 | 证据：块内偏移或表格单元格 |

### `samples`（`$defs/sample`）

L3 样品与处理前后状态

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 记录唯一标识 |
| `document_id` | string | 是 | 所属文献；跨文献引用视为错误 |
| `label` | string | 是 | 原文标签或简述 |
| `material_raw` | string | null | 是 | 材料原文 |
| `form_raw` | string | null | 是 | 形态原文（膜/粉/基底） |
| `state_raw` | string | null | 是 | 状态原文（镀态/退火态） |
| `treatment_raw` | string | null | 是 | 处理原文 |
| `derived_from_sample_id` | string | null | 是 | 来源样品，用于表达处理前后 |
| `evidence` | array[→ evidence] | 是 | 证据：块内偏移或表格单元格 |

### `role_assignments`（`$defs/role_assignment`）

L2 功能角色选择（受控多选）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 记录唯一标识 |
| `fact_id` | string | 是 | 所属事实 |
| `subject_mention_id` | string | 是 | 角色归属的物质提及 |
| `functional_role` | 枚举（accelerator / suppressor / leveler / carrier / brightener / other / unknown） | 是 | 功能角色（受控多选之一） |
| `role_raw` | string | null | 是 | 原文角色措辞；other 与 author_explicit 必填 |
| `role_basis` | 枚举（author_explicit / effect_inference / unknown） | 是 | 角色依据：作者明确/效果推测/未知 |
| `evidence` | array[→ evidence] | 是 | 证据：块内偏移或表格单元格 |
| `note` | string | null | 是 | 单条记录备注 |

### `entities`（`$defs/entity`）

物化层实体（由 mention 派生，id=ent:<mention_id>）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 记录唯一标识 |
| `document_id` | string | 是 | 所属文献；跨文献引用视为错误 |
| `label` | string | 是 | 原文标签或简述 |
| `type_id` | string | null | 是 | 实体类型；null 表示未定类型，会触发 audit 提示 |
| `identity_id` | string | null | 是 | 已核身份；pending 合并不写入 |
| `from_mention_id` | string | 是 | 实体来源提及 |
| `evidence` | array[→ evidence] | 是 | 证据：块内偏移或表格单元格 |

### `edges`（`$defs/edge`）

物化层边（由事实派生，边不新增语义）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 记录唯一标识 |
| `fact_id` | string | 是 | 所属事实 |
| `from_entity_id` | string | 是 | 边起点实体 |
| `to_entity_id` | string | 是 | 边终点实体 |
| `relation` | → relation_ref | 是 | 关系：原始表达＋定义＋候选编号 |
| `qualifiers` | object | 是 | 边的限定：陈述性质/来源范围/极性/模态/条件，全部复制自事实 |
| `evidence` | array[→ evidence] | 是 | 证据：块内偏移或表格单元格 |
| `review` | 枚举（pending / reviewed） | 是 | 后台人工审核状态；pending不自动禁止引用/分析 |

### 嵌套记录

**`evidence`**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `kind` | 枚举（block / table_cell） | 是 | 证据类型：block 或 table_cell |
| `block_id` | string | 否 |  |
| `start` | integer | 否 | 引用起始偏移（含） |
| `end` | integer | 否 | 引用结束偏移（不含） |
| `quote` | string | 否 | 逐字引文；必须等于块内对应片段 |
| `table_id` | string | 否 | 表格标识，须以 doc_id 开头 |
| `row` | integer | 否 | 表格行号（0 起，表头计入） |
| `col` | integer | 否 | 表格列号（0 起） |
| `cell_raw` | string | 否 | 单元格原文；必须与该 CSV 单元格完全一致 |

**`quantity`**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `value_raw` | string | null | 是 | 原始取值文本；数值型须逐字出现在证据中 |
| `value_kind` | 枚举（numeric / qualitative / ordinal / absent） | 是 | 取值形态：数值/定性/序数/缺失 |
| `unit_raw` | string | null | 否 | 原始单位文本 |
| `unit_status` | 枚举（reported / not_reported / not_applicable / unresolved） | 否 | 单位状态：已报告/未报告/不适用/未解析 |

**`relation_ref`**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `raw` | string | 是 | 原文表达 |
| `definition` | string | null | 否 | 关系定义 |
| `candidate_relation_id` | string | null | 否 | 候选关系编号；未登记只作候选 |

**`magnitude`**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `raw` | string | null | 是 | 程度原措辞；qualifier 非 unknown 时必填 |
| `qualifier` | 枚举（slight / moderate / marked / unknown） | 是 | 程度档：slight / moderate / marked / unknown |

**`comparison`**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `status` | 枚举（not_stated / raw_only / explicit） | 是 | 比较基准状态：not_stated（未给）/ raw_only（只有文字）/ explicit（有数值） |
| `baseline_raw` | string | null | 是 | 基准值原文（如退火前的 14.4 μΩ·cm） |
| `baseline_mention_id` | string | null | 是 | 基准提及；须为本事实参与者 |
| `basis_raw` | string | null | 是 | 基准口径原文（未给出时为 null） |
| `evidence` | array[→ evidence] | 否 | 证据：块内偏移或表格单元格 |

**`condition`**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `parameter_raw` | string | 是 | 条件参数的原文写法 |
| `candidate_parameter` | string | null | 否 | 候选参数编号；未登记只作候选 |
| `about_mention_ids` | array[string] | 是 | 条件作用对象 |
| `value` | → quantity | 是 | 数值或定性取值对象 |
| `scope_status` | 枚举（explicit / pending） | 否 | 条件作用范围是否已明确 |
| `evidence` | array[→ evidence] | 是 | 证据：块内偏移或表格单元格 |
| `inherited` | boolean | 否 | 条件是否来自 Run 继承 |

**`outcome`**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `indicator_raw` | string | 是 | 指标原文 |
| `value` | → quantity | 是 | 数值或定性取值对象 |
| `direction` | 枚举（increase / decrease / no_effect / mixed / unknown） | 否 | 变化方向；unknown 表示原文未给方向 |
| `stage_raw` | string | null | 否 | 处理阶段原文（如退火后） |
| `magnitude` | → magnitude | 否 | 程度限定：原措辞＋slight/moderate/marked/unknown |
| `comparison` | → comparison | 否 | 比较基准：状态＋基准值/基准提及/基准口径 |
| `evidence` | array[→ evidence] | 是 | 证据：块内偏移或表格单元格 |
| `sample_id` | string | null | 否 | 结果所属样品 |

**`quantity_condition`**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `parameter_raw` | string | 是 | 条件参数的原文写法 |
| `value` | → quantity | 是 | 数值或定性取值对象 |
| `evidence` | array[→ evidence] | 是 | 证据：块内偏移或表格单元格 |

**`entity`**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 记录唯一标识 |
| `document_id` | string | 是 | 所属文献；跨文献引用视为错误 |
| `label` | string | 是 | 原文标签或简述 |
| `type_id` | string | null | 是 | 实体类型；null 表示未定类型，会触发 audit 提示 |
| `identity_id` | string | null | 是 | 已核身份；pending 合并不写入 |
| `from_mention_id` | string | 是 | 实体来源提及 |
| `evidence` | array[→ evidence] | 是 | 证据：块内偏移或表格单元格 |

**`edge`**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 记录唯一标识 |
| `fact_id` | string | 是 | 所属事实 |
| `from_entity_id` | string | 是 | 边起点实体 |
| `to_entity_id` | string | 是 | 边终点实体 |
| `relation` | → relation_ref | 是 | 关系：原始表达＋定义＋候选编号 |
| `qualifiers` | object | 是 | 边的限定：陈述性质/来源范围/极性/模态/条件，全部复制自事实 |
| `evidence` | array[→ evidence] | 是 | 证据：块内偏移或表格单元格 |
| `review` | 枚举（pending / reviewed） | 是 | 后台人工审核状态；pending不自动禁止引用/分析 |

**`identity_merge`**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 记录唯一标识 |
| `from_identity_id` | string | 是 | 合并/拆分记录的起点身份 |
| `to_identity_id` | string | 是 | 合并/拆分记录的终点身份 |
| `relation` | 枚举（same_as / distinct_from） | 是 | 同一性操作：same_as（合并）或 distinct_from（拆分/拒并） |
| `basis` | 枚举（author_explicit / structure / database / name_candidate） | 是 | 依据：作者明确/结构/数据库/仅名称候选 |
| `review` | 枚举（pending / reviewed） | 是 | 后台人工审核状态；pending不自动禁止引用/分析 |
| `evidence` | array[→ evidence] | 是 | 证据：块内偏移或表格单元格 |
| `rationale` | string | 是 | 合并或拒并的理由（必填，供审计） |
| `note` | string | null | 是 | 单条记录备注 |

## 未实现与已知限制

- 冲突、共识、推荐窗口等聚合层：属消费层，尚未实现。
- 别名与结构消歧、外部库合并：按用户要求暂缓；`identities` 仅为候选，不用 InChIKey 冒充全局身份。
- 单位只保留原文串与状态，未做换算；QUDT 局部名未核对。
- 全库事实抽取、抽取准确率、问答效果：未做，不做准确率承诺。
- 多级表头与脚注的条件继承仍需抽取侧处理，本协议只校验单元格取值。
