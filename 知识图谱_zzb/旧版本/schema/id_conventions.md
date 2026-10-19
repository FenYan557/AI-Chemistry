# ID 与锚点约定 v1.1

本文件规定"一个信息单元在图里叫什么名字"。它比 schema 更容易被忽视，但**改一次就要重锚定全库**，所以先定死。
（本仓库只定规则，不含任何图谱数据；下面的 ID 都是**格式示例**，不是某篇文献的真实取值。）

## 1. 为什么不直接用清洗侧的块序

清洗产物（`清洗\02_清洗\out\`）里有三套块的编号：

| 产物 | 有无 ID | 问题 |
|---|---|---|
| `blocks\*.jsonl` | `block_id` | 位置哈希；本轮清洗已写入 |
| `enriched\*.jsonl` | 无 | 同上，加了 section/caption/cites |
| `chunks\*.jsonl` | `{doc_id}#0000` 顺序号 | 顺序号随切块规则变化而变 |

顺序号**不能当锚点**：清洗规则一改（合并阈值、切块长度），`#0000` 就指向另一段文字，而断言里存的还是旧号 → 溯源链静默错位，且事后查不出来。
所以 block_id 用**位置哈希**：位置是"这一页的这个矩形"，改了文字也不变。

块级溯源字段带来的三条锚点规则：

- `merged_from`：本段由几个原始块合并而成（1 = 未合并）。合并不可逆，**引用该段时不要声称"原文此处"就是这段起止**，允许多块拼合。
- `split` / `part`：超长段（>1200 字符）被切分；同一段的不同 part 是**独立 Block**（bbox 不同、block_id 不同），引用时要指明 part。
- `printed_page` 有值时优先展示期刊页码，引用定位仍用 PDF `page`。

## 2. block_id 生成规则

```
block_id = "blk:" + sha1( doc_id + "|" + page + "|" + bbox_ints.join(",") + "|" + type + "|" + part )[:16]
bbox_ints = bbox 各坐标四舍五入到整数（PDF point，亚点级差异属解析噪声）
type      = text|heading|table|image|chart|equation
```

- 例（格式示例，非真实取值）：`<doc_id>|3|48,762,475,900|table|0` → `blk:<16 位十六进制>`
- **`part` 必须进哈希**：清洗对超长段（>1200 字符）切分成多个 `part`，这些 part 共享同一页同一 bbox。若不带 `part`，实测 5316 个块只生成 4843 个唯一 ID（撞号 473 次），锚点会指向错误片段。未切分时取 0。
- 只有 16 位十六进制，可读性差但可复制、可校验；`scripts/validate.py --corpus <清洗产物目录>` 会反查是否存在。
- 同一 block 的**文字**改动（阶段一 repair、阶段二 LaTeX 归一）不改变 block_id；文本指纹另存 `text_sha1` 用于变更检测。

**已知边界（必须记住）**：
- 阶段二若改了合并阈值，被合并段落的 bbox 会变 → block_id 变 → 旧断言的锚点失效。
  处置：`Document.pipeline_version` 记录清洗产物版本；版本变化时先出一份重锚定报告，断言按 `doc_id + page + quote` 回查重绑，失败者降级待人工。
- int 取整理论上可能让两个仅差亚点的块撞号。校验器会报重复 ID，出现即改为 `%.1f` 生成。

## 3. 其它 ID

| 对象 | 格式 | 说明 |
|---|---|---|
| Document | `doc_id` 原样（如 `1_s2_0_S0013468609007385_main`、`3_异靛蓝季铵盐的合成及其在电镀铜中的应用`） | 沿用清洗侧命名，不做二次编码；中文 doc_id 保留，避免一改就对不上表 |
| Table | `tbl:{doc_id}:p{page}:{i}` | `i` = 该页第几张表（0 起），与 CSV 文件名 `{doc_id}__p{page}_{i}.csv` **一一对应**；清洗 v2 起表块自带 `table_meta.csv`，直接读它，别再按页码猜 |
| TableCell | `(table_id, row, col)`，均为 0 起 | 与 pandas 默认索引一致；`row=0` 是第一行表头（清洗保留了两行表头的原始行，不要先跳表头再数） |
| Figure | `fig:{doc_id}:p{page}:{i}` | 同页顺序号；`fig_no` 另存（"Fig. 4" 这种，可能为 null） |
| Equation | `eq:{doc_id}:p{page}:{i}`；`tag` 存原文编号（`3` / `式1`） | 公式块文本里常自带 `[式1]`，抽取时拆到 tag |
| BibEntry | `{doc_id}#ref{n}` | `n` 为原文序号 |
| Experiment | `exp:{doc_id}#e{n}` | 篇内编号，**跨篇不合并** |
| Run | `exp:{doc_id}#e{n}#r{k}` | 表格一行 = 一个 Run；k 从 1 起 |
| AdditiveUsage | `run_id#u{m}` | m 为该 Run 内出现顺序 |
| Observation | `obs:{doc_id}#{seq}` | seq 篇内单调，重建时允许变（Observation 不是外部引用对象） |
| Claim | `c:{doc_id_short}:{seq}` | `doc_id_short` = doc_id 的前 12 个安全字符 |
| EvidenceLink | `ev:{claim_id}#{k}` | |
| Conflict | `cf:{seq}` | 跨篇 |
| KnowledgeUnit | `ku:{subject_hash}:{predicate}:{indicator}:{direction}:{comparison_hash}` | `subject_hash` = sha1(subject.ref)[:8]；`comparison_hash` = sha1(comparability_key)[:8]（UTF-8）；**同一个 KU 只能对应一个 comparability_key**，跨口径必须拆号 |
| Chemical（已解析） | `chem:inchikey:{InChIKey}` | canonical 以 InChIKey 为准（异构体同键，盐型不同键） |
| Chemical（未解析） | `chem:unresolved:{sha1(归一化名)[:12]}` | **一等公民**：保留原始写法、置信度、出现位置；绝不因为"没 SMILES"就丢掉 |
| Motif / Role / Method / Mechanism / BathClass | 枚举名，不加前缀 | 词表在 `lexicon/` |

## 4. 锚点（anchor）最小契约

任何 Observation / Claim / AdditiveUsage / Run 必须带 ≥1 个 anchor：

```json
{"kind":"block","doc_id":"…","page":8,"block_id":"blk:…","quote":"原文片段","quote_check":"exact"}
{"kind":"table_cell","doc_id":"…","page":3,"table_id":"tbl:…:p3:0","row":9,"col":5,"quote":"Superfill"}
```

- `quote` 必填，且 block 类必须与原文归一化后子串匹配（≤0.90 相似度即拒收）。
- 表格数值**必须**锚到 `table_cell`，不许只锚整表：只锚整表等于放弃单元格级溯源，数值错行查不出来。
- 页码用 PDF 页（1 起，与清洗侧 `page` 一致）；`printed_page` 只是展示用，期刊页码与 PDF 页码不同（例：某篇 PDF p3 = 期刊 p5896）。

**四件事必须带 comparability_key**：
- 比较大小 / 排序候选 / 检出冲突 / 聚合 KnowledgeUnit；
- 它由 `{指标}|{主方法}|{参比电极 or na}|{孔型 or na}|{AR 桶 or na}|{面积基准 or na}` 派生，定义见 `schema.yaml#derived_fields`；
- 换算与桶化的规则写在这里而不是检索代码里，否则同一个问题两次回答会给出不同的口径判断。

## 5. 三处"不能做"的 ID 操作

1. **不许让 LLM 输出最终 ID**：抽取期只填 `name_raw` / `run_local` / `experiment_local`，映射到图内 ID 是归一化工序，可复现、可重跑。
2. **不许跨篇合并 Experiment / Run / Bath**：只允许跨篇合并 Chemical（经 alias + InChIKey）与 Motif（词表）。
3. **不许用文本当主键**（哪怕看起来唯一）：`SPS` 在不同篇里可能指不同纯度/牌号，文本只能作别名。

## 6. 本仓库的边界

这里只有**契约与校验器**，没有任何从语料抽出来的节点/断言数据：

- 抽取、归一化、物化成图都在执行侧另起（读者按本 schema 自行实现）；
- 因此本目录不含 `examples/claims.jsonl` 之类样例数据 —— 样例一旦进仓库，就会被当成"已验证过的图谱"，而它只是手写的几条示意。
- 需要跑通校验器时，自己给 `--claims` / `--nodes --edges` 指一份输入即可。

## 本轮清洗接口（2026-10-19）

chunks 带 `source_block_ids` 与 `source_pages`；这是来源块集合，不声明句级字符坐标。`page` 为来源首页，`pages` 为来源页集合。块的原文仍须回读。章节、图表、公式边界不携带上一段重叠；同节按长度切分才保留重叠。表格 `table_truncated` 标记预览截断，数值一律回读完整 CSV。旧 chunks 已失效，下游索引须重建。
