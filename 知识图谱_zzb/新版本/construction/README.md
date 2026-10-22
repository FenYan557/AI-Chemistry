# 构建入口

抽取：python construction/extraction.py <bundle> <block_id>，默认只生成提示词；导入必须显式指定--response与--output。实体归一：python construction/resolve_entities_llm.py --help。离线导入/校验不加载凭据，不自动联网。真实模型调用仍使用现有.local独立凭据，调用前按任务范围选择片段；不全库重抽。

同一性合并需decision、basis与逐字定义证据，成员并列共现不是同义。范围使用range类型，未报告单位保持未解决。保留coverage_complete=false和remaining_topics以便后续补抽。历史无证据提案保留uncertain。
