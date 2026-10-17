# Stage 4 proposal — retain pytest_5786 v0.1.0

分析起点：`e0a3148`。先审查合同、原补丁、原 grader 与历史资格，再创建三个小型诊断控制。
本提案写于评分实现变更之前；本阶段**没有计划修改评分实现**。
目前没有得到足以支持 P0 或 P1 评分变更的证据。建议保留 v0.1.0，补充解释性报告和可复现诊断控制。

| ID | 级别/状态 | 证据及受影响能力 | 建议 | 收益 | 过拟合/误拒风险 | 实施判断 |
|---|---|---|---|---|---|---|
| F01 | P2 / CONFIRMED | D02 是118个测试的复合信号；chain_assumed 的准确失败是原生 traceback 表示序列化，单看 D=false 看不出该点 | 在本阶段诊断 JSON/Markdown 中展开失败 check、可见异常和相关源码差异 | 提高归因精度，不增加测试 | 不把固定子测试名字当 Agent 答案要求；类别仅描述观察 | 实施报告层补充，不改 grader |
| F02 | P2 / NOT_SUPPORTED | “native/非 chain 表示完全未覆盖”假设被 chain_assumed 的 D02 失败反驳；原测试明确使用 --tb=native | 不新增重复 mandatory check | 保持检查集紧凑 | 只证明此错误已捕获，不声称所有表示组合穷尽 | 不改 Eval；保留诊断补丁 |
| F03 | P2 / CONFIRMED | links_omitted 与 sections_omitted 被现有检查拒绝；共享损失会引发多维失败；C03 的强要求包含 D03 的主要行为 | 文档明确检查相关性、C03/D03 的诊断区别，不求加权总分 | 避免把多个关联失败误当多种推理缺陷 | 删除 D03 会丢失 no-op 与 historical 的回归区分 | 仅完善能力矩阵和解释 |
| F04 | P2 / CONFIRMED | Alternative 的 H02 失败绑定冗余 wire 副本；历史合同审查和既有消费者没有固定 schema 要求 | 保持 H01/H02 diagnostic-only，保留原始失败 | 保持不同实现的接受空间 | 该结论只适用于已审查的特定失败，不能免除真实消费者回归 | 维持既有政策，不改评分 |
| F05 | P2 / PLAUSIBLE | 额外插件、跨版本 payload、较早链节点的结构字段、更多选项组合未全部枚举；当前没有消费者反例或误判补丁 | 若将来有具体消费者/合法输入反例，再先定义合同、构造最小复现 | 防止隐藏要求膨胀 | 直接断言 .chain 或固定 wire key 会排斥正确替代实现；跨版本要求甚至改变现有 Oracle 合格性 | 不实施；若改变接受空间须单独评审 |
| F06 | P2 / CONFIRMED | 只有一个有效真实 Agent 样本，约53秒全通过；对照补丁不是独立 Agent 样本 | 固定环境/题面/预算并预先定义多 Agent 比较计划；未来考虑独立问题样本 | 测量 Agent-level discrimination，而非调低某次分数 | 按已知通过补丁定制更难测试会过拟合；单任务可能有公开历史记忆影响 | 提出计划，不启动新模型、不添加新题 |
| F07 | P2 / NOT_SUPPORTED | “一次快速通过表明当前 Eval 太简单，必须加难”没有样本支持；本次已区分明确的错误补丁 | 保持原行为要求和预算，报告样本限制 | 不以模型失败为目标优化 Eval | 约53秒完成可能反映模型能力、任务局部性或熟悉度，无法仅靠轨迹区分 | 不改任务或评分 |

没有确认 false positive / false negative，也没有确认需要新增 mandatory 的 coverage gap。
F05 是待研究范围，不是已证实 bug。没有材料评分变化，因此不创建新 Eval 版本，原 lock 与基线保持不变。

验证计划：对七个原控制、归档的 first-real patch、三个新增诊断控制，使用既有受限 worker 与原 grader
各执行一次完整评分；比较原91项状态、原 Agent 的13项状态，并保存所有13项诊断。
对照失败属于候选行为；infrastructure_status 必须全为 ok，不能用基础设施异常替代有效拒绝。

执行完成后依据见 [diagnostic_results.json](diagnostic_results.json) 和 [最终报告](stage4_report.md)。
这是归档补丁重评，不是新 Agent Trial；零模型调用、无真实认证、worker 无网络。
