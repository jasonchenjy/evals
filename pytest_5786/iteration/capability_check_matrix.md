# Capability-to-Check Matrix

本 Eval 直接测量：给定固定历史 pytest 和统一任务合同，提交的补丁是否保存异常报告跨格式、报告类型、进程和消费者的可观察行为，同时不破坏指定邻近合同。它不能单独观测“根因推理”这一内部过程，也不要求修改多个源文件。

来源均为固定 base `955e54221008aba577ecbaefa15679f6777d3bf8`，而不是当代 pytest。下表实现依据为 [behavior.py](../private/tests/behavior.py)、[catalog](../private/test_catalog.json)、[instruction](../instruction.md)；历史源码快照在 [H02 来源目录](../private/qualification/h02_contract_20261016/probes/sources/)。

| Check | 直接行为 | 组件边界 | 支持的子能力 | 应拒绝的现实错误 | 重叠及限制 | 合法需求来源 |
|---|---|---|---|---|---|---|
| A01 | 两层显式 cause 的消息、顺序、连接文字及 failed 状态；含传输前 sanity check | ExceptionInfo → TestReport → hooks → JSON → 恢复报告 | 原缺陷修复：显式因果链可观察完整性 | last_only、links_omitted、noop | 与 B03 的显式链重叠；A01 为轻量对象路径，B03 验证真实进程和消费者 | 原 issue 显式示例；instruction 第1–3段；code.py repr_excinfo 的 __cause__ 分支 |
| A02 | 三层隐式 context 的消息、次序及两段 context 连接文字 | formatter 隐式 context → JSON → TestReport 渲染 | 区分 cause 与 context；多层信息保存 | 仅处理 __cause__、固定两层、遗漏连接关系 | 与 A01 共用 codec；输入语义不同，不能用 A01 代替 | 原 issue 隐式示例；code.py __context__/__suppress_context__ 分支 |
| B01 | CollectReport 类型、两层链、附加 section、captured stdout 保留 | collection producer → BaseReport codec → collector/terminal consumer | 跨报告类型与附加信息的行为一致性 | testreport_only、sections_omitted | 与 B03 collection 重叠，但 B03 没有此附加 section/capture 断言 | instruction 明示 collection、captured output、attached sections；CollectReport 继承 BaseReport |
| B02 | 最终 crash message/path/line、traceback entries、when/duration/keywords、stdout/stderr；传输后追加 section 并第二次往返 | 结构化 report → JUnit 所用 crash 字段/可变 sections → 再序列化 | 结构化消费者兼容、元信息与重复传输 | text_only、丢 metadata/sections、第二次传输损坏 | 与 B01 的 sections、D01 的普通 metadata 有交集；此处是链报告和二次往返 | junitxml.py reprcrash.message 消费；ExceptionRepr.addsection；BaseReport 字段与 hooks |
| B03 | 真实 gw0 的 call 与 collect、预期 exit=1、无 INTERNALERROR；终端及 JUnit 各含内外异常且只有一个 failure/error | xdist worker → hooks/JSON → controller → terminal/JUnit | 真实跨进程整合与两种消费者一致性 | testreport_only、只改本地显示、links_omitted；text_only 实际可通过 B03，须由 B02 拒绝 | 依赖 A/B codec 正确，失败可能级联；不能当独立统计试次 | 原 issue xdist 症状；固定 xdist 1.29.0 remote/workermanage；JUnit 输出合同 |
| C01 | from None 只显示最终异常，不泄露被抑制 context 或连接文字 | Python context 选择 → formatter → codec → 渲染 | 尊重合法异常显示语义 | 无条件遍历全部 __context__ 的修复 | 与 C02 chain=False 都会隐藏链，但一个是异常语义，一个是显示选项 | code.py 对 __suppress_context__ 的原有判断；instruction 的 Python context 语义 |
| C02 | 两种报告四层显式链；chain=False 仍只显示末端（显式断言排除最初层） | formatter 的 chain 参数/深度 → 两类 report → JSON | 深度泛化、配置语义保持 | 固定两层修复、忽略 chain=False | 与 A01/A02 的链保存重叠；扩展深度和显示选项；不等于任意深度证明 | ExceptionInfo.getrepr(chain=...) 原有接口与 repr_excinfo 循环 |
| C03 | 无 traceback 的有效 cause 内容、最终异常、连接文字及最终 crash 字段在两类报告保留 | native fallback/ReprEntryNative、reprcrash=None → codec → consumer | 合法稀疏元数据下的信息完整性 | historical：None.__dict__ 导致 AttributeError；丢弃 native cause | 与 D03 同一输入但更强：C03 要修复丢失的 cause，D03 只禁止新增崩溃 | code.py 既有无 traceback native fallback；instruction 要求合法 exception；#5971 本地来源证据 |
| D01 | pass/skip/string 报告两种类型的 outcome/nodeid/stdout；单异常文本/crash、extra Path/flag | ordinary reports → hook codec → 消费字段 | 邻近非链路径及额外属性无回归 | 修复时误处理非结构化 longrepr、丢 outcome/额外属性 | 与 B02 字段验证部分交集，但普通报告此前就在 base 上正确 | BaseReport 原合同与原测试；instruction normal single-exception reporting |
| D02 | 固定 inventory 的118个 reports/code/exception既有测试全部通过，零跳过/错误/xfail | 源码表示/formatter/report codec 与既有行为 suite | 广度回归；其中原生 traceback、locals、funcargs 等由真实既有断言保护 | chain_assumed：原生 ReprExceptionInfo 被错误当 chain；一般邻近回归 | 包含单异常/元数据等重叠；复合 check 的具体子测试比单个 D02 布尔值更有诊断价值 | 固定 base 测试 + 历史 helper relocation；排除7个 wire-specific 检查并由 H02 保留 |
| D03 | 有效无 traceback cause 在两种报告仍可传输、failed=true、显示最终错误 | 原本可用的 native cause → transport → outer-error consumer | 严格区分新增崩溃与原本丢链 | historical 的 None 编解码崩溃 | 逻辑上被 C03 的强条件包含，但分类有价值：noop D=true、historical D=false | base 对该输入本已不崩溃；原有兼容行为，非新增功能要求 |

H01/H02 均为诊断，不参加 Overall 或维度计算。H01 保留历史回归；H02 保留125个邻近既有测试（包括7个内部表示检查），不等于整个 pytest 测试集。Alternative 的特定 H02 失败不能否决有效的不同 codec，见 [合同审查](../private/qualification/h02_contract_review.md)。

A 与 B/C 不是独立测量：丢链会同时导致多项失败，不能把失败 check 数量当严重度分数，也不能把11项检查当11份独立模型样本。B 的 structured/collect 路径、C 的 missing-traceback 条件和 D 的 native/ordinary 回归有不同诊断价值。C03 蕴含 D03 的主要断言，但保留 D03 能区分“原问题未修复”和“修复引入崩溃”。D02 是复合检查，应展开失败子测试，而非增加一组重复的 hidden tests。

轨迹中的阅读、定位、编辑、复测属于过程诊断；成功补丁和跨边界行为属于直接观测。它们支持能力推断，但不证明 Agent 的私有推理、独立发现程度或不存在训练记忆。
