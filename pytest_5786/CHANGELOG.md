# Changelog

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
