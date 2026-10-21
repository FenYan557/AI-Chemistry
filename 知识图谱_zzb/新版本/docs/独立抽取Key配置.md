# 独立抽取 Key 配置与调用

本项目文献知识抽取固定使用 `.local/llm_extraction.json` 中的独立 Key，不复用 A2lab-key、Claude Code 或环境中的其他凭据。后续会话也遵循本目录 AGENTS.md 中的约定。

## 本机配置

- `api_key`：独立抽取密钥。
- `base_url`：API 基础地址，通常以 `/v1` 结尾，不包括 `/chat/completions`。
- `model`：默认模型，由实际抽取测试后设置；调用时可显式指定其他模型，但仍使用同一独立 Key。
- `api_format`：当前支持 `openai_chat_completions`。
- `enable_thinking`：当前设为 `false`，向兼容接口发送关闭思考模式的参数。

当前默认模型为 `qwen3.6-plus`。查询获得17个候选标识，实际试抽5个模型；本次选择依据是可用性和条件拆分表现，不是已核实的最低价格。详见[模型选型记录](../reports/model_selection_20261020/选型结论.md)。

只在本机编辑，不需要把密钥发到聊天中。`.local/` 已加入 `.gitignore`；该文件为本机明文配置，并非加密凭据库，不应分享或作为报告附件。

## 使用

在新版 schema 目录运行，Python 与 jsonschema 依赖沿用 requirements.txt，不增加 SDK：

```powershell
# 查询当前服务列出的模型（列表不保证实际可调用）
python -B -X utf8 scripts/extraction_llm.py models

# 用本机配置中的默认模型抽取单个块并校验导入
python -B -X utf8 scripts/extraction_llm.py extract reports/model_selection_20261020/source_bundle.json blk:7cf3c70d130e763f --output reports/new_extract.json --response-dir reports/new_extract_response
```

输出包括响应正文、用量、耗时、服务返回的模型标识及通过校验的 bundle。输出文件和响应目录必须是新路径，避免覆盖已有记录。响应不符合 schema、原文不能定位或内部记录校验失败时，不生成导入成功结果；原始响应保留便于定位问题。没有自动重试或其他 Key 兜底。

当前是可运行的单块调用入口，不是全库批处理或完整增量归一系统。现有模型契约每块最多 8 条事实；长段与高密度段需要拆分后抽取，达到 8 条应检查遗漏。跨段条件关联、实体归一仍需后续流程处理。

本次模型筛选记录位于 `reports/model_selection_20261020/`。服务模型别名不能验证真实上游身份，返回用量不能直接换算服务商收费；模型列表未提供价格，不能据此声称选中了最便宜的模型。
