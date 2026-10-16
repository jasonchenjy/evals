# pytest_5786 首次真实 Trial 前置执行报告（2026-10-16）

**结论：PARTIALLY_READY；正式 pilot 为 NOT_EXECUTED。** 采用 Colima VZ + Docker Engine 作为唯一新执行边界。已实际完成 Linux 历史环境、独立 grading、资源/清理与恶意文件交接验证；没有向真实模型发送 benchmark 请求，没有 participant patch、能力分数或 Agent Pilot 成功结论。用户选择的 model 保持 `gpt-6.1-sol`。

## 基线与保留的工作

开始时为 `main`，HEAD 与 origin/main 均为 `ffc25b55c0b3389ad25cc54d0b8cf9e416260762`，仅 `analysis/` 未跟踪。没有修改两个 analysis 子项目。未发现适用的 AGENTS.md。本报告记录开发验证时的工作树；后续提交与发布以仓库 Git 历史和仓库级 CHANGELOG 为准。

Eval v0.1.0，lock SHA-256 为 `067f222eccfbf8d40fe520a7f4196426e82a4e5d4861e506cb96e60d11732e03`；pytest source base 仍为 `955e54221008aba577ecbaefa15679f6777d3bf8`。prepare.py 成功恢复精确源码、443 项 manifest 和公开 payload，独立 synthetic baseline 为 `41ffd0de9c7ece927733fadc2201491c5ae51be2`。三种身份没有相互替代。运行时修改尚未提交，以执行时的逐文件 SHA 和最终 artifact_hashes.json 标识。

没有修改 Eval 任务、tests、Oracle、H02 决策、mandatory、阈值或四个评分维度。原 grader 完整保留；`grading.py` 仅把边界名称改为由 adapter 提供。

## 已实施的边界

用户不希望登录 Docker Desktop；其组织策略文件完全未改。检查未发现现成 Colima/Lima 或可用的已授权远程 Docker endpoint 后，通过权限流程安装 Colima 0.9.1/Lima 1.2.1，启动专用 Linux arm64 VM。Docker Engine 28.4.0、kernel 6.8.0-64-generic、cgroup v2。VM 为 2 vCPU/6 GiB RAM、8+12 GiB 稀疏磁盘；只有一个空的只读 host share，没有 HOME、SSH agent、Docker socket 向候选容器暴露。没有改全局 Docker context、SSH config 或自动启动服务。验证后已停止本次专用 VM 释放内存，保留其磁盘、镜像和证据。

可信 controller 使用显式 VM socket 与独立 Docker client config；公共镜像/依赖仅在可信 setup 时联网。候选容器强制 network=none、rootfs 只读、uid 1000、cap-drop ALL、no-new-privileges、private PID/IPC、无宿主挂载/端口。每次 start 前检查 Docker inspect 的实际 policy，不能靠配置名通过。

每个候选 worker 的上限为 2 CPU、4 GiB 聚合内存、禁用 swap、128 PIDs、2047 MiB /trial tmpfs + 1 MiB /dev/shm。controller 设置 wall deadline 和输出上限，正常结束、超时或输出超限后均停止整个容器 PID namespace 并删除容器。新容器不继承前次 writable state。有限资源探针使用 128 MiB/16 PIDs/8 MiB，避免在宿主做资源耗尽测试。

`container_sandbox.py` 为原 grader 的每次 Python 调用建立新 worker：源代码来自 controller 新建并验证 patch bytes 的快照；仅必要 private/check.py、behavior.py、existing_inventory.json、requirements 与源快照进入不可变输入镜像。COPY/chmod 构建不执行候选 Python；Oracle patch、研究资料、凭据和 controller 输出不进入镜像。候选 source/scratch 在独立 tmpfs 中。

stdout/stderr、执行记录与合并日志由 controller 在宿主独占目录发布，worker 无法访问。容器 bootstrap 通过现有 no-follow、目录 FD 固定、普通单链接文件、非阻塞与大小检查采集 observation，发送有界的 bytes envelope。controller 先确认容器所有进程停止，再验证 envelope 和 observation schema，将验证结果写入自己的兼容路径供原 grader 消费。它不使用 worker 返回的路径进行宿主读写。交接拒绝归为 infrastructure failure。

## 实际验证与证据

原始记录保留在 `runs/pilot_readiness_20261016/`（ignored）；经筛选证据在 [evidence/container_readiness/](evidence/container_readiness/)。可重复命令见 [container/README.md](container/README.md)。

- Runtime 单元测试 **29 passed**，包含原 22 项与新增 effective policy、不可变 image/显式 endpoint、bytes envelope、输入特殊文件、additional_tools 序列化和 requirements 一致性回归。
- 原 grader 合同测试 **7 passed**，由资格运行直接调用原测试文件。
- **Linux 七个资格控制全部完成，91/91 check 状态与先前 macOS 结果逐项一致，0 个意外 infrastructure error。** Complete/Alternative 全 mandatory 通过；Alternative H02 failed 保留；其余五个 unresolved。见 qualification_summary.json、qualification_comparison.json。没有把安全负例混入正常资格控制。
- CPython **3.8.20**，22 个 pinned dependencies，pytest.__file__ 为 `/trial/workspace/src/pytest.py`。serial/xdist 公开 reproducer 的 baseline 行为符合预期（有意 exit 1），public sanity exit 0；本地 xdist worker 成功启动。见 environment.json 与原始 environment/*.stdout。
- 聚合内存超限真实触发 cgroup OOM；14 个子进程后达到含 init/父进程在内的 16 PIDs 上限；tmpfs 返回 ENOSPC；网络 connect 返回无路由，非 DNS/timeout 推断。正常退出与 timeout 的 setsid 子进程均随容器消失；输出超限会停止；独立新容器的文件重置检查通过。见 resource_results.json、resource_receipts.json。
- **10 个真实容器交接用例通过**：normal、合并日志 symlink、stdout/stderr symlink、execution record symlink、observation symlink/FIFO/超大/非法 JSON、父目录替换。normal 和无用途的 worker.log symlink 安全完成；其余 8 项明确拒绝。假宿主文件始终未变，敏感假内容未进入结果/日志，没有无限等待。见 handoff_results.json。
- 额外真实 filesystem 探针确认：host canary 先由 controller 确认存在，容器绝对/相对父路径均不可读；共享 /private/tmp 的另一个 trial 假文件也不可读；外部写入失败；workspace 可读写；immutable test input 可读不可写；无 Docker socket。host 路径在独立 namespace 中返回不存在是挂载隔离结果，不是遗漏创建 canary。见 filesystem_canaries.json。
- 原 native handoff 历史证据保留。本轮以新容器边界的真实回归完成等效重验，没有将 mock 当隔离实测。

历史镜像 ID：`sha256:6fc218ba73f376189c8a3e860c5d5571782113b297704ffb153321c255cc2d12`，基础 Python image digest：`sha256:1d52838af602b4b5a831beb13a0e4d073280665ea7be7f69ce2382f29c5a613f`。没有安装现代 pytest。requirements 副本通过一致性测试。未来 apt 重建不是位级可重复，必须记录新 image ID 并重新资格验证。

## 实际工具与认证阻塞

已使用安装的 Codex CLI **0.162.1**，二进制 SHA-256 `74c6a6d263f40d65f99c27a815275f5b4ed0bcc2baecc396b4cf3255498bdfc0`。读取本地 help 与生成的 app-server schema；存在 environment/add 和远程 exec-server 接口，但尚未实施或验证完整的文件/工具容器路由。

新的 `probe_cli_inventory.py` 启动全新 ephemeral CLI、fresh HOME、禁用用户 config/rules/skills 等，将请求发给只在本机监听、始终拒绝且从不转发的 fixture。没有真实模型推理，也没有返回/执行合成工具调用。工具定义实际位于 `input[].type=additional_tools`，并非顶层 tools；新增测试防止把缺少顶层 tools 误读为零工具。

**发现真实阻塞：** 即使显式 disable multi_agent/multi_agent_v2 等，实际序列化请求仍含 6 个 collaboration 工具；functions.exec 的嵌套说明仍列出 3 个 MCP resource 入口。MCP server 配置为空不等于这些入口被删除，是否可进一步动态发现工具也未验证。skills 经精确路径禁用后已不在请求中。见 tool_inventory.json、request_identity.json，完整无 headers 的 raw request 留在 ignored runs 中。

该 fixture 证明了请求序列化现象；没有证明 live provider 请求相同、模型实际使用过工具、或所有入口均被容器限制。**effective_tools_verified 仍 false，原 agent.py 门禁未修改。** 尚不能把 controller 的本机文件入口误当候选容器入口。

专用 home 为 `runs/pilot-client/home`，已请求用户使用当前 CLI 的 device-auth 登录。没有复制或读取开发者认证文件，没有 token 写进 prompt/image/repo/log。最新支持的 `login status` 仍 exit 1 / Not logged in。实际 participant 的最终认证目录隔离仍需在工具路由完成后再验证。

下载并校验了匹配版本的 Linux CLI 公开 npm 包用于后续 remote executor 工作；未把它用作 participant，没有运行真实模型。当前选择模型仍是 `gpt-6.1-sol`，服务实际 model 信息不存在，不能编造。

## 失败分类、限制与下一步

本次正式 trial：**not_executed**。没有有效能力分数、participant patch 或私有评分；资格控制分数不能代替 trial。容器安全负例是预期 infrastructure rejection。第一次 fixture 在开发沙箱内绑定 loopback 被拒，随后通过工具权限批准启动可信 fixture；没有扩大候选权限。所有原始目录保留。

尚需完成的硬阻塞：

1. 为固定 CLI 建立受支持的完整工具限制和容器执行路径，并逐个验证读取、编辑、exec/write_stdin 及其余保留入口；直接拒绝额外工具，不能删布尔门禁或假设 feature flag 生效。若使用 environment/add/exec-server，controller 的模型客户端和认证必须保持容器外，候选命令继续断网。当前没有这一连接的验证结论。
2. 用户完成 dedicated login；随后以支持的 status 确认，并在最终 agent 路径证明认证目录、controller、private 和其他 trial 不可访问。
3. 完成 agent 容器停止后的安全源码导出到现有 controller-owned mirror；重用既有 collect/assert_applied，在独立 snapshot grading。当前新 adapter 只接通 grading/probes，未接通真实 agent 生命周期。

最小下一任务是单一 Colima 后端的 **Codex 工具入口连接与离线 canary 验收**，不是增加第二后端。通过后才能以 task.yaml 的 1800 秒预算执行一次 gpt-6.1-sol ephemeral trial，保存真实模型响应/事件、停止全容器进程、收集 patch、独立 grading、记录结果。unresolved 或空 patch 不自动重跑。

不能声称全面防作弊：候选与 check 共享解释器，仍可能干扰 grader；候选与容器 bootstrap 的同 UID 干扰也不属于已证明的防作弊能力。该边界保护宿主/private mounts，不认证候选行为本身。controller/daemon 崩溃情况下没有持久 watchdog；cleanup 失败必须 fail closed，并由操作者停止专用 VM，不启动下一次 trial。VM 路径在 /private/tmp，不是持久部署。

因此可以继续 runtime implementation，**尚不能进入真实 evaluation iteration、Agent Pilot 成功结论、模型排名或 A/B 比较**。
