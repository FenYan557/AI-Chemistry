# 文献事实记录协议 v4：添加剂候选选择与机理分析

当前版本：`4.0.0-draft`。面向几十篇起步的电镀专题文献库，按较便宜模型的能力下限设计。主要用途是候选选择与机理分析，允许结合文献证据和模型知识提出合理推断及库外类比候选。

## 从哪里看

- **模型抽取契约**：[`schema/extraction.schema.json`](schema/extraction.schema.json)——每条事实只有4个必填字段。
- **内部记录契约**：[`schema/records.schema.json`](schema/records.schema.json)；[可读schema](schema/schema.md)按原有九项导航生成。
- **回答契约**：[`registry/consumer_contract.json`](registry/consumer_contract.json)，引用、比较、机理分析、候选建议分别判断。
- **不看代码的完整讲解**：[`docs/本schema文字详解.md`](docs/本schema文字详解.md)，逐项解释39种类型、14种关系及完整事实结构。
- **与邻近旧版v1.1的对照**：[`docs/新旧版本区别与优势.md`](docs/新旧版本区别与优势.md)，说明适合当前项目的优势及取舍。
- **实现及验收说明**：[`docs/v4重建说明.md`](docs/v4重建说明.md)。
- **最新状态**：[`docs/MASTER.md`](docs/MASTER.md)。已完成计划、早期草稿和旧试跑见[归档](归档/README.md)。

## Schema 是什么、包含什么

Schema 规定知识图谱中**存什么、怎么连接、如何表达，以及需要满足哪些规则**。它不只是实体和关系清单，也包括属性、上下文、证据与数据约束。

| 内容 | 要说明的问题 | 本项目的落点 |
| --- | --- | --- |
| 实体类型 | 有哪些对象，如添加剂、镀液、镀层、实验 | `registry/entity_types.json`，记录中的mentions、samples、experiments等 |
| 关系类型 | 对象如何关联，如影响、吸附、测量 | `registry/relations.json`，facts中的relation与participants |
| 属性定义 | 名称、浓度、温度、电阻率等怎样记录，数据类型和单位是什么 | `schema/records.schema.json`中的属性、condition、outcome与quantity |
| 关系约束 | 谁能连接谁、方向如何确定、允许几个参与者 | 关系登记表中的域/值域、角色投影与基数 |
| 上下文 | 结论在哪个体系、条件和处理阶段下成立 | conditions、run_id、sample_id、stage_raw及比较基准 |
| 标识与命名 | ID怎么生成，别名如何保存，哪些对象可以合并 | `registry/identity_rules.json`，mentions与identities分开 |
| 来源与证据 | 来自哪篇文献、哪段原文，属于观测还是解释 | documents、blocks、evidence、statement_type；助手推断留在回答阶段 |
| 词表与校验 | 角色、指标如何统一，怎样发现引用不存在或单位状态矛盾 | `registry/vocab.json`、`registry/roles.json`、`schema/constraints.json`与校验脚本 |
| 扩展与版本 | 新类型/关系如何加入，旧记录如何兼容 | schema_version、候选登记与显式v3/v4迁移 |

## 实际保存的是不是全是三元组

当前保存的是**结构化事实记录＋派生图**，并非所有内容都转换成三元组。实体之间的规范关系可以理解为“实体—关系—实体”；名称、数值、单位等是属性；条件、结果、基准、实验上下文和证据主要是事实中的嵌套记录或引用。

例如，一条事实可以同时保存“被测对象是钴膜、糖精用量3 mg/L、退火后电阻率10.7 μΩ·cm、基准14.4 μΩ·cm及对应原文”。这些信息不需要全部各建一个节点。图边回指事实，读取完整条件和结果。

这采用了已有的事实中心、多元关系与属性图建模思路，不是新发明的知识图谱结构。也可以另行展开成三元组，但当前优先控制节点膨胀和抽取负担。具体记录集合和边界见[文字详解](docs/本schema文字详解.md)。

## 构建前需要准备什么

- **明确用途**：本项目优先服务添加剂候选选择与机理分析，用途决定结构取舍。
- **代表性材料**：准备真实文献、表格和典型事实，覆盖浓度依赖、前后处理、机理解释等情况。
- **具体查询问题**：例如“哪类添加剂值得优先验证”“低/高浓度为何作用不同”，检查schema能否提供所需信息。
- **工程约束**：明确文献规模、模型能力下限、人工维护量和成本。当前按小型专题库及较便宜模型设计。

## 构建与使用时注意什么

- **够用即可**：不追求类型多、字段全；新增结构应解决真实表达或查询问题。
- **分清实体、属性和角色**：避免同一内容重复建模；物质在某条件下的功能不能变成永久标签。
- **保住关键条件与证据**：不能为了精简把浓度、体系、阶段或原文出处丢掉，也不能把局部结果当成普遍规律。
- **允许未知、缺失和新关系**：不强迫模型猜测；区分“记录未提供”“文献未报告”和“研究发现无效应”。
- **按模型能力拆分任务**：让模型做短小、明确的抽取，代码承担ID、偏移、校验和图投影；模型背景知识与文献实证分开。
- **用真实例子验证**：检查能否正确表达和回答问题；格式校验通过不代表事实或化学结论正确。
- **区分后台与回答**：内部审核、候选治理信息不必全部进入正文；回答保留必要依据和适用条件，避免重复防御性说明。

## 模型只做小任务

模型输出单块中的字面内容，不输出ID、偏移、身份、审核状态、置信分数或图边。每条事实必填：

| 字段 | 含义 |
| --- | --- |
| `subject` | 作用物质或测量对象的原文字面 |
| `relation` | effect / adsorption / measurement / mechanism / future_work / other |
| `statement` | 观测、计算相关结果、作者解释、后续研究、报告陈述或未知 |
| `quote` | 完整原文引句，尽量包含subject及target |

按需要附target、条件与结果。低/高浓度作用不同应拆开，观测与作者解释应拆开。不能定位的重复引句返回具体错误，补充唯一上下文后再导入，不静默取第一个出现位置。

代码负责生成ID、查找偏移、补内部默认字段、映射关系、校验来源并派生图视图。`scripts/extraction.py`提供prompt生成与导入接口；没有内建任何特定供应商模型。

## 什么被简化，什么保留

- 内部事实必填缩为6项（id/document_id/relation/participants/statement_type/evidence），其余通过可选字段与代码默认值处理。模型实际只看到上面的4项精简契约。
- 后台39类细类型与14种候选关系保留兼容，不整包注入模型。类型分成9个后台组织组；模型不被要求从39类逐项选型。
- 当前启用r7作用、r11吸附、r9测量三类关系；只有角色签名支持的事实生成边，测量若只有单个对象也不强凑图边。其他陈述原样保留并支持事实级检索。
- 参与者顺序不决定图方向。多个候选或proposed类型不自动取首项作为确定类型。
- 数值、基准、样品、Run、方法和处理阶段按需要展开。文献中报告的关键条件不能为了精简丢弃；低频也不单独构成删除依据。
- 省略字段只代表当前记录未提供，不能据此断言文献未报告。`absent/not_reported`只用于明确核查后的缺失状态。
- 单篇结果、pending或未规范关系可以忠实概括和引用。人工审核、术语治理、研究证据广度互相独立；不再使用A–E总档统一限制回答。

## 回答模型收到什么

`scripts/answer_context.py`先校验输入，再生成自然语言证据卡。默认卡片只包含研究对象、作用、条件、结果、原文和“S1”式引用标记，不暴露内部事实ID、人工审核码或future_work等内部枚举。`references`单独供调用代码将引用映射回完整原文锚点，**发给模型时只发送instruction和evidence**；完整审计报告需显式开启`--audit`。

模型可以解释一般化学知识、整合机理、提出库外类比候选；文献具体数值和已报道效果必须有对应原文。一般知识不必逐句引用，但不能给外推候选伪配实验证据。只在影响选择、比较或适用性时提示具体限制，不重复通用免责声明。

该目录提供接口及真实片段示例，尚未接入外部正式问答应用。最终模型未定；测试模型不等于最终产品模型。便宜模型需满足精简结构、条件绑定、引用忠实和基本推断的任务要求，不凭名称推定质量或价格排名。

## 当前目录与历史归档

| 目录 | 当前用途 |
| --- | --- |
| `schema/` | v4模型抽取契约、内部契约、约束目录与生成的可读说明 |
| `registry/` | 当前类型、关系、词表、身份、角色、回答及标准映射登记 |
| `scripts/` | 当前可运行的生成、导入、校验、物化、迁移与回答接口 |
| `data/` | 当前来源快照与文献清单，保留供复现使用 |
| `examples/` | v4人工样例、真实模型抽取导入、回答上下文和试跑输入 |
| `reports/` | 与v4有关的验证、来源对齐、协议检查及模型试跑结果 |
| `tests/` | 当前契约和接口的回归测试 |
| `docs/` | 最新文字详解、版本对照、实现验收和状态摘要 |
| `归档/` | 已完成计划、过时草稿、旧试跑及未启用工具，不是运行入口 |

后台候选类型/关系和v3/v4迁移脚本仍被当前版本使用，继续保留。模型试跑中的失败也保留，不以归档名义只留下成功结果。邻近[旧版本](../旧版本/README.md)保持原位置作只读对照；归档对象为本目录内的历史材料。

## 运行

Python 3.10+，依赖见requirements.txt。以下命令在本目录执行。

```powershell
python -B -X utf8 scripts/build_examples.py
python -B -X utf8 scripts/build_hard_cases.py
python -B -X utf8 scripts/validate.py examples/literature_bundle.json --report reports/validation.json
python -B -X utf8 scripts/validate.py examples/hard_cases.json --report reports/validation_hard_cases.json
python -B -X utf8 scripts/render_schema.py
python -B -X utf8 scripts/check_budget.py
python -B -X utf8 scripts/review_protocol.py
python -B -X utf8 -m unittest discover -s tests -p 'test_*.py'
```

生成抽取提示：

```powershell
python -B -X utf8 scripts/extraction.py examples/literature_bundle.json blk:7cf3c70d130e763f
```

导入模型JSON（新文件输出，不隐式覆盖来源）：

```powershell
python -B -X utf8 scripts/extraction.py examples/literature_bundle.json blk:7cf3c70d130e763f --response response.json --output imported.json --model actual-model-id
```

生成回答上下文：

```powershell
python -B -X utf8 scripts/answer_context.py examples/literature_bundle.json --fact f:ado:low --fact f:ado:high --output context.json
```

这是按ID提供候选事实的消费接口，不是自动语义检索器。实际检索接入时应按问题选事实；`--limit`防止无界灌入。

迁移明确支持v3/v4，保留必要ID与来源；关系语义按登记角色投影，旧位置派生边会重建。不是通用迁移平台：

```powershell
python -B -X utf8 scripts/migrate_v4.py old-v3.json migrated-v4.json
```

## 已验证与范围

88项测试通过，两个真实片段bundle均无block；三处已知漏洞（反向端点、编造基准、合法缺失条件崩溃）有回归覆盖。示例仍为3篇4块的人工协议映射，不是全库抽取或金标。

保留单位原串，未引入全局单位换算、外部化学身份消歧、自动冲突裁决、完整推荐窗口和企业级平台。规范边减少不等于漏掉原文事实；所有事实可通过事实级键和原文回查使用。校验通过不等于化学语义正确；模型试跑结果与局限见重建说明。
