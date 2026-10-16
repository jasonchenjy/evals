# H02 Behavioral Contract 专项审查

日期：2026-10-16。审查起点：`jasonchenjy/evals` commit `0f7d61daa5bc9b66224db50462e156ac629c0973`。

**选定结果：Outcome B — Implementation-specific Historical Test。** Alternative 确实改变了一个特定畸形输入的处理，但证据没有表明它违反当前任务要求的报告行为。保留 H02 diagnostic-only、原始失败及 Alternative 补丁；不增加 mandatory，不改评分语义。这个结论仅针对 `TestReportSerialization.test_deserialization_failure`，不是认定全部历史测试或畸形输入处理都不重要。

## 1. 实际测试和失败根因

历史测试运行 `def test_a(): assert False`，取得 setup/call/teardown 三个报告中的 call report，调用 `_to_json()`；随后定位 `data["longrepr"]["reprtraceback"]["reprentries"][0]`，先断言其 `type` 为 `ReprEntry`，再改成 `Unknown`。最后调用 `TestReport._from_json(data)`，要求抛出 `RuntimeError`，且消息匹配 `INTERNALERROR: Unknown entry type returned: Unknown`。这不是来自未修改 serializer 的有效原生输入，而是定点破坏内部类型标签的输入。[历史测试：224–244 行](h02_contract_20261016/probes/sources/historical_test_reports.py#L224)

base 中同一测试名为 `test_unserialization_failure`，#5787 将它改名为 `test_deserialization_failure`，关键变异和期望不变。[base 测试：223–243 行](h02_contract_20261016/probes/sources/base_test_reports.py#L223)

即使只有一个异常，base formatter 也返回 `ExceptionChainRepr`。因此这个 `assert False` 报告在 Alternative 中也进入链编码路径，并非因为输入包含多层异常才失败。[producer：815–864 行](h02_contract_20261016/probes/sources/base_code.py#L815)

- **Complete 为什么通过历史测试：** 它先解码外层 `reprtraceback`，发现 `Unknown` 时立即调用错误函数；之后才有机会从 `chain` 构造最终表示。因此外层数据即便在链存在时不决定最终渲染，也会被校验。[解码顺序：450–474 行](h02_contract_20261016/probes/sources/complete_reports.py#L450)、[未知类型分支：414–439 行](h02_contract_20261016/probes/sources/complete_reports.py#L414)
- **Alternative 为什么失败：** serializer 同时保留外层副本和 `causes[*].part`。decoder 发现 `causes` 后递归解码各 `part`，恢复 sections 并直接返回，不再读取外层 traceback。只改外层 `type` 不会破坏真正用于重建的链片段，故恢复正常报告，历史测试报 `DID NOT RAISE RuntimeError`。[编码：182–191 行](h02_contract_20261016/probes/sources/alternative_reports.py#L182)、[提前返回：221–230 行](h02_contract_20261016/probes/sources/alternative_reports.py#L221)
- **不是删除了错误处理：** Alternative 的递归分支仍使用原有 entry decoder，未知的实际消费类型仍调用 `_report_unserialization_failure`。[entry decoder：242–267 行](h02_contract_20261016/probes/sources/alternative_reports.py#L242)、[RuntimeError：283–292 行](h02_contract_20261016/probes/sources/alternative_reports.py#L283)

本次完整 H02 重跑仍为 Alternative **124 passed / 1 failed**，唯一失败位置仍是该 `pytest.raises`。之前的同一结果没有覆盖。[本次真实日志](h02_contract_20261016/qualified/alternative/checks/H02/full-existing.log)、[此前真实日志](oracle_recheck_20261016/qualified/alternative/checks/H02/full-existing.log)

## 2. 合同分类与消费者证据

### A. Required observable behavior

- 在本任务固定环境中，同一实现的 serializer/deserializer 必须保存报告含义：异常链和顺序、报告类型、ordinary reports、sections、captured output 和结构化消费者使用的信息。这些已由 A/B/C/D 的现有必测约束。
- 实际消费的表示若不能被默认 codec 解释，不应悄悄变成一个丢失含义的成功报告。原实现对未知 traceback entry 提供带类型信息的 RuntimeError；本次用 producer 对象级探针确认四个实现保留这一行为。不能进一步推导“所有坏输入必须是 RuntimeError”或“所有替代 codec 都必须使用相同类型标签”。
- 使用现有 hooks 的 xdist 路径必须正常工作。xdist 1.29.0 调用序列化 hook 后仅添加 `item_index` / `worker_id` 等外层元信息；控制端把 payload 交还反序列化 hook，再将报告对象传给消费者。已检查的路径没有改写 `longrepr.reprtraceback.reprentries`。[worker：105–122 行](h02_contract_20261016/probes/sources/xdist_1_29_0_remote.py#L105)、[controller：321–328 行](h02_contract_20261016/probes/sources/xdist_1_29_0_workermanage.py#L321)

JUnit 等消费者随后读取恢复的 report 对象和 `reprcrash.message`，不是这份外层 wire 副本。[JUnit：216–232 行](h02_contract_20261016/probes/sources/base_junitxml.py#L216) 本次及之前的真实 xdist 必测均通过，且补充探针确认外层 worker 元信息仍被恢复。

### B. Implementation-specific expectations

- 固定的嵌套字典路径、`ReprEntry` 字符串标签、外层副本必须成为权威数据，以及必须验证每一份冗余副本，都未被确立为 #5786 的稳定接口合同。H02 此例同时绑定了这些细节和特定错误消息。
- `_to_json` / `_from_json` 是标注 experimental 的私有方法；两个序列化 hooks 在历史 `hookspec.py` 中明确标注 experimental，可在包括 bugfix 的版本间改变，主要面向 core-maintained plugins，未来才可能成为 public hook API。它们是**插件可用的实验接口**，不能简单称为完全不对外，但也没有固定嵌套 wire schema 的承诺。[hooks：381–412 行](h02_contract_20261016/probes/sources/base_hookspec.py#L381)
- pytest 的一般兼容性政策很重视兼容，但不能据此抹去该接口的明确实验性例外。反过来，experimental 也不是任意破坏有效报告行为的许可。[一般政策](h02_contract_20261016/probes/sources/base_backwards_compatibility.rst)
- Complete 和 Alternative 都会忽略外层副本中一次**合法类型的内容改写**，只不过 Complete 仍检查其类型标签。这说明原测试所测还包含解码顺序和冗余校验策略，不能等同于“真正的数据损坏被静默接受”。

### C. Uncertain compatibility assumptions

- 额外第三方插件是否直接修改该内部路径、是否有持久化报告库要求跨版本回放、是否需要混用不同 pytest 编码版本的 worker/controller，当前证据不能覆盖。不能声称没有这类用户，也不能据此把它们自动列入 mandatory。
- 任意畸形 payload 的统一错误类型、错误文本和完整 schema validation 没有发现明确规范。本次未知 report tag 为 AssertionError，删除 `longrepr` 为 KeyError，未知实际 entry 才是 RuntimeError；它们是不同无效输入的既有处理，不自动构成回归。
- 若下一 Runtime 要求混合版本或历史 payload 回放，必须先指定生产者版本、payload 样本和具体消费者，然后建立单独互通合同并重新资格验证。若有实际插件明确依赖外层变异路径，应以该插件的可观察需求重审本结论。

这些不确定项不阻断本次 B 决策，因为当前 Eval 的固定环境和已检查消费者没有依赖该冗余副本。功能资格结论限于这一范围，不能扩展为所有插件/跨版本兼容认证。

## 3. 实际执行的定向探针

脚本：[probe_h02_contract.py](probe_h02_contract.py)、[四控制驱动](run_h02_probes.py)。使用相同 CPython 3.8.20 和固定依赖，在四份独立 base snapshot 上分别应用 no-op、historical、complete、alternative。每个 producer 的精确 JSON 输入、期望说明、返回报告字段或完整异常消息都保存在 `probes/producers/<control>/observations.json`，原生有效 payload 另存 `payloads.json`。所有子进程 argv、cwd、退出码、超时、环境版本和源码/补丁 hash 见 [probes/summary.json](h02_contract_20261016/probes/summary.json)。

每个实现、每种报告类型执行以下有限探针，总计 **56 条输入观测**：

1. 原生 single/chain payload 加上 xdist 实际使用的外层元信息；验证报告内容、最终 crash 信息和元信息的实际恢复。三个修复实现同 codec 保留链；base 保留其已知丢链缺陷。
2. 重现 H02 的外层 `type=Unknown` 变异。Base/Historical/Complete 为上述 RuntimeError；Alternative 恢复未受损的链表示。
3. **对象级未知表示探针：** 在 producer 的真实 traceback 对象中用可渲染的 `Unknown(ReprEntry)` 替代一个实际 entry，再调用默认序列化 hook 和 JSON round trip。没有选择或改写任何序列化字典路径。四个实现、两类报告都抛出含 `Unknown entry type returned: Unknown` 的 RuntimeError。这是判断 Alternative 未移除实际解码拒绝能力的关键证据；不将 subtype 名称作为新评分要求。
4. 外层 entry 保持合法类型，仅把其 `lines` 改为 `outer-copy-only-733`。Base 渲染随之改变；Historical/Complete/Alternative 仍渲染原链。这一实验本身是布局诊断，不是新的 mandatory。
5. 未知 `_report_type` 与删除 `longrepr`：四个实现分别出现 AssertionError、KeyError。记录异常，不把这两个畸形输入记作有效报告回归。

另有 **64 条跨 codec 观测**（4 producers × 4 consumers × 2 report kinds × single/chain），全部传递未修改 producer payload：

- Base → Historical/Complete：两类报告的 single 和 chain 都报 `KeyError('chain')`，因新 decoder 直接索引新字段。
- Base → Alternative：可读取旧 payload；base producer 已丢失的原因信息无法恢复。
- Historical ↔ Complete：本组普通 single/chain payload 互通。
- Complete/Historical → Alternative：single 可恢复，chain 只恢复旧外层末端，丢失原因；Alternative → Complete/Historical 报 `KeyError('chain')`。
- 每个修复实现自身的 single/chain codec 配对可保存这组内容；base 自身仍丢链。

因此**不能宣称这些 Oracle 全部支持跨版本/跨编码互通**；Alternative 也不例外。实验同时说明，“接受一切先前版本 payload”不是当前 Complete Oracle 已满足的隐含规范。判断不只依赖这一结果，还依赖历史 hooks 的明确实验性说明和当前同环境消费者范围。详细记录：[base reader](h02_contract_20261016/probes/noop/cross_codec.json)、[historical reader](h02_contract_20261016/probes/historical/cross_codec.json)、[complete reader](h02_contract_20261016/probes/complete/cross_codec.json)、[alternative reader](h02_contract_20261016/probes/alternative/cross_codec.json)。

四个 producer 和四个 consumer 探针进程均 rc=0、无 timeout；这里 rc=0 表示实验完成并通过对既有未知 entry 拒绝行为的检查，**不表示每个 payload 都成功解码或所有互通组合通过**。每条实际异常均保留。

## 4. 修改与实际再资格验证

仅增加上述探针/证据、本报告、H02 catalog 的 `contract_review` 文档字段，以及资格报告、README 和 changelog 中的说明。四维、mandatory 标志、method、timeout、既有测试、grader、完整/替代/历史/负对照 patch 均未改；保持 Eval **0.1.0**。catalog 文档字段属于锁定文件，因此更新其 SHA256 并在最终锁下重跑全部七个控制；旧锁和旧日志仍保留。

实际命令（从 `/Users/junyuc/Documents/interview/SWE-bench` 执行，输出目录必须全新）：

```sh
python3 evals/pytest_5786/private/qualification/run_h02_probes.py --repo pytest --python evals/pytest_5786/.venv/bin/python --output evals/pytest_5786/private/qualification/h02_contract_20261016/probes
python3 evals/pytest_5786/private/qualification/qualify.py --repo pytest --python evals/pytest_5786/.venv/bin/python --output evals/pytest_5786/private/qualification/h02_contract_20261016/qualified
```

最终完整 grader 结果见 [qualified/summary.json](h02_contract_20261016/qualified/summary.json)：

- No-op：4/11，A/B/C=false，D=true，Overall=false，H02=125 passed。
- Historical：9/11，A/B=true，C/D=false，Overall=false；C03/D03 仍暴露 `reprcrash=None` 的 AttributeError，H02=125 passed。
- Complete：11/11，A/B/C/D=true，Overall=true；H01 两个历史回归通过，H02=125 passed。
- Alternative：11/11，A/B/C/D=true，Overall=true；H01 通过，H02=124 passed / 1 failed。该失败保持诊断可见。
- Last-only：4/11，Overall=false；TestReport-only：7/11，Overall=false；Text-only：7/11，Overall=false。现有负对照仍被拒绝，H02 状态也完整保留。

七个控制的 infrastructure_status 均为 ok，mandatory 无 skip/timeout/execution_error。负对照的 failed/error 不算通过。没有新增 Mandatory Test，因本次没有确认一个未被评分捕获的 required-behavior 回归。

## 5. 结论与下一阶段

H02 diagnostic-only 对**这个具体失败**有充分依据。不能因为 Alternative 失败就删掉诊断，也不应为了得到该特定 RuntimeError 而强制所有有效实现解析一份未被消费的副本。若后续出现实际消费路径上的有效信息丢失，应按 Outcome A 的要求建立行为测试，而不是沿用本次 B 结论掩盖新问题。

本 Eval 的当前功能资格足以**开始实现 Agent Pilot Runtime**。运行真实不可信 Agent trials 仍需隔离 Runtime、私有数据边界和资源限制；本轮没有实现这些能力，也没有做模型比较。功能结论只覆盖固定版本、已验证消费者和平台；对抗性 malformed-input 防护、未检查插件和跨版本互通仍不在已资格范围。

历史材料及评分不变的校验见 [integrity.json](h02_contract_20261016/integrity.json)；引用源码的身份和固定依赖来源见 [source_evidence.json](h02_contract_20261016/source_evidence.json)。
