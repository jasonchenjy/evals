# Evals

这个仓库保存 Coding Agent evaluation packages 及后续 Runtime 执行结果。每个 Eval 使用独立目录；目前完成的是 Eval package creation 和确定性资格验证，尚未运行 Agent trials。

## 当前 Eval

- [pytest_5786](pytest_5786/README.md)：pytest 异常链跨组件修复，版本 **0.1.0**，experimental / qualification-only。
- [资格报告](pytest_5786/qualification_report.md)：七个确定性控制态及四维评分结果。
- [机器结果](pytest_5786/private/qualification/summary.json)：完整 oracle 与替代实现通过全部必测，基线、历史 partial oracle 和负对照按预期未整体通过。

## 仓库约定

Eval 源码、文档、固定依赖清单、私有测试、oracle 和资格证据一起版本化。后续 Runtime 结果也保存在本仓库，应关联 Eval 版本、提交 SHA、提交补丁及执行环境，并与当前 qualification 记录区分。

不提交虚拟环境、下载缓存、临时 HOME/TMPDIR 或可重建的源码工作区。资格日志中的绝对路径保留为原始执行记录；它们不要求在其他机器上存在。复现方式见各 Eval 的 README。

仓库包含私有测试和参考解，面向评测维护者。Agent 只能获得各 Eval exporter 明确允许的公开 payload，不能获得整个仓库。
