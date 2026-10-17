# Harbor Agent readiness

结论：**AGENT_READY（本机、单用户、监督式 MVP）**。一次新授权的真实 Codex 合成 Trial
完成了读代码→定位初始失败→修改多个文件→新增 helper→复测→提交→独立隐藏验证。
**本轮没有运行真实 pytest #5786 Agent Eval，也没有重试真实模型 Trial。**

## 真实执行证据

- Harbor **0.24.0**，Codex **0.162.1**，`openai/gpt-6.1-sol`；全新容器与会话。
- 固定合成 base：`adb1b8fe6fd81e25b880f3bdee2adb74e1ca306d`。
- UTC 2026-10-17 07:39:22.976964 至 07:39:59.867005，共 **36.89 秒**；Agent 阶段 **21.25 秒**。
- 轨迹 **11 steps**，5 个 Code Mode exec 调用，实际包含 5 次 shell 操作、1 次多文件编辑。
- 初始公开测试 exit=1，`KeyError: quantity`；修改后 exit=0，自行增加的边界检查也通过。
- 修改 parser/service/validator，新增 normalization.py；可信补丁包含全部四个源文件。
- 独立 verifier 的 **3 个隐藏测试方法**（含参数化子用例）通过，`reward=1`，infrastructure=ok。
- Agent / verifier 容器 ID 不同，均已删除；仅源文件过边界，凭据和 Agent HOME 不传入 verifier。

证据：[原生工具输出](evidence/agent-readiness-real/codex/agent/codex.txt)、
[完整轨迹](evidence/agent-readiness-real/codex/agent/trajectory.json)、
[最终补丁](evidence/agent-readiness-real/codex/submission/submission.patch)、
[独立结果](evidence/agent-readiness-real/codex/verifier/result.json)、
[隐藏测试输出](evidence/agent-readiness-real/codex/verifier/hidden-tests.txt)。

## 能力判定

1. **PASSED — 启动与新会话。** 原生 Harbor Codex Adapter 成功；没有加载开发会话或旧 trajectory。
2. **PASSED — 阅读与定位。** 真实 Agent 用 `pwd`、`rg --files`、`cat` 阅读三个模块和公开测试；
   关联 service 调用和 validator 报错。实际 Agent 没有单独使用按函数名内容搜索命令；该具体操作由
   补充无模型环境诊断验证，不能算成真实 Agent 已使用过。
3. **PASSED — 编辑与新增文件。** 原生 apply_patch 修改三个文件、创建 normalization.py；后续工具调用
   导入新 helper、运行测试、查看 Git diff/status，采集结果与 verifier 字节哈希一致。
4. **PASSED — 执行与反馈。** Python、公测、Git、错误栈与非零退出码均在真实轨迹中出现。
   PTY/write_stdin 和明确 stdout/stderr 标记由离线工具/环境诊断验证；传输保留合并输出。
5. **PASSED — 多步调试。** 真实 Agent 先看到失败，再跨模块修复并复测通过，第一次编辑就完成修复。
   **未宣称真实 Agent 经历过“第一次修复仍失败”**；这条循环在独立 Complete 脚本控制中执行，
   包含初始失败、错误编辑后的失败、修正后通过。没有强迫模型制造错误或重试刷分。
6. **PASSED — 持久工作区。** 所有真实 shell 在 `/work`，修改跨工具调用可见，Git 显示三项修改和新文件；
   临时 debug 文件不进入 source patch。
7. **PASSED — 超时与进程清理（脚本诊断）。** Complete 控制触发 0.5 秒有界超时，结束时杀死所属
   parent/脱离子进程；随后确认源文件 mtime 不再变化。未做资源耗尽实验。
8. **PASSED — 独立验证与提交。** verifier 从固定干净基线开始；只传允许源文件补丁并逐文件比对。
   隐藏测试仅在独立 verifier 执行。No-op FAIL / Complete PASS / Incomplete FAIL 全部符合预期，
   Incomplete 公开测试通过但隐藏测试失败，证明验证器不是简单复述公开结果。
9. **PASSED — pytest 环境，不是解题。** 原上游 base `955e54221008aba577ecbaefa15679f6777d3bf8`，
   CPython 3.8.20、精确依赖、xdist 1.29.0、`pytest.__file__=/work/src/pytest.py` 均已实测。
   默认登录/非登录 shell 都使用固定 venv；公开 serial 和显式 `-p xdist.plugin -n 2` 各产生预期的两个失败。
10. **PASSED — 边界和授权。** 精确公开文件清单、无隐藏文件/Oracle、无宿主 bind/socket、非 root 工具、
    只读 rootfs、受限 tmpfs/capabilities 经过检查。用户为这一次合成 Trial 明确批准临时认证暴露和公网。
    candidate 仍能读取该认证并外传；没有声称认证隔离。真实执行结束后原生清理及容器删除完成。
11. **PASSED — 失败分类。** CLI pipefail + harness error/turn 检查拒绝基础设施失败；不会把它计成有效空提交。
    普通测试失败和健康 No-op 保持可评分。23 项针对性测试通过。
12. **NOT_VERIFIED — 真实 pytest 编码能力、其他平台/模型、生产级抗作弊。** 均不在本轮结论内。
    旧 real-02 的空补丁 0/0/0/1 不是模型能力分数；本轮合成 reward=1 也不能当作 pytest 得分。

脚本及环境证据：[合成控制](evidence/agent-readiness-controls/summary.json)、
[调试循环](evidence/agent-readiness-controls/complete/agent/diagnostic.json)、
[进程清理](evidence/agent-readiness-controls/complete/process-check.json)、
[原生工具预检](evidence/agent-readiness-environment/tool-preflight.json)、
[环境与任务绑定](evidence/agent-readiness-environment/summary.json)、
[补丁往返](evidence/agent-readiness-environment/roundtrip.json)、
[23 项测试](evidence/agent-readiness-environment/focused-tests.txt)、
[跨文件内容搜索及输出诊断](evidence/agent-readiness-search/summary.json)。

最终共享交接修复后，既有 pytest 七组确定性控制也已复验：**7/7 符合预期，91/91 Check 状态与原基线一致**，
四维与 Overall 均未变化，全部 infrastructure=ok，H02 仍是诊断项。这是已知补丁资格验证，不是模型解题。
[完整资格结果](evidence/agent-readiness-qualification/summary.json)。

## 确认并修复的问题

- 缺 Code Mode host / rg：复制完整六文件 CLI 包并保留布局，校验包哈希。
- 登录 shell 选择缺依赖的系统 Python：固定镜像 profile PATH；保留原 Python/依赖版本。
- 临时 CODEX_HOME 拒绝 helper aliases：移到容器内独立 HOME；shell 登录模式仍可能重置动态 alias，原生编辑工具正常。
- 默认后台插件克隆占满 64 MiB HOME：禁用本 MVP 未使用的 plugins/apps/remote_plugin 等功能；修复后 HOME 约 63 MiB 可用。
- CLI 退出正常掩盖工具/轨迹错误：加健康检查并阻止无效提交评分。
- 新文件 0600 导致无 DAC capability 的 root 采集失败：root 仅负责终止进程，之后以 UID 1000 的
  不可变 Python -I 执行采集。没有增加 capability 或放宽归档检查。
- 合成 verifier 默认 root 与工作区 owner 不同：显式 `verifier.user="1000:1000"`，不放宽 Git 安全检查。

失败证据保留在 `agent-readiness-home-failure`、`agent-readiness-source-failure`、
`agent-readiness-verifier-failure`；完整要素、复现入口及局限见 [RUNTIME_FACTORS.md](RUNTIME_FACTORS.md)。

## 后续最小步骤

Harbor 已能承担本 MVP 的 Agent/Trial 编排；仍复用现有 Runtime 的受限 worker、可信提交和评分适配，
不能因此删除全部 Runtime。下一步可以在一次新的明确授权下运行真实 pytest Pilot，之后关注 Evaluation Quality。
本次合成授权已消耗，不自动延伸到 pytest Trial。执行入口见 [preflight/README.md](preflight/README.md)。
