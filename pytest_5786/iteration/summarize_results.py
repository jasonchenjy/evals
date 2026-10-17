"""Explain existing scores without changing them or inferring private reasoning."""
import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

CONTROL_NOTES = {
    'noop': ('未作修复', '原缺陷保留', '空补丁；用于区分原有信息丢失与新增回归。'),
    'historical': ('历史链传输修复遗漏 None crash', '新增回归/边界处理缺失', 'crash 编解码假设总有对象；C03/D03 的 AttributeError 是候选行为错误。'),
    'complete': ('完整参考修复', None, '链结构与 None crash 均处理；正对照。'),
    'alternative': ('采用不同 wire layout 的修复', None, 'causes/part/link 递归 codec；H02 冗余副本变异失败仅作诊断。'),
    'last_only': ('只保留末端异常', '根因路径修复不完整', '序列化 chain[-1:]，仍然丢失原因。'),
    'testreport_only': ('仅在 TestReport 编码链', '遗漏报告类型', 'CollectReport 退回旧的末端表示，失败跨 B/C，不应当作两个独立根因。'),
    'text_only': ('把 longrepr 转为字符串', '结构化消费者不兼容', '可保留显示，B03 可通过；B02 的 crash/traceback 消费失败。'),
    'first_real': ('完整真实 Agent 补丁', None, '共享 BaseReport codec 保留链、None crash、sections 和非链表示；只是归档补丁重评。'),
    'chain_assumed': ('把所有 structured longrepr 都当 chain', '合法原生表示回归', 'complete 的 isinstance 判断改为 hasattr(reprtraceback)；遗漏非 chain ReprExceptionInfo 分支。'),
    'links_omitted': ('保存异常节点但漏掉关系描述', '因果连接信息丢失', 'complete 中序列化 description 被遗漏为 None；没有改异常消息、次序或其他字段。'),
    'sections_omitted': ('构造恢复对象后漏掉附加 sections', '附加报告信息丢失', 'complete 中 addsection 循环为空；保留外层 captured sections 与其他行为。'),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, default=HERE / 'evidence')
    args = parser.parse_args()
    summary = json.loads((args.evidence / 'summary.json').read_text())
    reference = {v['control']:v for v in json.loads((REPO / 'harbor/evidence/qualification-comparison.json').read_text())['controls']}
    expected = {'complete', 'alternative', 'first_real'}
    records = []
    comparisons = 0
    for entry in summary['controls']:
        name = entry['control']
        result = json.loads((args.evidence / name / 'result.json').read_text())
        assert result['infrastructure_status'] == 'ok' and result['submission_status'] == 'accepted'
        assert len(result['tests']) == 13
        assert not any(t['status'] in ('timeout', 'execution_error', 'skipped') for t in result['tests'])
        assert result['overall_resolved'] == (name in expected)
        if name in reference:
            assert entry['checks'] == reference[name]['checks']
            assert entry['dimensions'] == reference[name]['dimensions']
            assert entry['overall'] == reference[name]['overall']
            comparisons += len(entry['checks'])
        failed = []
        for check in result['tests']:
            if check['status'] != 'passed':
                failed.append(dict(check=check['id'], mandatory=check['mandatory'], status=check['status'],
                    observable_failures=check.get('observation', {}).get('failures', []),
                    execution=check['execution'], evidence=f'evidence/{name}/result.json'))
        description, category, change = CONTROL_NOTES[name]
        records.append(dict(entry, description=description, source_change=change,
            expected_affected_dimensions={'chain_assumed':['D'], 'links_omitted':['A'],
                'sections_omitted':['B']}.get(name),
            failure_mode_category=category, failed_checks=failed,
            failed_mandatory_checks=[x['check'] for x in failed if x['mandatory']],
            classification_correct=True, reasoning_claim='No inference about private Agent reasoning.'))
    assert len(records) == 11 and comparisons == 91
    original = json.loads((REPO / 'harbor/evidence/pytest5786-stage3-20261017T075426Z/codex/verifier/grader/result.json').read_text())
    again = next(x for x in records if x['control'] == 'first_real')
    assert again['checks'] == {x['id']:x['status'] for x in original['tests']}
    assert again['patch_sha256'] == original['patch_sha256']
    receipts = [json.loads(p.read_text()) for p in (args.evidence / 'workers').glob('worker-*/worker-receipt.json')]
    assert len(receipts) == 165 and all(x['removed'] and x['all_candidate_processes_stopped'] for x in receipts)
    manifest = json.loads((args.evidence / 'evidence-manifest.json').read_text())
    for e in manifest:
        raw = (args.evidence / e['path']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == e['sha256'] and len(raw) == e['bytes']
    output = dict(status='EVAL_READY_FOR_COMPARISON', eval_version='0.1.0', scoring_changed=False,
        model_calls=0, new_agent_trials=0, valid_historical_agent_samples=1,
        controls=records, total_controls=11, total_check_results=143,
        original_control_statuses_matched=91, archived_agent_check_statuses_matched=13,
        new_diagnostic_controls_rejected=3, infrastructure_errors=0,
        worker_receipts_verified=165, curated_files_verified=len(manifest),
        false_positive_found=False, false_negative_found=False,
        limitation='Finite purposive control set; not an error-rate estimate or proof of exhaustive coverage/Agent-level discrimination.')
    (HERE / 'diagnostic_results.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    lines = ['# Diagnostic control results', '',
        'A/B/C/D 是四维布尔结果，1=通过。所有11个补丁均在精确基线上应用成功，infrastructure_status=ok。', '',
        '| Control | A/B/C/D | Overall | 失败 mandatory | 失败 diagnostics |',
        '|---|---|---|---|---|']
    for row in records:
        dimensions = '/'.join(str(int(x)) for x in row['dimensions'].values())
        mandatory = ', '.join(row['failed_mandatory_checks']) or '无'
        diagnostic = ', '.join(x['check'] for x in row['failed_checks'] if not x['mandatory']) or '无'
        lines.append(f"| {row['control']} | {dimensions} | {row['overall']} | {mandatory} | {diagnostic} |")
    lines += ['', '原七控制91项状态、归档 Agent 的13项状态均与历史一致。总计143项检查；3项新诊断控制均拒绝。',
        '历史参考的 C03/D03 以及 text_only 的部分 error 是已完成检查捕获的候选异常，不是基础设施失败。',
        '165个 worker 收据确认停止并删除；188个精选文件哈希校验通过。', '',
        '## 新诊断的解释', '',
        '- **chain_assumed（预期 D）**：混淆结构化表示与链表示，D02 的 `test_reprentries_serialization_196` 报 ReprExceptionInfo 无 chain 属性；A/B/C 均通过。说明原生表示回归已有保护，无需重复加测。',
        '- **links_omitted（预期 A，级联 B/C）**：节点消息仍在，但 cause/context 关系文字消失。A01/A02 及 B/C 相关检查拒绝，D 全通过。信息完整性不能只查消息存在。',
        '- **sections_omitted（预期 B，兼有 D 回归）**：恢复 exception 对象时遗漏 addsection。B01/B02 直接检查附加内容失败，D02 的既有附加信息测试也失败；B03 和 A/C 仍通过。',
        '', '三者均是在 Complete Oracle 上引入一个明确的工程遗漏，再生成相对固定 base 的完整补丁；没有修改原 Oracle、按测试 ID 分支或匹配固定消息。',
        '生成步骤见 [build_diagnostics.py](build_diagnostics.py)；所有实际失败文本、check 状态与源码说明见 [diagnostic_results.json](diagnostic_results.json)。',
        '此有限样本内未发现 false positive；不能据此估计任意错误补丁的漏检概率。']
    (HERE / 'diagnostic_results.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps({k:output[k] for k in ['status','total_controls','total_check_results','original_control_statuses_matched','archived_agent_check_statuses_matched','infrastructure_errors']}))


if __name__ == '__main__':
    main()
