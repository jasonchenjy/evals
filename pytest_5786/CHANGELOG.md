# Changelog

## 0.1.0 资格执行修复与 Oracle 专项复核 — 2026-10-16

- Complete Oracle 原已正确处理 crash 编码/解码的 None，源码补丁保持不变；没有发现需要修改 Oracle 的已验证合同缺陷。
- 修复 `evals/` 仓库化后 `git apply` 向上发现维护者 Git checkout、静默跳过 snapshot 补丁的资格缺陷；清除继承的 Git 上下文并限制 ancestor discovery，统一源码和 curator 测试补丁的应用路径。
- 结果增加应用后源码 hashes 和历史测试 patch 身份；新增父 Git 仓库及继承 GIT_DIR/GIT_WORK_TREE 的回归测试。7 项 grader contract tests 通过。
- 原 mandatory 测试、catalog、评分规则及历史/完整/替代/负对照补丁均未变；完整 grader 七个控制按预期重获资格。Complete 11/11 mandatory、2 个历史回归、125 个相邻旧用例全过。
- 新增独立补充验证：两类报告、hooks/JSON、显式/隐式、正常/缺失 traceback、serial/真实 xdist、call/collect 共 32 项。Complete 32/32；base 和历史控制按预期暴露丢链或缺失 traceback 崩溃，无 skips。补充项不改变主评分。
- 首次 Git 上下文导致的无效运行、补充断言对 xdist banner 的误报和随后修正均保留。历史研究、ground truth、patch 和资格日志不覆盖。
- task version 仍为 experimental 0.1.0；当前核心锁与旧锁分开保存，后续重放须同时记录锁 hash。功能 Oracle 可交给下一 Runtime 阶段，隔离设施仍未实现，不宣称可以安全运行任意 Agent 提交。

最新证据：[专项复核结果](private/qualification/oracle_recheck_20261016/summary.json)；完整解释见 [资格报告](qualification_report.md)。

## 0.1.0 — 2026-10-16 — experimental / qualification-only

首次固定 pytest #5786 单任务 Eval；没有模型运行时或自动扩题系统。

- 原始要求：本地与 xdist 对显式/隐式异常链提供一致有效诊断，提交实际源码修复，保持普通报告行为。
- 有依据的合同扩展：TestReport/CollectReport、sections、消费者结构、上下文抑制、chain=False、不同链长、缺失 traceback。后者由 base producer 支持且 #5971 独立报告历史回归，未为增加难度而新造规范。
- 11 个 mandatory 分 A/B/C/D，2 个 historical diagnostic；C03 内容完整性与 D03 不引入新崩溃分开，避免混淆原缺陷与回归。完整源依据见 test_catalog.json。
- 评分采用 all-mandatory conjunction，拒绝 skip、少跑、失败收集、超时和不合法结果；保持四维原始状态，不引入任意加权分数。
- 控制态包括 no-op、历史 partial oracle、完整 oracle、另一 codec，以及 last-only / TestReport-only / text-only；历史参考同时是 missing-traceback negative control。
- 完整 oracle 11/11 mandatory，两个诊断均过；替代实现 11/11 mandatory，1 个旧 wire-layout diagnostic 失败明确记录。其余控制都按预期未整体解决。6 项 grader contract tests、2 项 infrastructure guards 和 export allowlist check 通过。
- 使用 Python 3.8.20、固定历史源码与 pins；新环境补齐旧研究的 optional test dependencies。`_version.py` 为固定 packaging shim，不冒称精确 release 版本。
- 公私分离通过 allowlist exporter 实现逻辑交付边界；仅一个 synthetic Git baseline。普通目录/venv 不视为安全沙箱；不可信代码与跨平台运行尚未资格验证。
- 已执行核心文件锁定在 checksums.json；最终文档与结果单独在 delivery_hashes.json 封存。

## 迭代规则

先在开发情境进行有限 Agent pilot trials，查看轨迹和补丁结果；仅依据软件合同修复 grader 缺陷/歧义/覆盖缺口。修改后重跑所有 no-op/oracle/negative controls，更新版本与 changelog，再冻结正式 A/B 比较材料。尽可能使用未参与模型特定调优的案例；不要为了强制两个模型得分不同而调整标准。一个公开 Issue 不支持统计显著区分度声明。

已知限制与资格结果：[qualification_report.md](qualification_report.md)。原研究 artifacts 保持不变。
