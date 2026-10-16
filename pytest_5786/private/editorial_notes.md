# Agent 题面编辑记录（私有）

来源：pytest-dev/pytest Issue #5786，原文来自既有 research/pytest_issues_raw.jsonl，没有重新采集。历史 PR #5787、后续 #5971 和 curator 分析均不进入 Agent payload。

原文是两段三层 ValueError 测试和本地/xdist 输出对照，原环境报告 pytest 4.0.2、xdist 1.25.0、Python 3.6.7。Eval 采用已锁定的历史 base 和已验证兼容环境，而非声称复刻作者全部原机器环境。

编辑：

1. 用普通用户症状标题替代含 serialization 定位提示的原 Issue 标题；去掉 Issue/PR 链接、日期、作者环境路径和大段终端输出。没有新增确切修复位置。
2. 保留两种链和三层顺序；公开代码只重命名测试函数/局部异常变量，数值 11–13 与 21–23 保持原示例。
3. 明示需要实际源码修复，可运行公开测试，明确 source-diff 提交格式与资源/环境边界。这些是评测操作合同。
4. 加入合法的行为保持要求：collection errors、captured output、附加 report sections、normal reports、Python context 语义、既有消费者及合法 exception representation。它们来自已存在的软件行为，避免隐藏正当需求。
5. 不在题面暴露具体 None 输入、private tests、helper 名称、reference patch、评分弱点或负对照策略；未要求 Agent 匹配历史 patch。

这些是统一的题面裁剪与合同澄清，不是训练污染消除证明。Eval ID/base 身份仍可能使模型识别公开题目。
