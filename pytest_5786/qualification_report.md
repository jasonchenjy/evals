# Eval 0.1.0 资格报告

## 2026-10-16 H02 合同专项审查

选定 **Outcome B**：`test_deserialization_failure` 破坏的外层 entry 是 Alternative 的冗余副本；实际消费的未知表示仍被明确拒绝。历史 hooks 明确允许包括 bugfix 在内的版本间变化，固定嵌套 wire 布局和全部冗余副本校验不是已确立的本题合同。四个实现的定向探针还确认：Historical/Complete 无法读取 base 的部分旧 payload，Alternative 也不支持所有跨编码链互通；这些限制保留，不假称全面向后兼容。

H02 保持 diagnostic-only，Alternative 的 124 passed / 1 failed 保留；未修改任何 Oracle、既有测试、grader 或评分语义，版本仍为 0.1.0。catalog 仅新增审查说明，核心锁随文档字段更新，并重新执行全部七个资格控制。Complete/Alternative 的 11 项必测通过，no-op、historical 和三个负对照仍被拒绝。详细代码依据、56 条输入观测、64 条互通观测和 A/B/C 合同分类见 [专项报告](private/qualification/h02_contract_review.md)；最新运行见 [资格结果](private/qualification/h02_contract_20261016/qualified/summary.json)。此结论只解释该项历史失败，不替代对其他诊断失败的逐项审查。

## 2026-10-16 Complete Oracle 专项复核

**最新结论：Complete Oracle 已通过完整 Eval 和补充的真实 serial/xdist 验证。Oracle 源码补丁无需更改；本轮发现并修复的是 Git 仓库化后出现的资格执行缺陷。** 本节记录最新复核；下文初始资格结果和原始日志保留，不追改历史记录。

完整机器证据见 [专项复核 summary](private/qualification/oracle_recheck_20261016/summary.json)。Complete Oracle 仍是 [complete.patch](private/oracle/complete.patch)，SHA256 `767fe3bc51d431784b7cb1af61b0f4be5253f7e6cb86c5919cef81599c150c5d`；原始 [historical.patch](private/oracle/historical.patch) 和所有既有控制补丁均保持原字节。

### 检查发现与实际修改

原 Complete Oracle 已在 `serialize_repr_crash` 和 `deserialize_repr_crash` 中分别保留 `None`，非空值继续使用 `ReprFileLocation` 编解码。检查 base producer 的 native traceback 分支和后续修复 `0e0006934019aba7a3bbec95e2fac7c1b82d1063` 后，未发现该实现不满足本题合同的功能缺陷；没有为了“产生修复”而重写正确的 Oracle。

本次首次重跑却发现所有控制态都表现为 base。根因是上一轮将 `evals/` 初始化为 Git 仓库后，普通私有 snapshot 位于该 Git 工作树的子目录；`git apply` 向上发现维护者仓库，对不符合子目录前缀的 patch 路径静默跳过，退出码仍为 0。源码补丁和 curator 历史测试补丁都未实际应用。此首次运行是无效资格证据，不能归为 Complete Oracle 失败；原始记录保存在 [缺陷复现](private/qualification/oracle_recheck_20261016/git_context_defect.json) 和 `oracle_recheck_20261016/grader/`，不覆盖或美化结果。

修复范围限于资格执行：`private/grader.py` 清除继承的 `GIT_*` 上下文、设置 snapshot 的 Git ancestor discovery 边界，并隔离系统/用户 Git 配置；`--numstat` 校验在独立临时目录解析；源码与历史测试补丁共用相同的应用路径。结果额外记录实际应用后的源码 SHA256、历史测试 patch SHA256 及其应用命令。新增“父目录是 Git 仓库、snapshot 被 ignore、同时继承 GIT_DIR/GIT_WORK_TREE”的回归测试，7 个 grader contract tests 全过。这个 Git 边界只修复路径语义，不构成代码执行安全沙箱。

`private/tests/behavior.py`、catalog、既有测试 inventory、评分阈值、全部 Oracle/负对照 patch 均未改。Eval 任务仍为 experimental v0.1.0；本次属于资格执行修复，比较和重放时必须同时标识最新 `checksums.json` 的 hash，不能把初始锁与当前锁混用。旧核心锁保存在 [core_lock_before.json](private/qualification/oracle_recheck_20261016/core_lock_before.json)。

### 完整 grader 重跑

- Complete：A/B/C/D 全通过，Overall=true，11/11 mandatory；H01 两个历史测试通过，H02 相邻完整旧 suite 125/125 通过。
- No-op：A/B/C 失败、D 通过，Overall=false，4/11 mandatory；原始 bug 可复现，未受影响行为保持可测。
- Historical：A/B 通过、C/D 失败，Overall=false，9/11 mandatory；C03/D03 均因 `reprcrash=None` 触发 AttributeError。125 个相邻旧测试通过，仍不足以满足扩展合同。
- Last-only：4/11，Overall=false；TestReport-only：7/11，Overall=false；Text-only：7/11，Overall=false。三个刻意不完整的修复都被拒绝。
- Alternative：11/11，Overall=true；保留 H02 的 124 passed / 1 failed wire-layout 诊断差异，没有改变其判定地位。

最终七个控制均 `infrastructure_status=ok`，无 mandatory skip、timeout 或 execution_error。负对照中的 failed/error 是实际功能结果，不是通过。逐控制实际 argv、退出码、四维状态、补丁 hash、解释器/完整依赖版本、stdout/JUnit 和错误栈均在 [qualified/summary.json](private/qualification/oracle_recheck_20261016/qualified/summary.json) 引用的文件中。

### 补充跨组件验证

此前 C03/D03 覆盖了缺失 traceback 的报告往返，而 B03 的真实 xdist 输入是普通异常链。本轮新增独立资格脚本 [verify_oracle_behavior.py](private/qualification/verify_oracle_behavior.py) 补齐这两者组合的证据，**不加入或更改 mandatory catalog**。

每个控制运行 32 项补充检查：16 项覆盖显式/隐式、普通/缺失 traceback、TestReport/CollectReport、直接 hooks/真实 JSON 的两次往返，并检查结构化消费者、sections 和 captured output；另 16 项覆盖同样四类异常输入的 serial/xdist、测试失败/收集失败。实际 worker 必须是 gw0，控制端和 worker 端异常表示须逐字一致，终端和 JUnit 必须保留原因、末端异常及顺序；还检查最终 crash message、traceback entries、预期退出码和没有 INTERNALERROR/AttributeError。

最终补充结果：[supplemental_final/summary.json](private/qualification/oracle_recheck_20261016/supplemental_final/summary.json)。Complete **32/32 passed，0 skipped**；No-op **8/32 passed**，其余 24 项暴露传输丢链；Historical **20/32 passed**，8 项结构化检查 error、4 项真实 xdist 检查 failed，均与缺失 traceback 的崩溃一致。serial 的预期测试失败退出码为 1、收集失败为 2；xdist 两类均为 1。没有用非零退出码直接认定报告错误。

补充脚本初版有四个误报：把含 worker banner 的 controller `report.longreprtext` 与 worker 端全文直接比较。base `BaseReport.toterminal` 合法添加该标识，因此修正为比较 `str(report.longrepr)` 的完整异常表示，同时保留文本、顺序、worker 和结构断言。该迭代及初版脚本留在 `supplemental/`，不是放宽现有必测标准；`supplemental_probe/` 还保留了 Git 上下文修复前的运行。

### 独立性与保存边界

[独立性审计](private/qualification/oracle_recheck_20261016/independence.json) 验证：Oracle 只改 `src/_pytest/reports.py`，不改测试；grader 的得分由行为观测与 catalog 决定，不比较提交与 Oracle 的内容或 hash。控制面的包完整性检查确实会校验 Oracle 文件 hash，这是材料身份校验，不是评分依据。不同 wire 编码的 alternative 仍通过 mandatory。

重新导出 Agent payload 并核对 443 个 base 文件，只增加公开题面、公开示例、公开依赖、公开元信息和生成版本 shim；单一 synthetic commit、无 remotes、无 hidden tests/Oracle。普通本机目录仍可被向上遍历，公私 allowlist 是交付边界，不冒称宿主隔离。既有研究、原始 ground truth、历史 patch 和所有旧资格日志保持不变；见 [integrity.json](private/qualification/oracle_recheck_20261016/integrity.json)。

### 实际命令与 Pilot 判断

复用 CPython 3.8.20 及已有固定依赖；没有重新安装环境。以下命令从 `/Users/junyuc/Documents/interview/SWE-bench` 实际执行，输出目录必须全新：

```sh
python3 evals/pytest_5786/private/qualification/test_grader_contract.py
python3 evals/pytest_5786/private/qualification/qualify.py --repo pytest --python evals/pytest_5786/.venv/bin/python --output evals/pytest_5786/private/qualification/oracle_recheck_20261016/qualified
python3 evals/pytest_5786/private/qualification/run_oracle_verification.py --repo pytest --python evals/pytest_5786/.venv/bin/python --output evals/pytest_5786/private/qualification/oracle_recheck_20261016/supplemental_final
python3 evals/pytest_5786/prepare.py --repo pytest --destination evals/pytest_5786/.artifacts/agent_oracle_recheck
```

**功能层面的 Oracle/Eval 资格已满足；尚不能直接启动不可信 Agent Pilot Trials。** 仍需下一阶段提供隔离 Runtime、真实资源和网络限制及私有资料隔离。只验证了 macOS arm64/Python 3.8.20/单 xdist worker；未证明跨平台、跨版本 wire 互通、全面插件兼容或对抗性防作弊。没有调用 Coding Agent、实现 Runtime 或改变模型比较标准。

## 初始 package creation 资格记录（原结果保留）

日期：2026-10-16。结论：**本机确定性控制资格通过；不可信 Agent 执行设施仍未资格验证。** 最终运行是 `private/qualification/qualified_v0_1_0`，其余 `run_01`～`run_03`、`final` 和 `final_v0_1_0` 为构建迭代记录。没有执行真实 Agent Trials，没有运行模型比较。

## 四个维度的准确含义

- **A / 原始问题：** 显式二层 cause 与隐式三层 context 经报告 hooks 和真实 JSON 往返后保留消息、次序、连接说明。
- **B / 跨组件：** TestReport 与 CollectReport、report metadata、captured output、longrepr sections、仍可被消费者使用的 traceback/crash 信息；真实 xdist worker/controller 的测试失败及收集失败都保留终端和 JUnit 诊断。
- **C / 边界：** `raise from None`、四层链、历史 `chain=False` rendering option、合法缺失 traceback 的原因信息完整性。来自原 producer 和 Python 语义，不是新造输入要求。
- **D / 非回归：** 普通 passed/skipped/string/single-error report、额外属性、118 个既有用例，以及缺失 traceback 原因不能引入新崩溃。D03 仅要求 base 已支持的“不崩溃”，C03 才要求原因内容完整，避免把 no-op 的原始缺陷误记为新增回归。

本版本有 **11 个 mandatory checks + 2 个 diagnostic checks**。每项来源、要求、预期、覆盖理由及超时都在 [private/test_catalog.json](private/test_catalog.json)。唯一主结果为全部 mandatory 满足；无加权总分。一个 check 内的子场景必须全部满足，未对其求平均。

## 实际控制结果

| 控制 | A 原始问题 | B 跨组件 | C 边界 | D 非回归 | Overall | 必测通过 | 诊断 |
|---|---|---|---|---|---|---|---|
| noop | 未通过 | 未通过 | 未通过 | 通过 | false | 4/11 | H01 failed; H02 passed |
| historical | 通过 | 通过 | 未通过 | 未通过 | false | 9/11 | H01 passed; H02 passed |
| complete | 通过 | 通过 | 通过 | 通过 | true | 11/11 | H01 passed; H02 passed |
| alternative | 通过 | 通过 | 通过 | 通过 | true | 11/11 | H01 passed; H02 failed |
| last_only | 未通过 | 未通过 | 未通过 | 通过 | false | 4/11 | H01 failed; H02 passed |
| testreport_only | 通过 | 未通过 | 未通过 | 通过 | false | 7/11 | H01 failed; H02 passed |
| text_only | 通过 | 未通过 | 未通过 | 未通过 | false | 7/11 | H01 failed; H02 failed |


所有 7 个控制的 `infrastructure_status=ok`，没有实际 mandatory skips 或超时。完整机器结果：[private/qualification/summary.json](private/qualification/summary.json)。每个控制的全部命令、Python/packages、原始日志与逐项结果分别见：
- [noop](private/qualification/qualified_v0_1_0/noop/result.json)；result SHA256 `8dab95679f33d4484e81610609f9d328c27eb44ccf91425f333aa15b842a3177`。
- [historical](private/qualification/qualified_v0_1_0/historical/result.json)；result SHA256 `f0ee0f60fb093e065e7a6b3a2d19326642b13cae5b2e650a8975142b7080da81`。
- [complete](private/qualification/qualified_v0_1_0/complete/result.json)；result SHA256 `af635f9ee64952a27e5111b3b21e4b6a96a85b8288b20ecc625af1d319435530`。
- [alternative](private/qualification/qualified_v0_1_0/alternative/result.json)；result SHA256 `0393c23842488ea95abd814edbb5379f968150f8658ee900b5c53d02e5d250af`。
- [last_only](private/qualification/qualified_v0_1_0/last_only/result.json)；result SHA256 `f467ab4be2300b75ed923c50d683199829241eba0488d6297ed4e3fddcd4def1`。
- [testreport_only](private/qualification/qualified_v0_1_0/testreport_only/result.json)；result SHA256 `ec2c4225596950e34e42a7a884bdf159c2e3c394be9274c34683f9d8416e3ebb`。
- [text_only](private/qualification/qualified_v0_1_0/text_only/result.json)；result SHA256 `dc132804cde729597066e70930643fdf429bef38df1a712174ba5804c2dba9f5`。

**No-op：** 原始 A 两项失败，未误授整体成功；D01、D02、D03 都通过。H01 精确历史测试为 2 failed；H02 全旧 suite 为 125 passed。

**历史参考：** A/B 通过，H01 两个历史回归都 passed，125 个既有测试也 passed；C03 与 D03 为 AttributeError，证实它只是 partial oracle。该异常是功能回归，不是基础设施失败。

**完整 oracle：** 11/11 mandatory、H01 两例、H02 125 个既有用例全部通过，无 skip/timeout/infra error。其实现是历史链方案加上独立审查的 None 编码/解码处理；用后续 #5971 作为证据，但资格由实际行为验证。[Bugbot 本轮单独复核记录](private/oracle/review.md) 明确不是第三方独立审查。

**负对照：** `last_only` 保留末端和结构却丢原因，被 A/B/C 拒绝；`testreport_only` 的 A 通过，但 CollectReport 和真实 collection transport 被 B/C 拒绝；`text_only` 连真实 xdist 可见文字都正确，仍因丢掉报告结构被 B02、D01/D02 拒绝。历史参考另外覆盖“普通链正常、缺失 traceback 崩溃”边界。

**替代实现：** 使用原 BaseReport 方法及递归扁平 codec，并采用不同 chain wire shape，11/11 mandatory 与 H01 通过。H02 是 **124 passed、1 failed**；失败为 `TestReportSerialization.test_deserialization_failure`，它修改旧布局的外层 reprentry 而该实现从另一链载荷读取信息。这项属于预先设为 diagnostic 的具体 wire mutation；没有改测试来让替代实现通过。该结果证明 grader 没有强制这一个布局，不证明所有替代解都公平、或所有跨版本/恶意损坏载荷都受支持。

## 既有测试与诊断策略

118 个 mandatory 既有测试的精确 inventory 在 [private/tests/existing_inventory.json](private/tests/existing_inventory.json)。它来自固定历史测试的已验证收集结果，grader 比较 ID 列表和数量，并拒绝任何 skip/error/failure，而非仅比较返回码。

完整相邻 suite 共 125 个旧测试（不含新增历史链测试）。其中 7 个实现布局检查只进入 H02：`test_xdist_longrepr_to_str_issue_241`、`test_deserialization_failure`、`test_paths_support`，以及 TestHooks 的 `test_test_report`、`test_collect_report`、`test_invalid_report_types` 两参数化实例。它们分别检查具体 wire 字段/嵌套结构或直接修改 `_report_type`。对应可观察行为由 A/B/D 的 hooks round trip、path 属性、报告类型和消费者检查覆盖。此选择是静态 contract 审查决定，发生在观察最终替代实现 H02 失败之前。

H01 是未改的 #5787 两个历史 focused tests，但其精确 ExceptionChainRepr 类型/chain 断言只作诊断；原始行为已由 A/B 的 independent assertions 强制。历史 helper 的迁移和完整 testing diff 仍一并应用，防止只摘函数导致伪失败。

## 环境和实际执行

CPython **3.8.20**，macOS arm64；pytest 精确源码 base SHA `955e54221008aba577ecbaefa15679f6777d3bf8`；xdist **1.29.0**。完整 pins 见 [requirements.txt](requirements.txt)，最终 freeze 见 [private/qualification/environment_freeze.txt](private/qualification/environment_freeze.txt)。本轮额外安装 decorator 4.4.2、Jinja2 2.11.3、MarkupSafe 2.0.1，因此上一阶段的两个 optional skips 本轮确实执行通过，未静默排除。

本轮环境安装第一次在 sandbox 中发生 uv/macOS system-configuration panic；经授权重试成功。初次自动依赖求解还安装了现代 pytest 与它的 transitive packages，随后全部移除，测试始终从固定 src 加载。未来安装说明已指定 `--no-deps`。这些是已解决的环境构建记录，不混进 Agent failure。详见 [private/qualification/setup_commands.json](private/qualification/setup_commands.json) 与 [private/qualification/install.log](private/qualification/install.log)。

实际资格命令：

```sh
cd /Users/junyuc/Documents/interview/SWE-bench
python3 evals/pytest_5786/private/qualification/test_grader_contract.py
python3 evals/pytest_5786/private/qualification/qualify.py --repo pytest --python evals/pytest_5786/.venv/bin/python --output evals/pytest_5786/private/qualification/qualified_v0_1_0
python3 evals/pytest_5786/prepare.py --repo pytest --destination evals/pytest_5786/.artifacts/agent_export
```

完整逐控制命令包括 Python 路径、patch、输出目录；每个 check 还记录自己的 argv/cwd/返回码/耗时。B03 在两个独立目录执行 `python -m pytest --color=no -q -p xdist.plugin -n 1 --tb=short --junitxml=report.xml test_transport.py`，并在输入模块中确认 worker 环境 `gw0`。两个内层失败是预期负载，外层检查它们完整且可消费地报告错误。

所有 Python 源码从固定 Git archive 重建；测试 patch 只进入私有评分快照。最小 `_version.py` 是相同的 `5.1.0` 包装 shim，非精确发行标识。环境在应用提交前 preflight；之后执行中的错误按 check 状态记录。基础设施检查另外实跑了错误 Python 和缺少可信本机确认标志，两者均返回 **rc=2、infrastructure_status=error、overall=false**；见 [private/qualification/infrastructure_checks.json](private/qualification/infrastructure_checks.json)。

6 个 grader contract tests 全通过，覆盖全部 mandatory 非通过状态、少跑/重复/额外 ID、合法控制补丁、越界/测试/生成版本/模式/binary 修改与超限补丁拒绝、真实子进程 timeout。见 [private/qualification/grader_contract.log](private/qualification/grader_contract.log)。这些控制面测试不算 Coding Agent 能力得分。

公开导出示例还分别实跑了 serial 与 xdist：两边都为预期的 2 failed，但 base serial 保留六个错误消息、xdist 只剩末端 13/23，确实复现原问题。命令和原始日志见 [private/qualification/public_examples/result.json](private/qualification/public_examples/result.json)。

导出审计确认仅增加 TASK.md、eval_public.json、公开示例、公开 requirements 和生成版本模块；无 private/research/reference patch，上游 Git history 不存在，只有一个 synthetic commit、零 remotes。见 [private/qualification/export_check.json](private/qualification/export_check.json)。

## 开发迭代与未资格范围

保留初次缺少锁文件导致的启动失败、JUnit system-out 解析错误、failed/error 分类调整、wire-layout 检查剥离与 C/D 拆分记录。最终目录的结果替代早期 run_* 作为 v0.1.0 证据；没有依据 Agent 成绩挑选评分规则。

未资格项目：安全执行任意恶意源码、网络/CPU/memory/disk 的真实运行时隔离、Linux/Windows、更多插件与多 worker 组合、跨版本 wire 互通，以及全面的替代解公平性。完整 oracle 通过表示符合这 11 个 mandatory 合同，不代表整个 pytest 全项目无缺陷。公开 Verified 污染无法排除，单题没有统计模型区分力证据。

下一 Runtime 的准确输入是 export 出的 Agent workspace 与预算，输出是 source diff；私有控制面输入该 diff，输出 schema_version=1 的 result.json。其隔离 worker 适配要求见 [README.md](README.md)。本阶段停止于 Eval 创建和控制资格验证。
