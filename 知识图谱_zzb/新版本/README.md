# 当前v2电镀文献知识图谱

版本：**kg-v2-repaired-20261022-r1**。机器入口为`CURRENT.json`，公开文件清单及指纹为`manifest.json`。本目录可独立离线读取，不依赖备份。

| 文件/目录 | 内容 |
| --- | --- |
| `knowledge_graph.json` | 48篇文献、3720个原文块、16966次提及、5844条事实、2902条图边，以及条件、结果、证据 |
| `entity_graph.json` | 5892个概念，包含别名、提及映射、篇内对象与上下文事实 |
| `relation_context.json` | 6条独立补充关系，保留方法、分组、基准及限定语，不重复计入事实数 |
| `schema/`、`registry/` | 数据结构、词表、来源更正与已知原文冲突 |
| `scripts/` | 离线读取、检索及校验 |
| `construction/`、`tests/` | 当前构建契约、合并门禁及针对性测试 |
| `docs/` | 使用说明、修复记录、队列与部分PDF核验图片 |

## 使用

在本目录执行，离线检索及校验不调用大模型：

```powershell
python -m pip install -r requirements.txt
python -X utf8 scripts/verify_graph.py
python -X utf8 scripts/entity_resolution_retrieval.py "PVP" --limit 8 --output "$env:TEMP\kg_v2_context.json"
```

详见[使用说明](docs/使用说明.md)。人工审核使用[唯一审核表](../人工核验/v2_人工审核.xlsx)，先读[审核说明](../人工核验/审核说明.md)。

## 质量与更新

专家审核仍为pending。结构校验不代表所有知识正确或完全覆盖语料；身份、条件、单位及原文冲突继续保留待审。相同概念不表示不同文献共享实验条件。检索可能漏掉已有事实，一次未命中不能证明未收录。

修复范围见[修复记录](docs/REPAIR_20261022.md)。英文术语、缩写、化学式与引文保留原样。修改数据前留快照，修改后同步派生视图、CURRENT和manifest指纹。

迁移携带manifest列出的公开文件及CURRENT、manifest本身，不携带`.local/`或历史备份。历史脚本只供追溯，不直接覆盖当前数据。
