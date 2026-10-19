# 阶段二：清洗与检索切块

当前结果：48 篇、5,316 个块、5,638 个检索块、98 张完整表格。正式数值与局限统一见 [总说明](../README.md)。

- scripts/clean.py：读取阶段一修复块，生成 blocks、meta、tables 与删除记录。
- scripts/chunk.py：生成检索块；三张长表仅在检索预览截断，完整 CSV 保留。
- scripts/verify2.py / release_check.py：按真实来源 ID 和文档目录验收，统计全图注和完整 CSV 的数值差额。
- scripts/check_reproducibility.py：临时重建阶段二，与正式产物逐文件比较。
- scripts/test_release_check.py：图注、重复数值、符号、科学计数法及空格边界回归。
- scripts/test_chunk_regression.py：章节、重叠溯源、跨页及表格截断回归。

out/report/release_validation.json 是当前验收来源。metrics.json、chunks_summary.json 是处理器计数，stage2_preanalysis.json 是历史开工分析。句尾目标未达标，数值差额未逐条人工裁决，不声称所有质量目标通过。执行命令见总说明。
