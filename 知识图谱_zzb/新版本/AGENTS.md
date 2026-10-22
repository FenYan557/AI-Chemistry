# 当前v2知识图谱

- 本目录是整理后的当前交付。读取CURRENT.json和manifest.json；默认离线入口为scripts/entity_resolution_retrieval.py，完整性入口为scripts/verify_graph.py。
- 三份图谱数据、schema、registry和必要运行代码共同构成完整交付；不要从备份加载旧图谱替代当前数据。
- 旧快照、修改过程、报告、开发代码及测试均在备份/20261021_整理前；不要删除或覆盖历史文件。
- 修改当前数据前保留快照，完成后同步CURRENT及manifest指纹；来源证据、实验条件、限定语与待审状态必须保留。
- .local是原有本机配置，未归档或迁移。不得打印、另存或提交密钥。若用户授权新增文献抽取，默认仍使用.local/llm_extraction.json中的独立知识抽取凭据；用户明确的同会话凭据授权优先，历史具体记录保存在备份中的AGENTS.md。
