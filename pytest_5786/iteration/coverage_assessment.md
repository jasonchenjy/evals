# False positive, false negative and coverage assessment

结论限定为固定 base、当前11个 mandatory checks、已审查消费者和本次11个对照补丁。
三个新诊断均代表真实的编码遗漏；没有为了得到失败而按测试名称、异常字面量或特殊环境分支。

## False positives

现有 last_only / testreport_only / text_only 分别挑战链内容、报告类型和结构化消费者；
新 chain_assumed / links_omitted / sections_omitted 挑战原生表示、关系文字和附加信息。
它们全部被 mandatory checks 拒绝，未找到“明确违反当前合同却 Overall=true”的补丁。

text_only 在 B03 中仍通过，是重要的分工证据：终端和 JUnit 内容正确不证明完整结构化报告合同。
B02 读取 reprcrash/traceback 并追加 section、二次往返，正确否决了该候选，所以这不是当前 Overall 的 false positive。
同样，chain_assumed 的 A/B/C 全通过，但 D02 已抓住原生表示回归；没有遗漏到最终判定。

这个对照集是针对性选取而非随机抽样，不能给出漏检率、可靠性置信区间或“任意错误修复都能识别”的结论。
没有测试恶意 grader subversion；既有沙箱边界也不等于测量防作弊证明。本阶段不做 Runtime 安全开发。

## False negatives

Complete、Alternative 和归档真实补丁都通过 mandatory。Alternative 使用不同 wire layout，
它的 H02 单一失败仍是修改了不被消费的冗余外层 traceback 后未抛出指定 RuntimeError。
[历史专项证据](../private/qualification/h02_contract_review.md)说明真实 xdist 不做该嵌套变异，
hooks 也没有跨版本固定 schema 承诺。继续记录 H02=false，同时 Overall=true，是当前合同下的正确分类。

本次没有发现有效替代实现被 mandatory 误拒。只有一个替代 codec 对照，不能据此证明所有
等价表示都被接受。D02 的历史测试仍检查部分对象字段及表示行为；若未来提出不兼容这些内部形式
但符合已知消费者的具体实现，需要先按其实际消费行为审查，不能提前宣布它必然有效或无效。

## 覆盖范围与未确认问题

| 候选议题 | 已有证据 | 判定与后续条件 |
|---|---|---|
| 显式 cause / 隐式 context | A01/A02、真实公测；links_omitted 拒绝 | 已有保护，不重复加测 |
| 抑制 context / chain=False | C01/C02；formatter 原始合同 | 是不同的隐藏链条件，保留两个信号；未声称穷尽组合 |
| 无 traceback 的 cause | C03 内容、D03 无新增崩溃；historical 拒绝 | 合法原输入，有明确独立诊断目的 |
| native / 非 chain 表示 | D02 原有 --tb=native 测试；chain_assumed 拒绝 | “完全没测”不成立；不用新增同类 mandatory |
| 附加 sections、stdout/stderr、结构字段 | B01/B02/D01/D02；sections_omitted 与 text_only 拒绝 | 已有行为测试，不应以 wire keys 代替 |
| 重复序列化 | B02 二次往返及真实 Agent 的自检 | 已测再编码；同一 dict 对象被多次解码不是同一合同，原 decoder 会原地转换字典 |
| xdist 与 JUnit | B03 真正执行 gw0 的 call/collect，两条消费者路径 | 覆盖固定版本；不是所有插件证明 |
| 跨版本/异构 codec 回放 | 历史64条互通观测显示多种实现不互通；hooks 明示 experimental | 当前未承诺；新增会改变接受空间，需先独立评审 |
| 每个非最终节点的全部内部字段 | 当前主要要求可见链内容和既有消费者所用结构；真实 patch 本身传递这些字段 | 未找到具体额外消费者或误判补丁，不强制 .chain 布局；仍为研究假设 |
| 任意链深度、更多格式/选项组合、第三方插件 | 四层、部分样式、固定邻近 suite，不是穷尽 | 有限覆盖是事实，但缺口是否导致当前误判尚未确认；先要可复现合同反例 |

所以本轮没有证实需要新增行为要求的 coverage gap。现有要求仍可被进一步挑战，
但不能把尚未遍历的笛卡尔积直接命名为 P1 缺陷。

## 区分力与难度

Patch-level：本次11个对照呈现7种不同四维结果，能区分未修复、共享路径遗漏、结构化兼容错误、
特定回归及有效替代实现。维度不是统计独立：丢链可同时导致 A/B/C 失败，C03 强条件也包含 D03。
保留多个维度的价值是定位行为类别，不是把检查数量相加衡量“推理程度”。

Agent-level：目前仍只有一次有效真实 Agent 试跑；重评归档补丁不增加该样本数。
因此未证明不同 Agent 的区分能力，不能估计通过率。约53秒完成只能说明该次会话在预算内完成；
任务可能因共享编解码入口而局部化，也可能被模型熟悉，但轨迹不能确认后者。
二元 Overall 与四个二元维度在正确方案间会饱和，细分强模型能力可能需要独立任务，而不是本题加难。

下一比较建议：先固定 v0.1.0、题面、源基线、依赖、工具权限及预算，预先选定比较对象和成功/失败报告方式，
再在另一次明确授权下运行独立 Agent。保留所有首次尝试，包括基础设施失败单独分类，不以结果筛选重试。
若要比较稳定能力，应安排预先确定的重复试次与更多独立问题；当前只提出研究计划，不运行新模型、不添加新 Benchmark Issues。
