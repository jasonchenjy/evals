# pytest #5786 Eval v0.1.0

最新 Complete Oracle 专项复核见 [资格报告](qualification_report.md) 和 [机器结果](private/qualification/oracle_recheck_20261016/summary.json)。Oracle 补丁未改；修复了父 Git 仓库导致 snapshot 补丁被静默跳过的 grader 问题。重跑 11 项必测与全部诊断通过，另有 32 项结构/serial/xdist 补充检查通过。原始 package creation 的资格日志及 manifest 中的原结果引用保留，最新复核使用更新后的核心锁。

一个固定任务的 **experimental / qualification-only Eval Package**。已经执行本机确定性资格验证，可由下一阶段 Runtime 按下述接口接入；尚未获得安全运行不可信 Agent/补丁的资格。没有 Agent Runtime、模型调用、模型比较或通用任务生成器。

目标能力：**Cross-Component Reasoning & Bug Fixing**。提交必须是可运行的源码修复；主结果是所有必测行为均满足的布尔值，没有加权平均分。仓库 `pytest-dev/pytest`，base `955e54221008aba577ecbaefa15679f6777d3bf8`，公开 Verified 实例 `pytest-dev__pytest-5787`。

## 文件与可见性

| 文件 | 用途 | 给 Agent 吗 |
|---|---|---|
| [task.yaml](task.yaml) | 控制面 manifest：身份、接口、预算、私有路径、资格结果引用 | **否** |
| [instruction.md](instruction.md) | 用户问题及源码提交要求 | 仅由 exporter 复制为 TASK.md |
| [environment.yaml](environment.yaml) / [requirements.txt](requirements.txt) | 环境/隔离合同、完整固定依赖 | 仅 requirements 的公开副本 |
| [prepare.py](prepare.py) / [base_files.json](base_files.json) | 从固定 Git 对象导出源码并逐文件校验，建立单一 synthetic baseline commit | 控制器执行，不整个暴露 |
| [tests/public/test_example.py](tests/public/test_example.py) | 原问题两条故意失败的公开复现 | 是，导出为 eval_public |
| [private/test_catalog.json](private/test_catalog.json) / [private/tests/behavior.py](private/tests/behavior.py) | 11 个必测项、2 个诊断项及逐项合同来源 | **否** |
| [private/grader.py](private/grader.py) / [private/check.py](private/check.py) | 接收 source patch、干净重建、私有行为测试、四维 JSON 结果 | **否** |
| [private/oracle](private/oracle) | no-op、历史、完整、替代与负对照 patch；单独审查记录 | **否** |
| [private/qualification/summary.json](private/qualification/summary.json) / [qualification_report.md](qualification_report.md) | 最终控制矩阵、日志索引、限制 | **否** |
| [checksums.json](checksums.json) / [delivery_hashes.json](delivery_hashes.json) | 已执行核心材料锁与最终交付文档/结果校验 | 控制面专用 |

两个 `.yaml` 文件采用 JSON 语法（合法 YAML 1.2 子集），可直接用 Python 标准库 json 读取，无需另装 YAML parser。**不能将整个 Eval 包挂载给 Agent**；manifest 含私有位置和校验信息。只有 prepare.py 的 allowlist 输出才是 Agent payload。日志和结果中的隐藏测试名称也不应在 trial 中反馈给 Agent。

## 初始环境准备

本轮复用先前下载的 CPython 3.8.20，在本包新建 `.venv`，没有改动旧研究 venv。宿主为 macOS arm64。最终依赖记录见 [private/qualification/environment_freeze.txt](private/qualification/environment_freeze.txt)；安装经过、一次已解决的 sandbox installer 失败和实际命令见 [private/qualification/setup_commands.json](private/qualification/setup_commands.json)。

新 Runtime 的推荐安装方式（执行前准备可信 Python 3.8.20）：

```sh
/path/to/python3.8 -m venv /runtime/deps
/runtime/deps/bin/python -m pip install --no-deps -r /eval/requirements.txt
```

`--no-deps` 很重要：这些已列全的 pinned 依赖包括 xdist；自动依赖求解会另装现代 PyPI pytest。目标 pytest 应从固定源码的 `src` 导入。初始 interpreter/wheel provisioning 可以联网；trial 开始前冻结环境。离线安装可预备对应平台 wheelhouse，然后使用 `pip install --no-index --find-links=/wheelhouse --no-deps -r /eval/requirements.txt`。本轮没有构建跨平台 wheelhouse；下一 Runtime 不应假定 macOS venv 可直接搬到 Linux。

每次评分 preflight 在**未应用补丁的 base**上验证 Python 恰为 3.8.20、各直接依赖版本与 pytest 导入，并记录路径/版本；不把安装错误作为 Agent 失败。pip 的 transitive dependency checker 会因历史 pytest 来自源码而缺少 wheel distribution metadata；这不应通过安装另一个 pytest 来“修复”。

`git archive` 缺少 setuptools-scm 生成的 `_version.py`，exporter 只增加同一固定版本模块 `version = '5.1.0'`。它是 release-family 引导值，不声称为该 commit 的精确发行版本；身份以 base SHA 和 [base_files.json](base_files.json) 为准。

## 1. 创建 Agent 可见工作区

可信控制器持有包含 base 对象的 Git 仓库，并调用：

```sh
python3 /eval/prepare.py --repo /trusted/pytest --destination /trials/0001/workspace
```

destination 必须不存在，防止复用脏工作区。输出包括固定 base 源码/原公开测试、TASK.md、两个公开示例、公开依赖清单与不含私有信息的 eval_public.json。Git 只有一个可复现日期/作者的 synthetic baseline commit，没有原 history/remote；这样 Agent 能用正常 `git diff HEAD -- src/` 提交。

运行环境设置：`PYTHONPATH=/trials/0001/workspace/src`、`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`、`PYTHONHASHSEED=0`、无用户 site packages；其他确定性变量见 environment.yaml。用固定 venv 的 `python -m pytest`，不要调用别处的 pytest console script。公开示例的两个测试始终故意抛错；修复后应改善诊断，退出码仍非零。

只允许提交 `src/` 下常规 `.py` 文本修改/新增/删除，排除生成的 `_pytest/_version.py`。不接受 tests/config/dependencies、符号链接、mode 修改、rename/copy 或 binary patch。源码最多 1 MiB，UTF-8 Git unified diff；空文件代表 no-op。新增源码可 `git add -N` 后收集 diff。Agent 可另写本地 debugging tests，但不得将这些文件作为提交内容。

## 2. 私有 Grader 的精确接口

这是本轮**已审阅控制补丁**实际使用的接口：

```sh
python3 /eval/private/grader.py \
  --repo /trusted/pytest \
  --python /runtime/deps/bin/python \
  --patch /submissions/submission.patch \
  --output /grading/0001 \
  --trusted-local
```

`--output` 必须是新的目录；不会覆盖旧结果。控制面可用 Python 3.8+，测试解释器必须 3.8.20。`--trusted-local` 只是明确承认本机运行已审阅的确定性控制，**不是安全隔离开关，不能用于宣称不可信 trial 已安全**。缺失该标志时当前 CLI 拒绝执行并返回 infrastructure error。

流程：检查固定 Eval 核心 hashes → 导出新的 base → preflight → 校验补丁路径及 `git apply --check` → 应用源码补丁 → 应用 curator 的历史 testing patch → 在独立子进程运行每个私有检查 → 汇总 JSON。Agent 工作区、测试修改、Git index、缓存和输出都不进入评分，只导入提交 diff。每个评分都有新的 HOME/TMPDIR、源码与测试缓存；重用依赖镜像应为只读。

stdout 返回简短 JSON 索引，完整结果固定为 `<output>/result.json`，`schema_version=1`。核心字段：

- `dimensions.original_bug_resolution / cross_component_consistency / edge_case_robustness / non_regression`：`satisfied` 布尔值或未运行时 null，以及具体 check 状态。
- `overall_resolved`：所有 mandatory checks 通过且所有维度通过才为 true；diagnostic 不参与主判定。
- `infrastructure_status`：`ok` 或 `error`。`submission_status` 区分 accepted/rejected/pending。
- `tests`：ID、mandatory、维度、passed/failed/error/skipped/timeout/execution_error、argv、cwd、rc、耗时、原始日志与观察。
- base、package lock、patch SHA256 和时间戳，用于关联精确输入。

退出码 **0=resolved，1=未解决/提交被拒，2=基础设施或控制面错误**。外层 check 的 `error` 表示候选执行中抛异常，不等同于 infrastructure error；原参考的 AttributeError 就属于前者。所有 mandatory skips、少跑/重复/未知 ID、collection errors、timeouts、缺失或不合法 observation 都不能获得成功。嵌套 B03 用例故意失败/收集失败，由外层检查验证其输出、真实 worker 和 JUnit 错误内容；其非零退出码不是基础设施错误。

## 3. 下一 Runtime 必须提供的隔离

本包没有实现 VM/container orchestration。下一 Runtime 应将可信控制面和不可信执行域分离：

1. Agent 域只能挂载 allowlist export、只读依赖与本 trial 的 writable scratch；无 curator 包、上游 Git、secret、网络或其他 trial。
2. 评分控制面持有 manifest、参考、hashes、patch 校验和结果聚合。准备新的 patched snapshot 后，评分 worker 只得到必要的源码、只读测试、check.py 和依赖；**oracle 和资格日志不可挂载给候选代码**。
3. 现有 grader 的 `run()` 是本机 launcher。Runtime 必须将 worker 启动适配为其真正的隔离执行设施，或提供等价隔离 worker 接口；不能只在同一宿主开启普通临时目录。worker 接口为 Python 3.8.20 执行 `private/check.py --method <catalog.method> --output <observation.json>`，环境提供 `EVAL_WORKSPACE`、`EVAL_SCRATCH` 和确定性变量。传回 observation、日志、退出码、超时状态，由可信控制面验证和聚合。
4. 强制 wall/CPU/memory/process/disk/network 限额；建议 trial 1800s、2 cores、4096 MiB、128 processes、2048 MiB disk。此处本机只实现 check wall timeout 和进程组清理，其余是下一 Runtime 的要求，**不是已实施能力**。
5. 每次新的环境须先重放 no-op / complete oracle，遇到机器故障、平台差异或资源异常时将 trial 标记无效并复核，不能靠 preflight 成功就断言后续错误一定来自 Agent。

普通 venv 不构成安全沙箱。即使有 OS 隔离，候选 Python 与私有检查仍可能共享解释器；恶意代码篡改测试框架/伪造结果的完整防护也未获资格验证。当前目标是功能正确性评测的可靠控制与清楚接口，不是对抗性代码执行服务。

## 4. 重放资格验证

```sh
cd /Users/junyuc/Documents/interview/SWE-bench
python3 evals/pytest_5786/private/qualification/test_grader_contract.py
python3 evals/pytest_5786/private/qualification/qualify.py \
  --repo pytest \
  --python evals/pytest_5786/.venv/bin/python \
  --output /private/tmp/pytest-5786-new-qualification
```

第二条只运行固定 7 个源码控制态，不调用任何模型。目录仍须全新。完整 oracle 和替代实现应 overall=true；no-op、历史参考、三个负对照应 false，并满足特定失败边界。历史参考同时充当“正常链能处理，但合法缺失 traceback 会崩溃”的第四类负对照，无需重复运行同一 patch。

## 已确认的资格与限制

最终结果见 [qualification_report.md](qualification_report.md) 和 [private/qualification/summary.json](private/qualification/summary.json)。11 个 mandatory / 2 个 diagnostic；完整 oracle 全通过。替代实现通过全部 mandatory，完整旧 suite 有一个 wire-layout 诊断失败，已经显式保留。必测既有 suite 为 118 个精确命名用例；完整 125 个 suite 的诊断结果与前者重叠，不能相加当独立覆盖量。

仅资格验证了 macOS arm64 + Python 3.8.20。本题公开属于 Verified，训练污染无法排除；单题不能支持统计意义上的模型区分结论。两个实现通过仅证明所测范围内的一部分替代解公平性。没有 Agent pilot trials，也没有据模型结果调整 oracle。

核心源码/测试/配置在最终控制运行前已用 checksums.json 锁定；交付文档和记录由 delivery_hashes.json 另行封存，避免为更新文字而改动已执行的核心锁。以后修改行为、环境或评分应更新版本、重跑所有控制、记录变更，随后再冻结用于正式比较。
