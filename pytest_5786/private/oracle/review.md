# Oracle 与 grader 正确性复核

日期：2026-10-16。按用户选择的 Bugbot 审查路径执行。当前没有 `subagent_type=bugbot` 工具，因此按 review-bugbot 技能在本轮直接复核，没有启动或冒称独立 reviewer。下面是与构建步骤分开的代码审查记录，不是第三方独立背书。

## 范围与方法

审查完整 oracle 相对固定 base 的 diff、替代实现、三个刻意不完整的 source patch，以及 prepare、grader、check、行为测试、catalog 和结果聚合。审查不以“复制历史 patch”代替正确性判断；结合 producer 的 None/native 分支、现有报告消费者和最终资格日志。

## Oracle 审查

- 完整 oracle 使用 #5787 的链传输实现，再分别修正 crash 对象的编码与解码：输入 None 保持 None，有对象时走原有 ReprFileLocation 编解码。没有创建虚假文件位置，也没有把缺失 traceback 解释为丢弃整个原因。
- producer 的 native fallback 仍经 ReprEntryNative 路径处理；每段 description 次序及最后一个异常的 reprcrash 语义保持。普通 report、sections、额外属性和终端消费者没有被替换为字符串。
- 无 traceback 的已知输入同时由 C03 验证原因信息完整性、D03 验证不引入新崩溃。完整 oracle 在两个报告类型上都通过；历史参考在二者均暴露 AttributeError。
- 替代实现保留 BaseReport 的原有方法，并递归复用扁平 codec，采用 `causes` / `part` / `link` 的不同 wire layout。它通过全部声明的必测行为，但不声称与历史内部 wire layout 的所有测试等价。
- 替代实现的 H02 有一个诊断失败：旧测试破坏外层冗余 `reprtraceback` 入口并期待 RuntimeError；替代实现从 `causes` 读取权威链，因此该具体 wire mutation 不再有效。这是已保留并报告的实现耦合诊断，不是被悄悄删掉的失败。是否要求跨版本 wire 兼容及通用损坏包策略，需后续明确规范；当前同版本 worker/controller 合同不含该要求。

## 构建中发现并修正的问题

| 问题 | 修正与验证 |
|---|---|
| 将 JUnit testcase 的所有子节点都当失败会误判正常 system-out | 仅忽略 system-out/system-err/properties；failure/error/skipped 等仍拒绝。最终既有 suite 精确 118 条零跳过通过 |
| 缺失目标消息用 str.index 直接报 ValueError，模糊了功能失败分类 | 先 assertIn，再比较次序；no-op / final-only 的原缺陷现明确记录 failed |
| 原先 C03 同时决定 C/D，会把 no-op 原有信息丢失也标成新增回归 | 分离 C03 完整性与 D03 不崩溃。最终 no-op D=true，历史参考 D=false |
| 旧测试的 wire key 断言可能强制历史实现 | 在观察最终 H02 之前将 7 个 wire-specific 检查移到诊断集；用 B/D 的独立 round-trip 行为断言补充。替代实现 primary=true，H02=false，两者都保留 |
| 只看进程退出码或少跑测试可能产生假成功 | 外层 stdlib unittest、固定方法/用例 ID、精确 118 条 inventory、结果状态与退出码双检；6 个 grader contract tests 全过 |
| 补丁先完整读入内存再检查 1 MiB 大小限制 | 在读取前先检查 stat 大小，读取后再次检查；更早的 provenance 哈希改为 64 KiB 分块读取，避免绕过该内存限制；超限输入纳入拒绝测试 |

## 最终审查结论与限制

Bugbot found no bugs in the reviewed declared-behavior qualification path after these fixes. 这是本轮 in-place review 的结论，范围限定为已审阅的确定性控制路径。

未认证任意恶意补丁的安全执行或防作弊能力。Python 候选代码与 worker 检查仍共享解释器，刻意破坏测试框架/伪造结果不是此版本已解决的问题。外部沙箱可保护宿主与资料隔离，但不能单独证明结果防篡改；下一 Runtime 阶段仍需可信控制面、只读挂载、资源/网络限制以及针对刻意 grader subversion 的独立措施。宿主本次只运行了明确构造并审阅的控制补丁。

没有发现需要继续修改 oracle 的已验证功能缺陷；这不证明不存在未覆盖的插件、平台或异常表示组合。没有 Agent Trials、模型比较或统计区分度结论。
