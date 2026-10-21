# 全库知识抽取结果

> 本目录现在是历史运行及中间结果的追溯区。两个正式登记的数据入口见 [versions](../../versions/README.md)：v1直接全库抽取、v2实体完善工作版；当前工作入口见 [CURRENT.json](../../CURRENT.json)。下文“最终保守版”指本次历史筛选阶段的结果，不代表全项目最新版本。

首轮抽取与本轮质检已完成（2026-10-21）。输入48篇文献、3,714单元。抽取使用独立Key/qwen3.6-plus；核验使用同一独立Key/qwen3.7-plus，均为非思考模式。

**入口：[验收报告](验收报告.md)。保守图谱5,816事实；语义核验仍需每批独立抽检，最终全库精确率尚未测得。**

## 取用哪些文件

- [quality/precision_graph.json](quality/precision_graph.json)：最终保守版，5,816事实、8,951提及实体、2,905边。
- [quality/primary_reviewed_facts.jsonl](quality/primary_reviewed_facts.jsonl)：60条主侧逐条原文核对通过事实，仍非专家金标；来源引用由保守图谱解析。
- [quality/accepted_facts.jsonl](quality/accepted_facts.jsonl)：保守版逐行事实，适合后续索引。
- [quality/final_summary.json](quality/final_summary.json)、[quality/final_decisions.json](quality/final_decisions.json)：最终统计及逐事实筛选决定。
- [quality/quarantine.jsonl](quality/quarantine.jsonl)：1,267条原始事实隔离；另见补充候选隔离文件。
- [knowledge_graph.json](knowledge_graph.json)：首轮原始图谱，6,929事实，保留追溯；不作为已核准结果。
- facts.jsonl、entities.jsonl、edges.jsonl：首轮原始导出，不能与quality中的保守版混用。
- input_manifest.json：文献SHA、3,714单元来源映射、98表的CSV物理行、图像清单。
- units/、requests/、retry_history/：单元状态、模型输入响应、已知用量及失败历史；请求记录不保存Key或请求头。
- glossaries/、alias_candidates.json：篇内术语和别名候选，未自动跨文献合并。

## 验证范围

正文2,580块、图注809块、公式149块、表格176行组。跳过987标题、125参考文献/行政块。571无图注图像待图像处理，带图注图像也只读了文字。

全部单元尝试过：success 1,797、empty 1,187、partial 542、failed 188。empty不证明文献无事实，partial保留通过部分，failed仍待恢复。所有节点主要是提及实体，未完成身份归一。

独立主侧32条和后续新样本24条分别有8条严格字段误标；原始成绩与修改顺序保留在验收报告，不能把最终保守版宣称为100%正确。主侧复查由AI完成，不是专家金标。代码134项测试通过；来源SHA一致；2篇抽取缓存及全质检一键续跑均实测0网络调用。

## 继续处理与增量运行

在新版schema目录执行，使用单独run目录接纳新增/修改来源：

```powershell
python -B -X utf8 scripts/knowledge_pipeline.py --run reports/下一批 --reuse-from reports/full_extraction_20261020
```

`--dry-run`只看计划；`--stage extract`只抽取；`--stage verify`只核验。单批中断使用同一run目录，兼容检查点不会重复调用。抽取模型/协议不兼容时拒绝复用；核验模型可用`--judge-model`指定并需重新校准。

仅重试本批partial/failed：

```powershell
python -B -X utf8 scripts/knowledge_pipeline.py --run reports/full_extraction_20261020 --retry-failed
```

先前partial/failed状态复用时原样保留，重试需显式指定；保留旧失败历史。单个run不能同时启动多个写入任务。认证/路由失败停止派发，不自动换Key。

[方法与复用说明](../../docs/全库抽取验收与复用.md)说明规则、抽检边界和后续要求。已完成本轮抽检标签只对本轮来源成立，新批次仍须独立抽检。
