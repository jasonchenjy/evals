# Harbor 替代 Runtime：实测评估

结论：**NEEDS_MORE_VALIDATION**。Harbor 已执行真实 Codex → 源码修改 → 独立 verifier，并可在不改评分逻辑的情况下复用 pytest_5786。它可以承接评测编排，但当前证据不足以替代自研 Runtime 的安全边界。runtime/ 保留，未推送。

## 版本与环境

实际安装为 PyPI Harbor **0.24.0**，控制器 CPython 3.13.12；Agent/Eval grader 使用既有镜像中的 **CPython 3.8.20** 和原 requirements.txt 的精确依赖。控制器依赖冻结于 requirements-controller.lock，已安装关键源码指纹见 [installed-harbor.json](evidence/installed-harbor.json)。官方 main checkout 的项目版本也是 0.24.0，但部分源码比 wheel 新，因此运行接口以已安装 wheel 为准。

宿主为 macOS arm64，使用现有 Colima Docker Engine 29.2.1；只在 harbor/tools 安装 Compose 5.6.0 和 Buildx 0.38.0。基础镜像 ID 由 launch.py 强制校验为 sha256:1734efd60ea49a9bef74be6943cf0845625048f2ba59b36461fdb78a3f8cc9a9。未改 Docker Desktop 策略、全局 Docker 配置或 Colima 挂载配置。

实际遇到并保留的故障：缺 Buildx 导致网络隔离 sidecar 构建失败；官方原始二进制下载反复超时，改用校验过的 Homebrew 压缩包；相对结果路径被 Compose 按任务目录解释；此 Colima daemon 无宿主目录共享，原生 mounted 日志机制无法回传 reward。最后一项通过 Harbor 支持的自定义 Environment import_path 解决：colima.py 保留 Docker 后端，只移除已知日志 bind、声明 mounted=False，使用 Harbor 自带的上传/下载。没有修改 Harbor 安装源码或退回共享验证。故障证据位于 evidence/failed-*。

## 合成任务的执行证据

[三控制结果](evidence/spike/summary.json)：No-op reward=0、Correct Patch reward=1、Incomplete Patch reward=0；均无基础设施异常。Incomplete Patch 使用 abs(a/b)，公开正数例通过、负数隐藏检查失败。

任务固定 Git base 为 c273d4511362006a30b36447448cb4137eae1361。Agent 镜像只有源码、公开例子和固定 Git 基线；隐藏脚本仅进入 verifier。task.toml 显式指定 environment_mode="separate"。Harbor 收集 /work/src，再在新容器中恢复；verifier 检查独立的 /base 原始源码和固定 commit、双方不同 hostname、隐藏测试缺席观察、最终源码 SHA256，保存 final.patch/result.json/reward.json。该结果来自真实 Harbor Trial，不是本地 pytest 冒充资格验证。

## 一次真实 Codex Trial

[真实结果](evidence/codex-spike/codex/result.json)、[ATIF trace](evidence/codex-spike/codex/agent/trajectory.json)、[最终补丁](evidence/codex-spike/codex/verifier/final.patch)。CLI **0.162.1**，模型 **openai/gpt-6.1-sol**，9 个 trajectory steps。trace 记录了读取 divide.py、apply_patch 将 // 改为 /、执行 python public_test.py。独立 verifier 的六个行为检查全通过，reward=1，exception=null，模式为 separate。

Agent hostname=39a7c49de88d，verifier hostname=886fed997d6f。每次新建容器和 CODEX_HOME；没有指定 resume/load trajectory，也没有传开发会话或宿主配置。既有 Linux CLI vendor 二进制放入忽略的构建上下文，认证没有进入镜像。

当前进程无 API key。用户明确授权仅这一回合成 Trial 使用主 auth.json，Harbor 的受支持认证接口在运行时将其上传到临时 Agent 容器；原生日志记录了运行结束删除临时 secrets/CODEX_HOME，Harbor 随后销毁容器。保存的 trace、日志经过凭据模式扫描，未复制认证文件。此授权没有延伸到真实 pytest_5786 Trial。

## pytest_5786 接口映射

| 既有接口 | Harbor 适配 |
| --- | --- |
| task.yaml | harbor/pytest_5786/task.toml，显式独立 verifier |
| instruction.md | 构建时逐字复制，不重写指令 |
| environment.yaml / prepare.py | 调用原 prepare.export；仅 Agent allowlist 入镜像，固定 venv PATH 与源码 PYTHONPATH |
| private/grader.py | verifier 调用原脚本，原文件及 lock 均不修改 |
| result.json | 完整保留，同时转换为 overall reward 和四维 0/1 reward |
| Oracle / negative controls | 由受信任 ControlAgent 在 Agent 容器施加原补丁；空补丁为 No-op |

源为 pytest-dev/pytest，base=955e54221008aba577ecbaefa15679f6777d3bf8。Agent 预检检查 Python 3.8.20、候选 pytest 从 /work/src 导入，以及全部原固定依赖。verifier 使用新建原始 export 与可信 Git index 生成最终源码 diff，拒绝链接、非 Python 文件、模式变化和 version shim 修改；原 grader 再从固定原始仓库创建 fresh snapshot、原样验证/应用 patch 并评分。applied_source_sha256 与传入最终源码逐项比较。

没有维护第二份完整 Eval 包；生成上下文按原 checksums.json 的要求临时复制最小必需文件，generated/ 被忽略。原 grader 的 lock 要求 verifier 内存在锁定 Oracle 文件，这是保留原契约的兼容性代价，也构成下面的安全缺口。

## 控制结果

| 控制 | 原 Bug | 跨组件 | 边界 | 非回归 | Overall |
| --- | --- | --- | --- | --- | --- |
| No-op | 0 | 0 | 0 | 1 | FAIL |
| Historical | 1 | 1 | 0 | 0 | FAIL |
| Complete Oracle | 1 | 1 | 1 | 1 | PASS |
| Alternative Oracle | 1 | 1 | 1 | 1 | PASS |
| last_only | 0 | 0 | 0 | 1 | FAIL |
| testreport_only | 1 | 0 | 0 | 1 | FAIL |
| text_only | 1 | 0 | 0 | 0 | FAIL |

首轮完成的 pytest-002：7/7 预期满足，91/91 状态与原 qualification 及现有 Runtime mac_mini_20261016 完全相同，所有基础设施状态 ok。H02 保持 mandatory=false；Alternative Oracle 的 H02=failed，但 Overall=PASS。没有将 H02 改成必过或改评分逼迫通过。最终 Agent PATH 配置的复验结果见本报告末尾的最终验证记录。

真实 pytest_5786 Agent Trial **未运行**：其认证不在已授权的合成 Trial 范围内，且尚未通过下述安全等价性检查。未为了得到成功解反复运行模型；只有一次真实合成 Agent Trial。

## 替代范围与差距

| 能力 | 实测与迁移判断 |
| --- | --- |
| Task/Trial 编排、超时、环境生命周期 | Harbor 已承接本次执行；可替换对应自研通用编排 |
| Agent 集成 | Codex 真实读、写、测试已证实；其他模型/harness 仅源码显示支持，尚未实测切换 |
| 环境复现 | 固定源码、基础镜像 ID、Python、依赖已验证；换宿主/架构仍需复验 |
| Hidden Test 隔离 | Agent 镜像与文件观察确认无私有测试/Oracle；独立容器不等于独立 VM |
| Patch 交接 | 受信任控制全部逐字节复现；尚无对并发写入、恶意链接/特殊文件、超大目录的完整攻击验证 |
| Grader 兼容性 | 无需改评分逻辑，四维和 91 状态一致；原私有包 integrity 要求 Oracle 进入 verifier |
| 日志/产物 | 原生 result/config/lock/trial 日志、ATIF/native trace、补丁、原 grader 详细结果均保留 |
| 资源限制 | 配置 CPU/内存；未证明等价的 128 PID、2 GiB 磁盘、脱离进程/输出限额策略 |
| 运维复杂度 | 需 Python>=3.12 控制器、Compose、Buildx、网络 sidecar；此 Colima 需薄 Environment 适配 |

最关键的安全边界仍需自定义：Harbor 的 separate 模式不自动产生可信补丁，不自动在采集前冻结全部 Agent 后台进程，也未在本任务中证明不跟随链接、读取大小限制和原子发布。原生 artifact 接口不是已验证的恶意文件交接防线。

当前原 grader、隐藏检查、候选代码在同一 verifier 容器内以 root 执行；恶意候选可以尝试读取 private/Oracle、干扰 observation/result/reward。保留原 security_mode="trusted-local-qualification-not-a-sandbox" 标签，并用独立 isolation.json 说明实际容器边界，不能把它解释为抗作弊资格。若要达到现有 Runtime 的控制器/工作进程分离，需要外置受信任评分编排及每检查隔离，保留专门的安全交接验证。既有 Runtime 的相应证据见 runtime/evidence；它本身也不是因此自动满足所有生产安全要求。

真实 Codex 以 Harbor 默认的容器内 bypass 模式运行，认证对 Agent 代码可读，Agent 阶段网络为 public。此次只验证了正常合成任务；没有做完整工具权限清单、认证隔离或恶意网络绕过审计。推理认证代理和只允许模型端点的网络策略仍需专门验证。

**实际删除的 Runtime 代码：0 行。** 新集成约 330 行 Python，另有任务配置、安装脚本、文档和证据。这个规模说明 Harbor 能复用通用 harness，而不是证明整个 Runtime 都可以删除；不能把未迁移的安全代码算成已经省掉。建议先将 Harbor 作为编排层候选，保留现有安全边界，补齐对抗交接、grader 权限、资源/网络/认证测试后再决定全面迁移。

决定：**NEEDS_MORE_VALIDATION**。

## 最终验证记录

最终配置执行为 harbor/raw/pytest-003，7/7 控制符合预期，全部 infrastructure_status=ok。每个 Agent 的 public-preflight.txt 均验证 Python 3.8.20、源码 pytest 和全部固定依赖。原 grader 未修改，91/91 检查状态与原资格证据及现有 Runtime 完全一致；H02 仍仅作诊断。

- [最终 7 控制摘要](evidence/pytest_5786-final/summary.json)
- [91 项逐项比较与基线 SHA256](evidence/qualification-comparison.json)
- [原详细 grader 结果示例](evidence/pytest_5786-final/complete/verifier/grader/result.json)
- [独立环境与补丁验证](evidence/pytest_5786-final/complete/verifier/isolation.json)
- [Agent 公开环境预检](evidence/pytest_5786-final/complete/agent/public-preflight.txt)
- [最终 Eval 证据文件清单与 SHA256](evidence/pytest_5786-final/evidence-manifest.json)
- [原 Eval 文件未变审计](evidence/final-audit.json)

3368 个已记录的原 Eval 文件校验和保持不变；源码语法检查通过。提交范围限定 harbor/，未删除或改写 Runtime，未推送。最终决定仍为 NEEDS_MORE_VALIDATION。
