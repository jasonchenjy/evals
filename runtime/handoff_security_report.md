# Controller 文件交接安全修复

状态：**PARTIALLY_READY**。真实模型调用 **0**；没有执行 Agent Pilot。基于 `main` 的 `16fe50b3b14fade8c7b7735090331ec3e25da745`；开始时工作区干净、无后续提交。本次不提交或推送 Git。

## 根因与修复

原 adapter 把 grader 的 `checks/<id>` 同时用作 worker 可写 scratch 和 controller 日志目录。worker 结束不等于其路径可信：合并日志的普通 `write_text()` 会跟随 worker 制造的链接，捕获日志、执行记录和 observation 也存在类似交接风险。修复前先新增测试，真实观察到假 controller 文件被 `normal stdout / normal stderr` 覆写，测试失败；见 [修复前证据](evidence/handoff_security/before_fix.log)。

现在分为三个文件域：

- **Controller 产物**：原 grader 的 `checks/<id>` 中保存 stdout、stderr、合并日志和 `.execution.json`，以及经过验证的 observation 副本。sandbox 显式拒绝该目录与 controller 目录访问。启动器检查输出目录不在 workspace/scratch 可写根之下，逐级无链接打开父目录，并检查目录所有者及 group/other 写权限；系统 sticky 临时目录仅可作祖先。新目录 0700、文件 0600。相同 UID 下的真正隔离来自 Seatbelt，不能用 chmod 代替。
- **Worker 输出**：每次调用使用独立的 `<grading>-worker-scratch/<call>`。原 grader 的 `--output` 及 scratch 环境映射到此处；controller 在启动前固定其目录描述符，只接收扁平文件名 `observation.json`，不遍历 worker 创建的子目录。worker 的 `worker.log` 等同名诱饵不会被消费。
- **只读检查输入**：继续只挂载必要 check/behavior/inventory/requirements；Oracle、完整 Eval、controller 与其他 trial 不进入 worker。原 grader 本身没有改动。

安全读取使用目录相对的 `os.open(..., dir_fd=...)`，所有路径组件带 `O_NOFOLLOW`；最终文件带 `O_NONBLOCK`，打开后 `fstat` 确认单链接普通文件，拒绝 FIFO、设备、目录、符号链接和硬链接。目录身份在交接前后核对，读取前后核对 inode、大小、时间等信息，拒绝替换或读取期间修改。即使发生晚到的目录项替换，已打开的描述符也不会重定向到链接目标。observation 上限 **1 MiB**，捕获读取上限 **8 MiB**，读循环最多限额加一字节，不信任单次 `st_size`。常规 JSON、重复键、非有限数字、method、schema_version、tests_run、status、duration、failures/skips 和 `details` 字典列表均校验，验证不依赖 Python assert。

stdout/stderr 以 `O_EXCL|O_NOFOLLOW` 新建并保持打开的描述符，结束后检查路径仍指向该文件；controller JSON 和合并日志在已固定的目录中写独占临时文件，再按目录描述符原子替换，绝不 truncate 链接目标。拒绝时只输出固定原因，不输出被拒绝文件的内容。adapter 在 controller 独占路径写入安全解析后的 observation，原 grader 才进行自己的普通读取。

不安全或无效的交接抛出 `InfrastructureError`，中止剩余检查，记录 `handoff_failure.json` 和原 grader 的基础设施错误；不会被记为 passed 或普通能力失败。未生成任何 observation 的进程失败/超时仍保持原 grader 的 execution_error/timeout 行为。有效 observation 的评分语义保持不变。

关键代码：`grading.py:30`（scratch/输出映射与交接）、`sandbox.py:42` / `:53`（真实 policy 与路径边界）、`core.py:59`（捕获与执行记录）、`handoff.py:28` / `:77` / `:114` / `:177`（目录固定、安全读写、格式校验）。`tests/test_handoff.py` 与 `probe_handoff.py` 是可复现回归入口。

## 实际验证

从 `evals` checkout 执行以下命令；native 命令的可信 controller 由开发工具批准在外层 sandbox 之外启动，worker 始终保留严格原生 sandbox：

```sh
python3 -B -m unittest discover -s runtime/tests -v
python3 -B runtime/probe_handoff.py --eval pytest_5786 --repo ../pytest \
  --python pytest_5786/.venv/bin/python \
  --output runs/handoff_security_20261016/native_verified
python3 -B runtime/qualify.py --eval pytest_5786 --repo ../pytest \
  --python pytest_5786/.venv/bin/python \
  --output runs/handoff_security_20261016/qualification_verified
```

- **22 个 runtime 测试通过**（原 10 + 新 12）。测试覆盖日志/捕获/执行记录链接、打开后的替换竞态、父目录链接及替换、硬链接、FIFO、超大 observation、无效 JSON/字段、正常交接与不泄漏。整个 unittest 进程另受 90 秒期限约束；实际约 21 秒，无 timeout。见 [测试日志](evidence/handoff_security/runtime_tests.log) 与 [执行记录](evidence/handoff_security/runtime_tests_execution.json)。
- **真实 native 安全回归通过**。Codex CLI 0.162.1、macOS arm64、CPython 3.8.20。worker 直接读假 controller 文件与 controller observation 被拒；替换合并日志/stdout/stderr/执行记录/捕获父目录被拒。worker 确实创建 scratch 内的恶意链接，controller 拒绝 observation，流程基础设施错误、没有任何 check 被接受。假文件前后 SHA256 相同，假内容未进入 controller 结果或日志。见 [原生回归及实际 policy](evidence/handoff_security/native_regression.json)、[worker 断言](evidence/handoff_security/native_worker.stdout)、[拒绝结果](evidence/handoff_security/native_rejected_result.json)、[交接失败记录](evidence/handoff_security/native_handoff_failure.json)。这是单独的预期安全拒绝，未混入正常资格控制。
- **原 grader 7 个合同测试通过**。由 qualify.py 直接运行原测试脚本，退出码 0。见 [合同测试日志](evidence/handoff_security/grader_contract_tests.log)。
- **七个既有资格控制全部通过预期**，基础设施状态均 `ok`。Complete 与 Alternative 的 11/11 mandatory checks 通过；Alternative 的 H02 仍失败且只作诊断。No-op、Historical、Last-only、TestReport-only、Text-only 均 unresolved。逐一比较此前 stage2 证据，七个控制的全部 13 个 check 状态、overall 与 infrastructure 状态均完全一致。见 [资格汇总](evidence/handoff_security/qualification_summary.json)、[评分摘要](evidence/handoff_security/control_results.json) 和 [完整性与逐项比较](evidence/handoff_security/integrity.json)。

保留失败尝试：嵌套开发 sandbox 启动最初返回 `sandbox_apply: Operation not permitted`（[日志](evidence/handoff_security/nested_startup_blocker.log)），独立启动后实际验证通过；第一次正常资格重跑发现本次校验器错误地假定 `details` 为字典，已按未修改的 behavior.py 的实际列表契约修正。该失败留在 raw `qualification/`，最终有效证据来自全新 `qualification_verified/`。早期单元测试曾把总 check 数误写为 11，已修正为实际 13（mandatory 11 + diagnostic 2）。这些失败没有归因于模型或混入最终通过结果。

精选证据约 65 KiB，位于 `runtime/evidence/handoff_security/`；原始运行目录仍在 ignored `runs/handoff_security_20261016/`。修复前的精选失败日志仅隐藏了断言中的假敏感标记，原日志哈希保留在 integrity.json；真实数据、凭据和认证目录均未读取或纳入交付。

## 完整性、语义和限制

21 个 Eval 锁定文件全部匹配，checksums.json SHA256 仍为 `067f222eccfbf8d40fe520a7f4196426e82a4e5d4861e506cb96e60d11732e03`。Eval base commit、任务、hidden tests、Oracle、mandatory、阈值、H02 和四个维度均未改；可信 pytest checkout 仍干净。仅更新 runtime 自身完整性清单；旧 qualification 证据保留为历史记录。

本修复封闭 controller 对 worker 文件路径的跟随/覆写边界，不证明同一 Python 解释器内的全面防作弊。安全 handoff 能限制文件类型、大小和格式，不能证明一个格式合法的 observation 的业务真实性。已有工具权限、专用认证、聚合资源与 detached 子进程限制仍未解决；`agent.py` 及其真实模型启动门禁未改。没有模型参与的完整 trial，stage readiness 继续是 **PARTIALLY_READY**。
