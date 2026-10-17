# Agent 写代码所需运行要素：pytest #5786 实测清单

审计范围是此仓库的 **Harbor 0.24.0 → Codex 0.162.1 → pytest #5786** 路径，
不是所有 Agent 产品的通用依赖声明。审计使用固定本地响应驱动原生 CLI，零真实模型调用，
没有尝试修复 pytest 题目。后续最小集成修复和资格结果见 [PILOT_REPORT.md](PILOT_REPORT.md)。

## 已确认的故障及最小修复

1. **C / 工具执行：缺少 Code Mode host，阻断真实 Trial。**
   `pilot-real-02` 的 `codex.txt` 明确记录 `failed to spawn code-mode host ... host executable was not found`。
   CLI 能报告版本、连上模型、正常退出，但两个工具均未执行。
   原 builder 只复制 `bin/codex`；修复为保留完整六文件包及目录结构，记录各文件 SHA256。
   复现命令：`harbor/.venv/bin/python -B harbor/audit/offline_tools.py --image <image-id> --output <new-directory> --temporary-home`。
   当前旧镜像重建证据见 `evidence/runtime-audit/runtime-audit-tools-current/result.json`；完整包对照见同目录的 `runtime-audit-tools-complete/result.json`。

2. **A/C / 实际工具环境：登录 shell 换错 Python，阻断测试。**
   `exec_command` 默认登录 shell 选择 `/usr/local/bin/python`，导入源码 pytest 时缺 `atomicwrites`。
   它和 venv 的 Python 都显示 3.8.20，故只查 `python --version` 不够。
   Harbor 外层 `bash -c` 的 PATH 正确，并不保证内层 `bash -lc` 正确。
   修复为镜像 `/etc/profile.d/pytest-runtime.sh` 恢复固定 venv/CLI 路径，明确使用系统 Bash。
   原生工具预检分别验证默认登录 shell 和 `login=false` 的 `sys.executable`、依赖及 pytest 导入位置。

3. **C / 辅助命令：缺 rg；临时 CODEX_HOME 禁止 CLI 创建 PATH 别名。**
   完整包的 `codex-path/rg` 可以运行；原单文件镜像没有 rg。
   CLI 提示 `Refusing to create helper binaries under temporary dir /tmp`。
   将原生 adapter 的 CODEX_HOME 改为临时容器中的 `/home/agent/.codex`，保留原生认证清理。
   原生 `tools.apply_patch` 在旧的临时 HOME 下也能工作；不能把“shell 找不到 apply_patch”误报为所有编辑功能失效。
   登录 shell 仍可能丢弃动态 helper PATH；非登录 shell 别名和原生 apply_patch 已实测。

4. **E/F / 结果分类：工具基础设施坏了却产生有效完成标志，阻断可信评测。**
   `pilot-real-02` 返回正常 CLI 退出码，旧 runner 将空补丁送去评分并报告 `live_completed=true`。
   原 grader 对空补丁输出合法，但它不是 Agent 能力结果。
   修复为原生命令管道启用 pipefail；检查 harness error/turn.failed/turn.completed；
   未健康完成时冻结并保存日志，但在提交收集及评分前拒绝。
   普通 shell 非零退出、测试失败和健康 No-op 不被错误归类为基础设施异常。

5. **G / 原生配置权限：此前已修复。**
   `pilot-real-01` 在配置 `chown && chmod 600` 被过窄白名单拒绝后终止。
   只允许原生认证及配置的精确所有权命令，以文件所有者 UID 1000 执行，未赋予候选 root 权限。
   假认证预检继续检查该路径和原生 finally 清理。

6. **A/C / 新发现：后台插件克隆耗尽 HOME，阻断轨迹保存。**
   带公网的原生预检偶发 `No space left on device`，64 MiB HOME 的可用空间为零。
   `home-usage.json` 证明 `.tmp/plugins-clone-*` 正在克隆未使用的插件 marketplace：仅 Git pack
   已约 25 MiB，其余插件资源耗尽剩余空间。不是模型调用或 pytest 依赖造成。
   关闭本 MVP 不使用的 plugins/apps/remote_plugin/skill search 和 multi_agent，保持资源边界不变。
   修复后同路径预检通过，HOME 仍有 66,060,288 bytes 可用，无 plugins-clone。
   本地 Responses fixture 没有向上游转发；修复前 CLI 自身确有后台公网下载，不能把那几次预检称为完全断网。

7. **E/G / 新发现：0600 新文件不能由只有 CAP_KILL 的 root 读取。**
   合成完整控制上传的新 normalization.py 使用 0600；旧 root 采集报 PermissionError。
   修复为 root 只执行进程终止，再用 UID 1000 的全新 controller exec 运行不可变 Python -I
   做 metadata/hash/archive；保留限制，不增加 DAC capability。合成控制覆盖新文件、旧文件及后台进程。

8. **G / 合成 verifier 的默认用户。**
   Harbor 会按 phase 配置覆盖环境默认 UID；不声明 verifier.user 时以 root 执行，Git 报 dubious ownership。
   合成 task.toml 明确 verifier.user="1000:1000"，与工作区所有者一致，隐藏检查也以非 root 运行。
   未通过 safe.directory=* 绕过所有权检查。

## 完整运行要素及当前证据

1. **控制器和支持接口。** 控制器 Python 3.13.7，独立 `harbor/.venv`，安装 Harbor 0.24.0。
   使用已安装 wheel 的 `Trial`、`BaseEnvironment`、原生 `Codex.run`、`BaseVerifier` 接口。
   上游 main 文档、旧机器报告不能替代本机安装版本证据。
2. **容器后端与客户端。** 本机既有 Colima，Docker socket 显式传入；task-local Docker config/HOME、
   Compose 和 Buildx 可用。Agent 不接触 Docker socket、宿主目录、凭据目录或 Docker API。
   “Docker CLI 存在”与“守护进程和构建/exec/upload/cleanup 均可用”分别验证。
3. **架构与 ABI。** 宿主和 Linux guest 为 arm64；CLI/host 为 Linux aarch64 musl 静态二进制。
   打包的 rg 可运行，bwrap `--help` 可运行；打包 zsh 要求 GLIBC_2.38，在基镜像不可运行。
   本路径显式使用兼容的 Bash，未升级基镜像/依赖。bwrap 的 namespace 执行未作为本路径依赖验证；
   Codex 使用原生 bypass 模式，外层 Docker 提供限制。
4. **完整 CLI 发行包。** 需要 `bin/codex`、`bin/codex-code-mode-host`、`codex-package.json`、
   `codex-path/rg`、`codex-resources/bwrap`、`codex-resources/zsh/bin/zsh` 的完整布局。
   记录 version、target、entrypoint 和所有文件哈希。包内存在不等于每项都能在此 ABI 上运行；见上一项。
5. **运行时与工具分层。** 当前原生 Code Mode 使用自己的执行器。Node/npm 不存在也不阻断本次
   `functions.exec → exec_command/apply_patch/write_stdin`。npm 安装路线、额外 Node REPL/MCP
   可能另需 Node，但未使用，不能据此宣称所有扩展已就绪。
6. **模型和认证。** 固定声明 `openai/gpt-6.1-sol`，实际交给 CLI 的模型名为 `gpt-6.1-sol`。
   旧 real-02 已证明当时认证和模型调用可达；离线预检不能证明将来的登录有效性、额度或模型可用性。
   原生 Harbor 临时上传指定 auth.json，同 UID 的候选命令可读且能公网外传；需要每次真实 Trial 的明确授权。
   不打印/提交/烘焙凭据，假认证与真实凭据严格区分。
7. **网络与信任边界。** Agent 使用 bridge/public，模型请求和候选命令共享 egress；没有伪称端点隔离。
   verifier/每检查 worker 使用 network none。管理 TCP 2375/2376 不可达；无宿主 bind/设备/端口发布。
   本地 Responses fixture 只监听容器 loopback，没有 upstream，提供固定响应，不是生产 gateway。
8. **会话与上下文。** 每 Trial 新容器、新 CODEX_HOME，无 resume/load、宿主历史、开发对话或宿主配置。
   原 instruction.md 逐字一致，基线及完整 CLI 构建输入绑定预检哈希。
   tools 可用不代表被实际使用；修复前离线工具清单包括 collaboration，但没有调度子 Agent；当前显式关闭 multi_agent。
9. **任务身份。** Eval 0.1.0，原锁 SHA256 `067f222eccfbf8d40fe520a7f4196426e82a4e5d4861e506cb96e60d11732e03`。
   上游 base `955e54221008aba577ecbaefa15679f6777d3bf8`；公开导出产生独立单提交基线
   `41ffd0de9c7ece927733fadc2201491c5ae51be2`。二者用途不同，不能把合成 Git HEAD 当上游 commit。
   复用原 prepare/export，验证公开文件清单及 SHA；无上游历史、remote、alternates、隐藏测试或 Oracle。
10. **Python 与依赖。** `/opt/pytest-python/bin/python`，3.8.20，原精确 requirements，xdist 1.29.0，
    `PYTHONPATH=/work/src`，`pytest.__file__=/work/src/pytest.py`，禁用插件自动加载。
    源码导入的 pytest 没有已安装 distribution metadata 是预期行为，不是缺依赖。
    启用 xdist 需原 instruction 中的 `-p xdist.plugin`；只传 `-n` 会失败。
11. **工作区与 shell。** 固定 `/work`、UID 1000 可写源目录；PATH、HOME、SHELL、工作目录、环境变量
    必须同时覆盖 Harbor 外层和 Code Mode 内层。固定系统解释器用于可信采集，不能被候选 PATH 替换。
12. **工具实际闭环。** 原生固定响应测试涵盖读/搜索、文件创建、apply_patch、默认/非登录 shell 测试、
    PTY 与 write_stdin、非零退出码传回。只检查版本、文件存在、setup 或 API 返回成功都不充分。
    测试源文件与题目无关；公开 reproducer 两个用例本来就应失败，本地/xdist 的失败被明确断言。
13. **资源和超时。** CPU 2、内存 4GiB、swap 0、PID 128、只读 rootfs、cap-drop ALL、NNP；
    写入限于四个定额 tmpfs，单文件和输出上限，传输进程组超时及候选子进程停止。
    原配置 agent 1800 秒、verifier 1800 秒分别计时，不能称为端到端 1800 秒硬截止；
    这是待真实 Trial 授权时必须明确的预算语义，不用基础设施失败冒充未解题。
14. **提交冻结。** AGENT_END 停止并杀死所有内核 UID 含 1000 的进程，包括 nondumpable/脱离进程。
    随后以 UID 1000 启动受信任不可变解释器（-I）读取 owner-only 源文件；不能边写边打包，也不能依赖候选“我完成了”的说明。
15. **允许提交的内容。** 只接受受限 `src/**/*.py`，新文件可进入提交；保护版本 shim。
    拒绝链接、特殊文件、目录逃逸、重复 tar 路径、非 UTF-8、越限与异常执行位。
    限制为单源文件 2MiB、合计 16MiB、10,000 entries；不信任候选 Git config/index/hooks。
16. **补丁与交接。** 可信干净 baseline 生成 patch；在 fresh export 应用并比对整个允许源树的字节哈希。
    原生工具创建的 harmless source 已进入该链路，再传入新建的无网络 verifier 验证。
    “复制成功”不能替代 baseline/patch/最终字节一致性。
17. **评分边界。** `environment_mode="separate"` 保留；原 `private/grader.py`、检查 ID、四维、阈值和 H02
    诊断属性均不改。可信评分控制器在宿主，候选 Python 每次在全新受限 worker 执行。
    Oracle、controller credentials 和可信 result 文件不进入 worker；候选与行为检查共用解释器的反作弊限制仍存在。
18. **状态机。** 区分环境/认证/工具/网络/交接/评分/权限失败和真正代码失败；测试失败允许，基础设施失败拒绝评分。
    健康空工作区可作 No-op。CLI exit 0、Harbor reward 文件存在和 grader infrastructure=ok 各自都不单独证明 Agent 成功运行。
19. **证据可复现性。** 保留版本、基镜像/实际镜像 ID、Eval 锁、task+adapter+bundle 哈希、时刻、native/ATIF轨迹、
    工具输出、最终 patch、完整 grader JSON、mandatory statuses、四维和 infrastructure状态。
    旧失败记录不覆盖；假响应的 0 token/0真实调用不能计入真实模型结果。
20. **生命周期与操作约束。** 新输出目录禁止覆盖/重复试跑，真实 Trial 不自动重试；结束删除容器并留 receipt。
    原生认证清理加容器销毁降低暴露时长，不能阻止运行期间窃取。
    证据整理排除工作区和认证，扫描后才提交；只提交 Harbor，保留其他改动，不 push。

## 复现入口

- 旧/完整包工具对照：`harbor/audit/offline_tools.py --help`，有独立 network-none 容器。
- 运行包/ABI 清单：`harbor/audit/runtime_inventory.py --help`。
- 修复后的原生 Harbor 预检：`harbor/pilot/live_preflight.py --task <built-live-task> --output <new-directory>`。
- 资格控制：`harbor/pilot/run.py --task <built-controls-task> --output <new-directory> --image <qualified-base-id>`。
- 故障证据：`harbor/evidence/runtime-audit/summary.json` 及逐文件 manifest。

完整包审计证明工具具备执行能力；只有授权后的真实 Trial 才能证明此任务的模型→工具→提交→评分端到端能力。
