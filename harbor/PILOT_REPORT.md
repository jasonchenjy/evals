# pytest #5786 真实 Agent Pilot

当前进展：底层工具和交接问题已经修复，新的多文件合成 Trial 通过，
Agent readiness 为 **AGENT_READY**。详见 [最新 readiness 报告](agent_readiness_report.md)。
按最新任务要求，本轮没有再次运行真实 pytest Agent Eval，因此仍没有有效的 pytest 模型能力分数。

以下保留 `pilot-real-02` 当时 **BLOCKED** 的历史事实和证据。

最新获批尝试 `pilot-real-02` 实际调用了 `openai/gpt-6.1-sol`，但两次工具调用
均因镜像缺少 `codex-code-mode-host` 而在执行前失败。Agent 没有读取或修改仓库。
独立 grader 正常评估了空补丁，四维为 **0 / 0 / 0 / 1**，Overall Fail。
这些是未修改基线的有效评分，**不能当作模型解题能力的有效评价**。

本次授权只执行一次，未自动重试。前一次 `pilot-real-01` 使用独立的旧授权，
在模型调用前因配置权限适配错误失败；那一问题已修复，旧证据全部保留。

## 本次真实执行与证据

- [最终审计](evidence/pilot-real-02/attempt-audit.json)：区分 Agent 工具基础设施故障与 grader 正常执行。
- [原生 Codex 输出](evidence/pilot-real-02/codex/agent/codex.txt)及
  [结构化轨迹](evidence/pilot-real-02/codex/agent/trajectory.json)：3 次模型调用、2 次工具调用尝试，
  两次均返回缺少 `/usr/local/bin/codex-code-mode-host`，实际 shell 命令执行数为 0。
- [原始 grader 结果](evidence/pilot-real-02/codex/verifier/grader/result.json)：
  infrastructure_status=ok，submission_status=accepted，overall_resolved=false。
- [最终源码补丁](evidence/pilot-real-02/codex/submission/submission.patch)为 0 字节；
  [提交清单](evidence/pilot-real-02/codex/submission/submission.json)的 changed_files 为 `[]`。
  补丁 SHA256 为 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。
- [证据清单](evidence/pilot-real-02/evidence-manifest.json)包含选取文件的 SHA256；
  认证文件、原始工作空间和传输归档没有纳入 Git。

运行版本为提交 `dcd5f18c4a5d1aae09433ce87b6abb7fef2d888d`，Harbor 0.24.0、
Codex CLI 0.162.1。原生 session/trajectory 记录模型为 `gpt-6.1-sol`，
模型用量归属为 `openai/gpt-6.1-sol`；没有替换模型。
新 session ID 为 `01a148a8-129c-7371-9694-985c3e498997`，公开任务指令保持原样。

Trial 从 `2026-10-16 23:58:51.138 PDT` 到 `23:59:43.223 PDT`，共 **52.085 秒**；
Agent 阶段为 **13.440 秒**，未触及 1800 秒预算。轨迹记录 input tokens 37,197
（其中 cached 34,304）、output tokens 307。这些是原生轨迹计数；不从轨迹推断隐藏推理。

Eval 为 `pytest_5786` 0.1.0，pytest 基线为
`955e54221008aba577ecbaefa15679f6777d3bf8`，Python 3.8.20 与原依赖保持不变。
Eval lock SHA256 为 `067f222eccfbf8d40fe520a7f4196426e82a4e5d4861e506cb96e60d11732e03`。
基础镜像为 `sha256:6fc218ba73f376189c8a3e860c5d5571782113b297704ffb153321c255cc2d12`；
实际 Agent 镜像 ID 保存在审计与 docker-inspect.json 中。

## 四维结果与解释

- **原问题解决：Fail，0。** A01、A02 均失败；没有源码修改，原缺陷仍在。
- **跨组件一致性：Fail，0。** B01、B02、B03 均失败；未实施报告序列化修复。
- **边界稳健性：Fail，0。** C01 通过，C02、C03 失败；仍是原基线行为。
- **无回归：Pass，1。** D01、D02、D03 均通过；空补丁未引入回归。

11 个 mandatory checks 均由原 grader 执行。H01 失败、H02 通过，H02 继续只作诊断。
上述 Fail 都不能归因为模型的编码错误：模型没有可工作的工具执行通路。
它明确报告无法访问仓库并结束，没有声称已经完成修复。

## 已实现并实际验证的隔离

新增实现仍只位于 `harbor/`。Harbor 管理 Trial、原生 Codex adapter、独立 verifier
和容器生命周期；可信 controller 保留 Eval lock、Oracle 与评分结果，候选 Python
调用通过现有 Runtime 的受限 worker 执行。本次 14 个 grader 候选调用均被拦截；
另有依赖预检 worker，共 15 个 worker，均已停止并删除。

Agent 的有效配置和 cgroup 已检查：非 root uid 1000、effective capabilities=0、
no-new-privileges、只读根目录、无宿主挂载／Docker socket／发布端口，
2 CPU、4 GiB、零 swap、128 PID、有界 tmpfs 与输出。Agent 公开材料与可信基线一致，
隐藏测试、Oracle 和假宿主私密文件不可见。候选公网访问依本次授权开放。

源码交接先终止候选 uid 的全部进程，再用不可修改的系统解释器有界采集并核对
inode/字节。拒绝链接、特殊文件、逃逸路径和超限输入；忽略候选 Git metadata；
补丁应用到新的可信基线，整个允许源码树与采集字节一致。
独立评分 worker 为非 root、只读、无网络、无宿主挂载，不能接触 controller 的
Oracle、认证和最终评分文件。

保留的[安全探针](evidence/pilot-security/summary.json)、
[worker 交接攻击测试](evidence/pilot-worker-handoff/results.json)及
[20 项单元测试](evidence/pilot-setup/postfix-unit-tests.json)均通过。
[最终七组控制](evidence/pilot-qualification-postfix/summary.json)为 **7/7、91/91**，
全部四维评分与原资格结果一致。本次运行前后 adapter/Runtime SHA256 与该资格证据一致，
21 个原 Eval 锁定文件均校验通过；没有改动原评分、隐藏检查、Oracle 或 H02 规则。

本次 Agent 和 verifier 的[清理收据](evidence/pilot-real-02/codex/agent-environment/cleanup.json)
确认容器删除，15 个 worker 收据也全部确认清理。
候选和行为检查仍共用 worker 解释器，因此不能宣称完整的生产级抗作弊安全。

## 认证实际情况

用户明确批准了本次使用 `/Users/junyuc/.codex/auth.json`、容器内认证暴露和公共网络。
认证已临时注入候选容器，**没有实现凭据隔离**。同 uid 命令可读取凭据，且可公网外传；
此前假凭据探针已验证这种暴露。没有用旧授权自动重试，也没有切换到其他凭据。

原生 run 走到清理阶段，Harbor 最终删除容器及临时文件系统。归档凭据模式扫描通过，
未提交 auth.json 或认证内容。清理不能撤回可能已被复制的凭据，模式扫描也不能证明
检测到了所有形式的秘密；本次可观察轨迹中两条候选命令均未能执行。

## 三个观察到的基础设施问题

1. **镜像打包遗漏，仍未修复。** `pilot/build.py` 只复制主程序 `codex`。
   本机预置 0.162.1 Linux 包实际还包含 `bin/codex-code-mode-host`，但它没有进入镜像。
   原生输出直接报告缺少该可执行文件；这是本轮工具失效的具体原因。
2. **预检没有覆盖实际工具派发。** 扩展预检验证了原生配置、认证链接、新会话及清理，
   但在 `codex exec` 前截断，因此未检出工具宿主缺失。版本号和启动准备成功不足以证明
   Agent 能读取、修改文件或运行 pytest。此前配置权限问题的修复有效，但预检仍不完整。
3. **完成标记过于宽松。** 原始 Harbor 没有抛异常，runner 的 `live_completed=true`、
   `expectation_met=true` 只说明生命周期与 grader 结束，不能证明 Agent 工具正常。
   原始记录保持不变；新增审计明确将 `coding_evaluation_valid` 设为 false，标记阻塞。

官方 CLI 文档区分 Code Mode host 与客户端连接；本次具体诊断以安装包布局和原生
错误输出为准。[官方 CLI 参考](https://learn.chatgpt.com/docs/cli/reference)

## 迁移判断与最小下一步

Harbor 的编排、受控交接和原 grader 对接已验证，但真实 Agent 工具通路仍有阻塞。
仍复用 Runtime 的安全组件，未删除或修改 Runtime，不能宣称完全替代。

下一步应先修正 Codex 运行包布局，在同样隔离条件下用假凭据、零模型调用验证
工具宿主能实际读写公开文件并执行 Python/pytest，再让入口拒绝这种工具基础设施错误，
并对修改后的版本重新资格验证。完成这些工作后，真实尝试仍需另一次明确授权。
本轮没有继续修改运行代码或启动第三次尝试；仅保存真实结果、审计与报告。

历史证据 `pilot-real-01`、`pilot-live-preflight-02`、`pilot-setup/*` 均保留。
其中“未调用模型／未读取认证”等历史字段只描述各自生成时点；本次结果以
`pilot-real-02/attempt-audit.json` 和本报告为准。
