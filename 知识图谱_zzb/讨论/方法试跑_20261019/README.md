# 自动发现方法试跑：输入、检查与复现

2026-10-19。用途：检查“不预设领域实体/关系清单”的候选发现及定义归一流程能否执行。不是正式准确率、迁移或BERT比较实验。主方案见[优化方案与实验协议](../02_抽取方法与试跑/可迁移知识抽取方法_优化方案与实验协议.md)。

## 输入与已执行步骤

- `input_blocks.jsonl`：3篇文献、4段清洗文本，含浓度依赖作用、退火前后电阻率和未来协同研究建议。
- `input_manifest.json`：原文件与输入哈希；这是有目的选择且父侧事先读过的样本，不是随机样本或未见测试集。没有回看原PDF验证解析质量。
- `01_候选抽取提示词.md`：未给领域类型列表的通用候选记录协议。
- `01_candidates.json`：DeepSeek原始结果，58个提及、39个原始类型名称、18条事实候选、1条别名候选。原始错误未覆盖修改。
- `audit_pilot.py`、`01_audit.json`、`01_offsets.json`：父侧独立程序检查提及、关系原文、证据句、条件片段与引用ID。
- `derive_relation_spans.py`、`01_candidates_with_spans.json`、`01_span_derivation_report.json`：按统一规则拆省略号、顺序定位原文片段的派生结果，不是模型重跑或语义修正。
- `02_类型归一提示词.md`、`02_induced_proposals.json`：对固定候选做定义归一，产生39项表示提案（19 entity、11 attribute、8 context、1 defer）及14项关系提案；这不是39种最终领域节点。仍未证明粒度恰当或模式变简单。
- `audit_induction.py`、`02_audit.json`：父侧确认58个提及、18条事实均各有一个映射，ID和反向引用一致，原始输入与候选哈希未变。6条事实被建议拆分；语义合理性尚未金标验证。
- `03_改进抽取提示词模板_未执行.md`：role、fact_group、关系片段与独立认知状态的后续协议提案，本轮未重跑。
- `update_manifest.py`、`execution_manifest.json`：运行环境、任务ID、文件哈希和远端复现限制。
- `experiment_protocol.json`：后续正式实验拟定协议；其中模型revision、金标和实际划分尚未就绪，不能当作已经能训练的完整配置。

## 父侧发现的错误

全部提及、主证据句和条件值均可作逐字子串定位，但f11/f12/f14的`relation_raw`使用`...`拼接，原文不存在这一连续字符串。子任务自报检查未覆盖这一字段；父侧检查器返回退出码1并保存3项违规。这个结果是本次输出中的协议违规，不是语义错误率或抽取准确率。

派生脚本为这三条保留原始写法，并新增有偏移的`relation_spans`；状态仍是`fragments_only_needs_semantic_review`。这证明片段能定位，不证明片段构成完整正确关系。

语义审查另发现：若干事实含多个作用或阶段，参与者只有ID而没有角色。下一版记录协议应加语义角色与共享组标识，并按原子事实拆分；不能用增加领域实体类别代替这一步。浓度依赖两种作用也应分别绑定条件，不能仅作为两个未绑定的词组保存。

## 可复现检查

在项目根目录运行：

```powershell
python -B -X utf8 'ai_electroplating/项目/知识图谱/讨论/方法试跑_20261019/audit_pilot.py'
python -B -X utf8 'ai_electroplating/项目/知识图谱/讨论/方法试跑_20261019/derive_relation_spans.py'
python -B -X utf8 'ai_electroplating/项目/知识图谱/讨论/方法试跑_20261019/audit_induction.py'
```

第一条在本次原始结果上预期退出码为1，报告3个`relation_raw`错误；不要把失败改成通过。第二条生成独立派生层，原始文件不变。

候选抽取和类型归一的实际入口：

```powershell
python -X utf8 'D:/Apps/Tools/agent-hub/agenthub/bridge_cli.py' delegate --to deepseek --project A2lab --prompt-file 'D:/Files/Work/A2lab/ai_electroplating/项目/知识图谱/讨论/方法试跑_20261019/01_候选抽取提示词.md' --wait --timeout 900 --json
python -X utf8 'D:/Apps/Tools/agent-hub/agenthub/bridge_cli.py' delegate --to deepseek --project A2lab --prompt-file 'D:/Files/Work/A2lab/ai_electroplating/项目/知识图谱/讨论/方法试跑_20261019/02_类型归一提示词.md' --wait --timeout 900 --json
```

这两条会调用本机DeepSeek现金通道，并写提示词指定的结果文件。重跑前应将输入、提示词和输出复制到独立实验目录并同步路径，以保存本次原始结果。它们是本机探索通道，不是无需修改即可在任意机器运行的通用训练程序。

迁移到其他数据时复用的是记录协议、分阶段步骤和审查/评价方法；应更换输入清单，保留哈希，并固定模型和执行环境。当前远端`deepseek-flash`为服务别名，解码参数、后端权重快照和CLI系统上下文没有全部暴露，因此不能承诺逐位再现。正式论文需要至少一个锁定权重revision的开放模型实验版本，辅以重复运行结果。

## 不应据此声称

没有人工金标、独立测试集、BERT训练或跨域实验；不能给出P/R/F1、模型优劣、模式质量最优或迁移成功的结论。候选输出量、类型数与子串通过也不是这些结论的替代指标。两轮方法讨论与两阶段试跑已完成产物验收；这里的“验收”仅指实际文件、映射和可追溯检查，不表示自动产生的模式获得科学正确性认证。
