# Stage 4 — Evaluation Quality

状态：**EVAL_READY_FOR_COMPARISON**，限定为当前固定题目、受监督执行和已声明行为合同。
建议保持 `pytest_5786` **v0.1.0 不变**；没有确认 P0 或需要评分变更的 P1。
本轮零模型调用，没有认证注入，未修改 Harbor、Runtime、历史基线、原 Oracle 或 Pilot 证据。

## 主要结果

1. Eval 直接测量提交代码在异常 producer、报告编解码、TestReport/CollectReport、xdist、
   terminal/JUnit 之间的行为保持，以及指定邻近合同的无回归。它不能直接证明 Agent 的内部根因推理。
2. B 的跨类型/结构化消费、C 的合法边界、D 的 ordinary/native 回归提供不同诊断信息；
   A/B/C 会因同一丢链缺陷共同失败。C03/D03 逻辑重叠但能区分“没修好”和“新增崩溃”。
3. 真实 Agent 补丁的原 PASS 有行为支持，独立重评仍为四维全通过，13项状态与原 Pilot 一致。
4. 在有限的11个对照中未确认 false positive 或 false negative；不能把该结果解释为零误判率。
5. 没有确认新的 mandatory coverage gap。原生表示疑点被已有 D02 保护，跨版本 wire 兼容则不是已建立的任务要求。
6. 三个新诊断：chain_assumed 被 D02 拒绝；links_omitted 被 A/B/C 拒绝；sections_omitted 被 B/D 拒绝。
   它们增强了对检查区分能力的证据，没有导致重复隐藏测试。
7. 只新增能力矩阵、补丁审查、覆盖分析、改进提案、诊断控制及报告脚本。没有修改评分规则、题面或版本，H02 仍是诊断项。
8. 重评11个补丁、143项检查；原七对照91项状态全部匹配，归档 Agent 13项全部匹配；
   infrastructure_status 均为 ok。原 grader 的7项合同测试通过。165个隔离 worker 收据确认停止和删除。
9. 可以开始预先定义的同条件 Agent 比较；**尚未证明 Agent-level discrimination**，目前真实有效样本仍只有一个。
10. 下一高价值动作是独立 Agent 样本与预注册比较计划。若需要区分更强 Agent，应优先规划独立问题覆盖，
    而非因某次53秒通过就增加本题隐藏难度。

## 交付与证据

- [能力矩阵](capability_check_matrix.md)及 [结构化矩阵](capability_check_matrix.json)：逐项列出行为、组件边界、能力证据、错误方案、重叠和来源。
- [真实补丁审查](real_patch_review.md)：已验证观察、合理假设与未验证担忧分开。
- [误判与覆盖分析](coverage_assessment.md)：H02 政策、同版本/跨版本合同及两种区分力。
- [优先级提案](stage4_proposal.md)：CONFIRMED / PLAUSIBLE / NOT_SUPPORTED，实施收益和误拒风险。
- [诊断结果](diagnostic_results.md)及 [完整 JSON](diagnostic_results.json)：四维、mandatory/diagnostic 失败、异常文本、执行记录和源码解释。
- [原始重评汇总](evidence/summary.json)、[真实补丁重评](evidence/first_real/result.json)、
  [精选文件清单](evidence/evidence-manifest.json)、[不变性审计](integrity.json)。

结果中的 `error`（例如 historical 的 C03/D03）表示 stdlib unittest 捕获到候选代码异常，
不是 infrastructure_status=error。原始详细结果和失败 traceback 均保留；没有把失败检查改成 pass。
目前仍使用已有 worker 隔离，候选与行为检查共享解释器的抗作弊限制没有在本阶段解决。

## 复现

从仓库根目录执行，输出目录必须新建。仅重评补丁，命令不调用 Agent、不需要真实凭据。
Docker endpoint、镜像、CPython 3.8.20 和依赖与已资格环境一致。

```sh
harbor/.venv/bin/python -B pytest_5786/iteration/build_diagnostics.py
harbor/.venv/bin/python -B pytest_5786/iteration/run_controls.py \
  --output runs/stage4-new-run
harbor/.venv/bin/python -B pytest_5786/private/qualification/test_grader_contract.py
harbor/.venv/bin/python -B pytest_5786/iteration/summarize_results.py
```

最后一条默认检查已归档的 evidence，不会自动切换到新 run。新的实验目录可用既有
`harbor.curate_pilot.curate(source, target)` 保存，再向 summary 脚本传 `--evidence`。
本次原始工作区和完整运行日志保留在 `runs/stage4-v010-20261017/`（Git 忽略），
精选结果/执行收据包含完整 grader 观察与断言失败；没有把原始源码快照或镜像加入 Git。
本阶段的所有交付都放在 `pytest_5786/iteration/`；本轮只本地提交，不 push。
