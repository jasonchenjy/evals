# Diagnostic control results

A/B/C/D 是四维布尔结果，1=通过。所有11个补丁均在精确基线上应用成功，infrastructure_status=ok。

| Control | A/B/C/D | Overall | 失败 mandatory | 失败 diagnostics |
|---|---|---|---|---|
| chain_assumed | 1/1/1/0 | False | D02 | H02 |
| links_omitted | 0/0/0/1 | False | A01, A02, B01, B02, B03, C02, C03 | H01 |
| sections_omitted | 1/0/1/0 | False | B01, B02, D02 | H01, H02 |
| first_real | 1/1/1/1 | True | 无 | 无 |
| noop | 0/0/0/1 | False | A01, A02, B01, B02, B03, C02, C03 | H01 |
| historical | 1/1/0/0 | False | C03, D03 | 无 |
| complete | 1/1/1/1 | True | 无 | 无 |
| alternative | 1/1/1/1 | True | 无 | H02 |
| last_only | 0/0/0/1 | False | A01, A02, B01, B02, B03, C02, C03 | H01 |
| testreport_only | 1/0/0/1 | False | B01, B03, C02, C03 | H01 |
| text_only | 1/0/0/0 | False | B02, C03, D01, D02 | H01, H02 |

原七控制91项状态、归档 Agent 的13项状态均与历史一致。总计143项检查；3项新诊断控制均拒绝。
历史参考的 C03/D03 以及 text_only 的部分 error 是已完成检查捕获的候选异常，不是基础设施失败。
165个 worker 收据确认停止并删除；188个精选文件哈希校验通过。

## 新诊断的解释

- **chain_assumed（预期 D）**：混淆结构化表示与链表示，D02 的 `test_reprentries_serialization_196` 报 ReprExceptionInfo 无 chain 属性；A/B/C 均通过。说明原生表示回归已有保护，无需重复加测。
- **links_omitted（预期 A，级联 B/C）**：节点消息仍在，但 cause/context 关系文字消失。A01/A02 及 B/C 相关检查拒绝，D 全通过。信息完整性不能只查消息存在。
- **sections_omitted（预期 B，兼有 D 回归）**：恢复 exception 对象时遗漏 addsection。B01/B02 直接检查附加内容失败，D02 的既有附加信息测试也失败；B03 和 A/C 仍通过。

三者均是在 Complete Oracle 上引入一个明确的工程遗漏，再生成相对固定 base 的完整补丁；没有修改原 Oracle、按测试 ID 分支或匹配固定消息。
生成步骤见 [build_diagnostics.py](build_diagnostics.py)；所有实际失败文本、check 状态与源码说明见 [diagnostic_results.json](diagnostic_results.json)。
此有限样本内未发现 false positive；不能据此估计任意错误补丁的漏检概率。
