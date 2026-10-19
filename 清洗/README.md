# 电镀文献清洗阶段结果 v1

日期：2026-10-19。48 篇文献的两阶段处理结果：补足解析缺陷 → 去噪、组织结构与检索切块。

这是**可追溯、可复现的阶段性结果**。文件结构与来源关联检查通过；不宣称 PDF 原文完全无损，也不宣称所有科学数值均已人工确认。原文 PDF、MinerU 内容块与图片复用仓库的 [文献提取](../知识图谱所需文献/文献提取/)。

## 当前结果

| 项目 | 本次实际验收 |
|---|---:|
| 文献 | 48 篇 |
| 原始 / 阶段一块 | 10,975 / 10,975 |
| 阶段二块 | 5,316 |
| 正文 / 标题 | 2,700 / 987 |
| 图片与图表 / 公式 | 1,382 / 149 |
| 完整表格 CSV | 98 |
| 检索块 | 5,638 |
| 来源块引用缺失 / 跨章节检索块 | 0 / 0 |
| 已逐篇解析图片文件路径 | 1,382 |
| 参考文献结构化记录 | 2,758 |
| 删除决策记录 | 5,796 |
| 句尾完整率（标点启发式） | 89.04% |
| 正文章节覆盖 | 99.41% |
| 正文检索块平均字符数（全体加权） | 471.69 |
| >900 字符的检索块 | 14 |

计数以 [release_validation.json](02_清洗/out/report/release_validation.json) 为准。旧报告中的 3,777 / 5,807 块及 6,309 检索块不再适用。

## 目录与使用

- 01_补足原材料缺陷/out/repaired/：48 份修复块及对应字段候选；字段为正则候选，需抽取层确认。
- 01_补足原材料缺陷/out/report/：已有缺陷总账、修复统计、OCR 与阶段一 PDF 文本诊断记录。
- 02_清洗/out/blocks/：正文、标题、表格、图片、公式；meta.json 保留参考文献和页码映射。
- 02_清洗/out/tables/：完整矩阵 CSV 及表清单。科学证据取完整 CSV。
- 02_清洗/out/chunks/：检索预览；记录携带 source_block_ids / source_pages。
- inputs/documents_index.json：文档 ID → 仓库相对原材料路径、PDF、修复块和原始内容块字节 SHA-256 与规范 JSON SHA-256。
- inputs/文献清单.csv：冻结的书目信息；PDF 路径相对于仓库的知识图谱所需文献目录。
- lib/、各阶段 scripts/：现有处理实现与发布验收。
- docs/历史方案/：保留设计依据，其中旧计划及数字不代表当前验收。

图片块 img 相对于该文档原始解析目录：查 documents_index.json 对应条目的 source_dir，在仓库根目录以 source_dir / img 定位。表格 csv 相对于 02_清洗/out/。page 从 1 开始；MinerU page_idx 从 0 开始。bbox 为原始归一坐标，不能直接当作 PDF 点坐标。

## 信息保留与已知局限

1. **本次整理没有新增科学内容丢失**：339 个阶段数据文件已与原工作区逐一比较；仅把 72 个 JSONL 文件中表格路径的反斜杠改为正斜杠，其他 JSON 值保持一致。原始/发布哈希见 [packaging_integrity.json](02_清洗/out/report/packaging_integrity.json)。这不证明此前解析与清洗无损。
2. 三张表的检索预览被截断；对应完整 CSV 全部存在。不得只凭 chunk 回答整张表的问题；具体表见发布验收记录。
3. 原 97.70% 指标漏计输出图注，不再作为质量结论。新诊断纳入正文、公式、完整表格、图表题注及 caption_extra，使用带符号数值多重集；负号、科学计数法、千分位和重复次数均纳入。
4. 新诊断：出现次数匹配 25028/25718（97.32%）；按篇去重匹配 6827/6927（98.56%）。两项口径不同，也不同于旧 97.70%，不能直接比较。包含引用号、化学式下标、作者地址与去噪数据；差额**不等于实验数据损失率**。39 篇存在出现次数差额，见 [numeric_differences.json](02_清洗/out/report/numeric_differences.json)，尚未逐条人工裁决。
5. 句尾完整率未达到原定 95% 目标；标点完整不代表语义完整。14 条检索块超过 900 字符。
6. 原材料仍有单位、上下标、题注与表格语义风险。已有 OCR 记录 confirmed 86 / partial 9 / unreadable 3，是历史辅助证据；本次未重跑 OCR。
7. 删除记录存在且字段齐全，不据此宣称每次删除均正确或所有删除已独立审计。图表与公式数量守恒不能替代逐项内容核对。

## 验证与复现

建议 Python 3.10+。阶段二、验收和回归仅依赖标准库。在仓库根目录运行：

    python 清洗/02_清洗/scripts/verify2.py
    python 清洗/02_清洗/scripts/check_reproducibility.py
    python 清洗/02_清洗/scripts/test_release_check.py
    python 清洗/02_清洗/scripts/test_chunk_regression.py

本次已执行以上检查。结构验收通过；临时目录重建的 243 个 blocks/meta、tables 和 chunks 文件与正式数据一致，见 [reproducibility.json](02_清洗/out/report/reproducibility.json)。复现检查不覆盖正式科学数据；验收会更新相应 JSON 报告。

需要重新生成正式阶段二产物时：

    python 清洗/02_清洗/scripts/clean.py
    python 清洗/02_清洗/scripts/chunk.py
    python 清洗/02_清洗/scripts/verify2.py

从已有阶段一产物复现即可，无需重跑 OCR。完整阶段一重建见 [阶段一说明](01_补足原材料缺陷/README.md)。改变输入后须更新相关报告，不能继续引用旧哈希、旧 OCR 或旧验收数字。

## 发布范围

不包含旧 out 归档、归档 ZIP、旧 enriched、review 临时脚本/派发任务/运行日志与缓存。正式数据、来源原材料、删除记录及两阶段处理实现均可追溯。旧 enrich.py / verify.py 已被现行 clean.py / verify2.py 替代，未作为当前入口发布。

跨平台完整性：发布目录以 .gitattributes 保留 JSON/JSONL/CSV 字节，避免 Git 换行转换改变数据哈希。原材料沿用仓库已有换行规则，验收使用 documents_index.json 中的 content_list_json_sha256：按键排序、ensure_ascii=False、紧凑分隔符规范化 JSON 后取 UTF-8 SHA-256；content_list_sha256 则保留整理时原材料的字节哈希用于记录。
