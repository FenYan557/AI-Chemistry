# 电镀添加剂选型知识图谱 · Schema v1.1

> 历史参考状态（2026-10-19）：用户已决定从头重建；本文的“当前”和“真源”仅指旧版 v1.1，不是新方案的约束。请先读[讨论总结](../../讨论/讨论总结_过程与最终结果.md)。

本目录定义电镀文献事实的结构、来源、条件、证据等级与校验规则。当前 `frozen: false`；共有 24 类节点、34 类边、16 个谓词和 51 条约束。

**结构可以表达多跳查询；真实图谱、图查询程序与检索适配器尚未交付，因此尚不能直接运行多跳问答。**

## 阅读与目录

| 位置 | 用途 |
| --- | --- |
| [Schema_v1.1_从基础理解结构与用途.md](Schema_v1.1_从基础理解结构与用途.md) | 当前入门讲解：对象、关系、抽取内容与用途 |
| [schema.yaml](schema.yaml) | 单一真源：对象、边、谓词、派生字段和检索契约 |
| [claims.schema.json](claims.schema.json) | 抽取输出的断言 JSONL 格式 |
| [constraints.yaml](constraints.yaml) | 拒收、降级、警告规则与落地位置 |
| [id_conventions.md](id_conventions.md) | ID、来源锚点和清洗接口 |
| [lexicon/](lexicon) | 六份受控词表 |
| [scripts/](scripts) | 契约自检、断言校验、图校验、回归夹具、只读语料普查 |
| [docs/知识图谱结构图.png](docs/知识图谱结构图.png) | 一页看懂：五层结构、主干边与三道门禁（重渲染：`python -X utf8 docs/渲染结构图.py`） |
| [docs/实体关系与约束清单.md](docs/实体关系与约束清单.md) | 当前实体/边/谓词/约束的实测清点与落地状态（查表版） |
| [docs/实体关系与约束的含义.md](docs/实体关系与约束的含义.md) | 同一套契约的语义讲解：每个对象代表什么、每条规则防哪种错（读义版） |
| [docs/多跳支持与落地边界.md](docs/多跳支持与落地边界.md) | 可表达的多跳路径、限制和实现缺口 |
| [docs/知识图谱结构综述与选型.md](docs/知识图谱结构综述与选型.md) | 历史设计背景 |
| [docs/文献支撑.md](docs/文献支撑.md) | 设计依据及工程判断 |
| [docs/与GraphRAG-LightRAG对比.md](docs/与GraphRAG-LightRAG对比.md) | 框架组合思路，非当前实现说明 |

旧入门说明和 v1.0 评估已移出当前目录，保存在 [历史归档](../_archive/schema_v1.0_20261019/README.md)。历史压测、主观评分及旧快照不作为当前验收结果。

## 当前数据接口

上游为 `项目/知识抽取/清洗/02_清洗/out/`：

- `blocks/{doc_id}.jsonl` 与同名 `.meta.json`：来源块及文献元数据。
- `tables/{doc_id}__p{page}_{i}.csv` 与 `_tables_index.csv`：完整表格及索引。
- `chunks/{doc_id}.jsonl`：检索切块，携带 `source_block_ids` / `source_pages`；命中后回读 blocks，chunk_id 不作证据锚点。
- 表格预览 `table_truncated=true` 时必须回读完整 CSV，数值引用到单元格。

2026-10-19 契约快照：48 篇、5316 blocks、5638 chunks、98 张表。清洗 `metrics.json` 的保留块现为 5316，旧“5807 与 5316 不一致”的问题已修复。这些是清洗规模，不能当作已建图规模。

`enriched/` 尚未按新 blocks 重跑，`CITES` / `REFERS_TO` 相关查询暂不能视为可用。旧 chunks 索引须重建。

## 执行流程

清洗产物 → 抽取 claims → 断言校验 → 归一化与物化 nodes/edges → 图校验 → 聚合 KnowledgeUnit → 检索与回答。

本目录提供契约与校验器。抽取、化学身份归一化、物化、窗口聚合、索引及查询在执行侧实现。抽取期填写 `name_raw` / `run_local` / `experiment_local`，最终图内 ID 由归一化工序生成。

## 使用

在本目录运行（Python 3.10+，依赖 `pyyaml`、`jsonschema`）：

```powershell
# 契约修改后自检
python -B -X utf8 scripts/selfcheck.py
# 人工夹具回归；不证明真实抽取或多跳问答质量
python -B -X utf8 scripts/selftest.py
# 下列占位路径须替换成实际数据
python -B -X utf8 scripts/validate.py --claims <claims.jsonl> --corpus <清洗产物目录>
python -B -X utf8 scripts/validate_graph.py --nodes <nodes.jsonl> --edges <edges.jsonl>
python -B -X utf8 scripts/survey_corpus.py --corpus <清洗产物目录>
```

校验器退出码 1 表示存在 reject。

## 使用时必须保留的语义

- `not_reported` 是未知，只有明确 `unconstrained` 才表示不限。
- `comparability_key` 相同仅满足初筛；关键字段未知仍不可据此比较，AR 桶内仍须核对原始结构、AR 与工况。
- KnowledgeUnit 保留逐条 `evidence_windows`；`effective_window` 仅表达共同支持区间，允许 null，不能把离散点填成连续范围。
- 未裁决冲突单独展示；pending/reject 不能作为已验证证据。
- 证据支持度与性能优劣分别判断；多条边连接不等于因果成立，多篇证据不能自动提高等级。

## 剩余工作与冻结

三条化学约束仍待实现：`acid_base_compatible`、`metal_consistency`、`acid_copper_composition`。表画像、SMARTS 草案验证、真实抽取和聚合算法仍需执行侧推进；表格可读性不等于已具备正确的数值抽取模板。

现阶段适合先做 1–6 篇试点；既定冻结节点为 10 篇试点后。冻结指标沿用既有方案：新增谓词 ≤2 个/篇、downgrade 率 <40%、KU 中 consensus 占比 >10%、schema 改动 <3 处/篇，均尚未作为真实试点结果验证。

契约改动需检查 `schema.yaml`、`claims.schema.json`、`constraints.yaml` 与校验器的一致性，并通过 `selfcheck.py`。
