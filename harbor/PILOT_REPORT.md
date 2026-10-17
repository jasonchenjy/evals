# pytest #5786 单次真实 Agent Pilot

状态：**PARTIALLY_READY**。

唯一获批的真实试跑在调用模型之前遇到适配错误，未完成求解或评分。
真实认证已按本次授权临时注入；容器已删除。没有第二次真实尝试。
已修复配置权限兼容问题，并通过假凭据的原生启动准备测试。
确定性控制和安全边界可验证，但真实 Codex 到独立 grader 的全链路仍未验证。

## 本轮实现

Harbor 0.24.0 继续负责 Trial、Codex adapter、独立 verifier 和生命周期。
新增代码位于 `harbor/pilot/`：公开基线构建、固定网络与资源约束、停止候选
进程后的源码采集，以及调用原 grader 的 `BaseVerifier` 适配。
原 `pytest_5786` 的评分、隐藏检查、Oracle、指令、Python 3.8.20 与依赖均未修改。
`runtime/` 没有修改或删除；复用的八个安全组件通过 SHA256 固定，变化即拒绝运行。

可信 controller 保留 Eval lock 与 Oracle。候选代码只进入独立的非 root、
只读、无网络、无宿主挂载 worker；每个检查使用新容器。原 grader 的所有
候选 Python 调用都被拦截，worker 不能访问或写入 controller 的最终评分文件。
候选与检查仍共享 worker 解释器，因此不能把本次边界测试解释为完整抗作弊证明。

## 实测隔离与资格验证

- [源码与配置权限测试](evidence/pilot-setup/postfix-unit-tests.json)共 20 项通过，覆盖不安全归档、候选 Git hooks/config、
  新基线补丁应用，以及原生配置准备只能以 uid 1000 执行规定的权限操作。
- [Agent 容器与资源探针](evidence/pilot-security/summary.json)：9 项 Agent 探针通过；
  worker 的内存、PID、磁盘、网络、超时、输出及脱离进程清理探针通过。
- [原 worker 的文件交接攻击测试](evidence/pilot-worker-handoff/results.json)：10 项符合预期。
- [扩展后的假凭据预检](evidence/pilot-live-preflight-02/summary.json)：CLI 0.162.1；
  原公开材料一致；非 root、capabilities=0、禁止提权；Docker socket 不存在，
  网关 2375/2376 不可达；假宿主私密文件不可见。它进入原生 `Codex.run`，验证
  config.toml 为 uid 1000 / 0600、认证链接和新会话，拦截模型命令并验证清理。
  此预检没有读取真实凭据或调用模型，不能证明后端登录或模型可用性。
- 源码采集拒绝符号链接、外部硬链接、FIFO、设备、目录逃逸、重复路径、异常
  可执行位及超限输入；终止候选进程后采集，候选 Git metadata 不参与可信 diff；
  应用后的整个允许源码树逐字节核对。nondumpable 后台写入进程也已实测清理。
- 有效 Docker 配置与 cgroup 均记录：2 CPU、4 GiB、零 swap、128 PID、
  只读根目录、有界 tmpfs、无宿主挂载／设备／发布端口。控制和 grader worker 无网络；
  真实配置的候选 shell 能连公网，这一点没有伪装成模型专用网络。

[真实尝试之前的七组控制](evidence/pilot-qualification/summary.json)已完成：
**91/91 检查状态和全部四维评分一致**，七组基础设施正常，Harbor exception 均为空。
其 adapter 与复用 Runtime 源码 SHA256 在运行前后完全一致。
七个 Agent、七个独立 verifier 和 105 个 worker 均已清理。
H02 保持 diagnostic-only，Alternative 的 H02 失败不影响其 Overall Pass。

控制预期：No-op Fail；Historical 原 Bug 通过、已知回归失败；Complete 与
Alternative Pass；last_only、testreport_only、text_only 均 Fail。
[修复后的最终资格验证](evidence/pilot-qualification-postfix/summary.json)再次达到
7/7 控制、91/91 状态及四维评分全部一致；14 个 Harbor 容器和 105 个 worker
全部清理。当前代码与资格验证、扩展预检的 SHA256 一致，21 个原 Eval 锁定文件
校验通过。详见[最终审计](evidence/pilot-setup/postfix-audit.json)。这些结果另行保存，
没有覆盖真实尝试所依据的旧证据。

## 唯一真实尝试的结果

[失败审计](evidence/pilot-real-01/attempt-audit.json)与
[Harbor 原始结果](evidence/pilot-real-01/codex/result.json)记录：

- Eval `pytest_5786` 0.1.0，基线 `955e54221008aba577ecbaefa15679f6777d3bf8`。
- Eval lock SHA256 `067f222eccfbf8d40fe520a7f4196426e82a4e5d4861e506cb96e60d11732e03`。
- 基础镜像 `sha256:6fc218ba73f376189c8a3e860c5d5571782113b297704ffb153321c255cc2d12`；
  运行容器的实际镜像 ID 另见其 docker-inspect.json。
- Codex CLI 0.162.1；请求模型 `openai/gpt-6.1-sol`。后端实际模型身份为未知，
  因为 `codex exec` 未启动；没有模型 token、会话轨迹或候选工具调用。
- Trial 于 `2026-10-17T06:48:19.716132Z` 开始，`06:48:26.553839Z` 结束，
  总耗时 6.838 秒，预算 1800 秒。只有一次尝试，重试次数 0。
- 原生启动准备上传认证后，写入配置时请求 `chown ... && chmod 600 ...`。
  初版适配层只允许认证文件的 chown，因此主动拒绝并报 RuntimeError。
- AGENT_END 仍完成源码恢复，得到[空补丁](evidence/pilot-real-01/codex/submission/submission.patch)，
  changed_files 为 `[]`。这是异常退出后的未修改基线，**不是模型提交**。
- 独立 verifier 未启动，原 grader 未运行；没有评分结果文件，也没有 mandatory check 结果。
  不能把控制组 No-op 的结果当作本次成绩。

四个维度均为 **未评估**：原问题解决（A01–A02）、跨组件一致性（B01–B03）、
边界稳健性（C01–C03）、无回归（D01–D03）。没有相关模型源码改动。
这是基础设施准备失败，不能判定模型在任何维度编码失败。

## 认证实际情况

用户在本次对话明确批准使用 `/Users/junyuc/.codex/auth.json`，并批准一次容器内
认证暴露和公共网络访问。该文件已临时上传到 Agent 容器；这**不是凭据隔离**。
候选 uid 可以读取认证，且公共网络允许外传；假凭据探针已验证这种可读性。
未发现额外的未授权凭据注入，但本轮测试不能证明通用的凭据防泄漏能力。

本次异常发生在原生认证 finally 清理之前；最终由 Harbor 删除整个容器及其 tmpfs。
[容器清理收据](evidence/pilot-real-01/codex/agent-environment/cleanup.json)确认 removed=true。
未启动模型或候选命令。归档只选取允许的证据文件，凭据模式扫描通过；
没有把 auth.json、认证内容、原始工作空间或传输归档提交到 Git。
扫描是归档检查，不构成所有形式秘密检测的证明。

## 观察到的失败模式与修复

1. **配置权限适配遗漏**：Harbor 原生配置写入需要一条组合权限命令。
   已只允许固定 config 路径的精确 chown/chmod 600，并以现有 uid 1000 执行；
   仍拒绝系统安装、其他路径、权限放宽、追加 shell 命令及 root 默认用户。
2. **预检范围不足**：原预检只覆盖 CLI setup 与假认证上传，没有进入原生 run 的
   配置阶段。已扩展到真正的模型命令边界，检查配置权限、新会话与认证清理。
   Live 入口现在要求该预检证据与当前 adapter SHA256 完全匹配。

两项都是基础设施缺陷；没有模型编码结果可分析，也不推断隐藏推理。
修复后仅做假凭据预检和确定性资格验证，没有消耗第二次真实试跑授权。

## 迁移判断与最小下一步

Harbor 已承接本轮通用编排与 Agent 接口，仍依赖现有 Runtime 的可信补丁、
受限 worker、输出交接和评分隔离组件。实际删除 Runtime：0 行；不能宣称完全替代。

最小下一步是基于修复并重新验证后的版本，另行明确授权一次真实尝试，保存实际
Agent 轨迹、源码补丁与独立 grader 结果。此前的一次授权不会被自动复用来重试。
本轮不自动改变 Eval，也不把未完成的真实试跑标记为就绪。

复现命令、边界和授权参数见 [pilot/README.md](pilot/README.md)。
`pilot-setup/final-audit.json` 和 `provenance.json` 是真实尝试之前的历史快照，
其中“未读取认证／未真实运行”只描述该快照时点；本次结果以失败审计和本报告为准。
