# 阶段03：化学物质抽取与消歧

日期：2026-10-20。输入为 [02_清洗](../02_清洗/) 的发布产物（chunks / blocks / tables），
按"抽取 → PubChem 检索 → 消歧 → 落盘"四步，对 48 篇文献做化学物质提取与消歧。
方案借鉴桌面参考稿《输入改成 Markdown + 图片后的流水线更新》，
但因 02_清洗 已完成切块与表格结构化，预处理部分改为直接复用其产物。

## 流程

```
02_清洗/out/chunks（正文检索块）
02_清洗/out/blocks（表格块 + 图片题注）
02_清洗/out/tables（完整表格 CSV）
   │
   ├─【步骤1 build_input.py】组装抽取单元
   │     ├─ 正文块 → source_type=text
   │     ├─ 表格 → [TABLE] 行记录（列名 + 行值，整表不切开）
   │     └─ 图片题注 → [FIGURE] caption 块
   │
   ├─【步骤2 抽取】DeepSeek 抽 ChemicalSubstance
   │     prompts/01_化学物质抽取提示词.md
   │
   ├─【步骤3 pubchem_lookup.py】span → PubChem 候选（PUG REST，带缓存）
   │
   ├─【步骤4 消歧】DeepSeek 候选内选号
   │     prompts/02_消歧提示词.md
   │
   └─【步骤5 merge_results.py】合并去重 + 规则降级 + 落盘 JSONL + 质检
```

## 运行

在仓库根目录执行（仅依赖标准库；步骤3需要访问 PubChem）：

```powershell
python -X utf8 清洗/03_化学物质抽取消歧/scripts/build_input.py
python -X utf8 清洗/03_化学物质抽取消歧/scripts/pubchem_lookup.py
python -X utf8 清洗/03_化学物质抽取消歧/scripts/merge_results.py
```

步骤2、4 为 LLM 调用，两种方式任选：

- **agent-hub 委派**（参考方法试跑的调用形态）：
  `bridge_cli.py delegate --to deepseek --project A2lab --prompt-file <提示词> --wait --timeout 900 --json`
- **DeepSeek API**：设置环境变量 `DEEPSEEK_API_KEY` 后用
  `python -X utf8 清洗/03_化学物质抽取消歧/scripts/call_deepseek.py --prompt <提示词> --input <抽取单元.jsonl> --output <结果.json>`

注意：提示词中 `{INPUT}` 与 `{OUTPUT}` 为占位符，调用前替换为实际路径。

## 与参考稿的差异（适配说明）

| 参考稿步骤 | 本阶段处理 |
|---|---|
| Markdown 按标题切块 | 已由 02_清洗 完成，直接用 chunks（带 section / page / source_block_ids） |
| 表格转行记录 | 用 blocks 的表头 + tables 的完整 CSV 生成，table_id 取 CSV 文件名 |
| 图片 OCR 分流 | 02_清洗未重跑 OCR，本阶段只取图片题注；文字型截图的 OCR 回填留待后续 |
| 检索层 PubChem | 不变 |
| 图注候选≥2 强制 ambiguous、聚合物规格代号不硬匹配、text+table 同 span 合并保留 alt_contexts | 在 merge_results.py 中实现 |

## 已知局限

1. 抽取与消歧由 LLM 完成，本阶段只保证流程可追溯，不宣称科学正确性。
2. 图片仅使用题注文本，图中文字（配方表截图等）未进抽取流。
3. PubChem 检索受限于其同义词库；商品名、分子量规格代号可能落入 unmatched_new，属预期。
4. 5638 个检索块全量抽取调用量大，建议先单篇试跑核对输出格式再放量。
