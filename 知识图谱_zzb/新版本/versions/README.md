# 两个完整知识图谱数据版本

| 目录 | 内容 | 何时使用 |
| --- | --- | --- |
| [v1_direct_extraction](v1_direct_extraction/README.md) | 原始全库直接抽取，完整图谱6,929事实、10,403提及、3,302边 | 查看原始自动结果、回溯被筛选内容 |
| [v2_entity_enhanced](v2_entity_enhanced/README.md) | 当前实体完善工作版，完整图谱5,816事实、16,936提及、2,905边 | 继续完善关系、检查条件、准备应用 |

唯一当前选择器：[CURRENT.json](../CURRENT.json)。机器目录：[index.json](index.json)。每个版本目录都有完整`knowledge_graph.json`、`manifest.json`和说明，不需要手工把实体增量与事实文件拼起来。

数据版本分别是1.0.0与2.0.0-dev.20261021；schema均是4.0.0-draft。v2继承了保守筛选中间结果并补充实体，不是把v1所有原始事实照搬后加节点。快照固定只表示文件字节和出处已登记，不代表实体/事实经专家确认。

`reports/`保留原始响应、缓存、失败、主审及中间结果，是证据区，不是第三个当前图谱版本。大图文件和运行目录本地保存，Git跟踪清单、哈希、代码与文档；备份或迁移时必须把本目录两个完整版本文件一并带走，单独克隆代码仓库不会带回图谱载荷。

检查版本完整性（不联网）：

```powershell
python -X utf8 scripts/kg_versions.py check
python -X utf8 scripts/kg_versions.py current
```

[版本治理规则](../docs/版本治理.md) / [变更记录](../CHANGELOG.md)
