# Changelog

仓库级 runtime 与实验记录；Eval 本身的版本变化见 [pytest_5786/CHANGELOG.md](pytest_5786/CHANGELOG.md)。

## 2026-10-16 — Colima/Linux runtime 与首次 pilot 前置验证

基于已审查提交 `ffc25b55c0b3389ad25cc54d0b8cf9e416260762`。状态仍为 **PARTIALLY_READY**，正式 Agent Trial 为 **not_executed**，真实模型调用为 0。指定模型保持 `gpt-6.1-sol`。

### 实现

- 选择 Colima VZ + Docker Engine/Linux arm64 作为唯一新候选执行边界；不修改 Docker Desktop 组织策略。专用 VM 已在验证后停止，保留镜像与磁盘。
- 增加不可变 image ID、显式 daemon endpoint、启动前实际 policy 校验；候选容器无宿主挂载、无网络、非 root、只读 rootfs，并限制聚合内存、PIDs、CPU、可写存储、输出及 wall time。
- 正常结束、超时、输出超限后停止整个容器进程命名空间，包含脱离普通进程组的子进程；新容器不继承之前的可写状态。
- 接入原 grader：controller 重建 source snapshot，必要测试作为不可变输入，worker 输出通过有界 bytes envelope 与 observation schema 校验后交接。保留原有安全文件交接机制，不在宿主执行候选 Python。
- 新增真实资源、文件交接与拒绝式 CLI 请求捕获探针，以及 7 个新增 runtime 单元测试；更新使用说明、中文报告和 runtime 完整性清单。

### 实际运行的实验

- Runtime **29/29**、原 grader 合同 **7/7** 通过。
- Linux CPython **3.8.20**、22 个依赖 pins、导出源码 import、serial/xdist 公开 reproducer 与公开 sanity 验证通过。
- 七个资格控制完成，**91/91 check 状态与前一 macOS 资格记录完全一致**，无意外 infrastructure error。Complete/Alternative 全 mandatory 通过，Alternative 的 diagnostic-only H02 failed 保留，其余五个 unresolved。
- 真实容器验证聚合内存 OOM、PIDs 上限、tmpfs ENOSPC、网络无路由、输出上限、setsid 子进程清理与新容器状态重置。
- **10 个文件交接用例**通过：正常交接安全完成，危险 observation、capture 与父路径替换被拒绝；假私有内容没有泄漏或被覆写。另验证绝对/相对路径、共享 tmp、跨 trial canary 和只读测试输入。
- 捕获实际 CLI 序列化请求，发现禁用参数后仍存在 collaboration 和 MCP resource 入口。fixture 只在 loopback 返回拒绝，不转发、不调用模型、不执行合成工具调用。

### 阻塞与不变项

- 完整工具限制与容器路由仍未验证；专用 home 的支持式 login status 仍为未登录；agent 停止后的安全源码导出尚未接通。真实 agent 启动门禁保持关闭，不把资格控制结果作为模型能力分数。
- Eval 的 base、任务、hidden tests、Oracle、mandatory、阈值、四个维度及 H02 决策均未改变，21 项 Eval lock 验证通过。
- 同解释器/同 UID 的 grader 干扰不属于已证明的防作弊能力；controller/daemon 崩溃时仍需人工停止专用 VM。

实验及提交范围：[实验索引](runtime/evidence/container_readiness/README.md)、[完整控制结果](runtime/evidence/container_readiness/controls/)、[中文执行报告](runtime/container_readiness_report.md)、[复现命令](runtime/container/README.md)。原始认证 home、运行工作区、下载缓存和 VM 状态不入 Git；其他任务的 `analysis/` 目录不纳入本次提交。

## 已有 runtime 历史

- `ffc25b5`：修复 controller/worker 文件交接，详见 [安全报告](runtime/handoff_security_report.md)。
- `16fe50b`：实现 native runtime、独立 grading adapter 与确定性资格链路，详见 [实现报告](runtime/implementation_report.md)。
