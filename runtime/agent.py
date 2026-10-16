"""Fresh Codex CLI command/config contract. No developer-thread reuse."""
import json
from pathlib import Path

from core import InfrastructureError, bounded, clean_env, save, sha

DISABLED = ['apps','plugins','remote_plugin','browser_use','browser_use_external',
            'computer_use','memories','hooks','multi_agent','shell_snapshot','workspace_dependencies']


def configuration(sandbox, workspace, scratch, controller_home=None):
    env = clean_env(workspace, scratch, sandbox.python)
    settings = ['default_permissions="trial"', 'permissions='+sandbox.permissions(workspace, scratch),
                'web_search="disabled"', 'project_doc_max_bytes=0', 'developer_instructions=""',
                'mcp_servers={}', 'shell_environment_policy.inherit="none"',
                'shell_environment_policy.ignore_default_excludes=false',
                'shell_environment_policy.set={'+', '.join(json.dumps(k)+'='+json.dumps(v) for k,v in env.items())+'}']
    if controller_home is not None:
        system = Path(controller_home)/'.codex/skills/.system'
        settings.append('skills.config=['+', '.join(
            '{path='+json.dumps(str(system/name/'SKILL.md'))+',enabled=false}'
            for name in ['imagegen','openai-docs','skill-creator','skill-installer'])+']')
    argv = [sandbox.codex, '--no-daemon', '-a', 'never']
    for name in DISABLED:
        argv += ['--disable', name]
    argv += ['--enable', 'skip_host_skill_discovery']
    for setting in settings:
        argv += ['-c', setting]
    return argv


def client_env(controller_home):
    """Authentication may be provisioned later using supported Codex login; never copy keys."""
    home = Path(controller_home)
    (home/'.codex').mkdir(parents=True, exist_ok=True)
    (home/'tmp').mkdir(exist_ok=True)
    return {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'HOME': str(home),
            'CODEX_HOME': str(home/'.codex'), 'TMPDIR': str(home/'tmp'),
            'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1'}


def build_command(sandbox, workspace, scratch, model, final_path, controller_home=None):
    if not model or not model.strip():
        raise ValueError('A model must be selected explicitly')
    return configuration(sandbox, workspace, scratch, controller_home) + [
        'exec', '--ignore-user-config', '--ignore-rules', '--ephemeral', '--json',
        '-C', str(workspace), '--model', model, '--output-last-message', str(final_path), '-']


def prompt(workspace, python):
    return (Path(workspace)/'TASK.md').read_text() + (
        '\n\nRuntime instructions: Work only in this exported repository. Use '+str(python)+
        ' -m pytest with PYTHONPATH pointing to its src directory. Plugin autoload is disabled; '
        'load xdist.plugin explicitly when using -n. Public reproducer tests intentionally raise '
        'exceptions and may exit nonzero after a correct fix. Leave your source edits in the '
        'workspace. The controller collects allowed source changes; no Git commit is required.\n')


def inspect(sandbox, workspace, folder, controller_home=None):
    """No model turn. Preserve actual prompt/debug output; fail closed without tool evidence."""
    folder = Path(folder)
    folder.mkdir(parents=True)
    home = Path(controller_home).absolute() if controller_home else folder/'client-home'
    if home.resolve() == Path.home().resolve():
        raise InfrastructureError('Use a dedicated runtime client home, never the developer home')
    credentials = (home/'.codex').resolve()
    readable_roots = [Path(workspace), folder/'candidate-scratch'] + [Path(p) for p in sandbox.readable]
    for root in readable_roots:
        try:
            credentials.relative_to(root.resolve())
        except ValueError:
            continue
        raise InfrastructureError('Controller authentication home overlaps candidate-readable paths')
    env = client_env(home)
    version = bounded([sandbox.codex, '--version'], folder, env, 10, folder/'version')
    auth = bounded([sandbox.codex, 'login', 'status'], folder, env, 10, folder/'auth-status')
    command = configuration(sandbox, workspace, folder/'candidate-scratch', home) + [
        '-C', str(workspace), 'debug', 'prompt-input', prompt(workspace, sandbox.python)]
    observed = bounded(command, folder, env, 20, folder/'prompt-input')
    result = {'model_calls': 0, 'harness': 'codex',
              'version': Path(version['stdout']).read_text().strip(), 'executable_sha256': sha(sandbox.codex),
              'fresh_home': str(home), 'auth_status_exit_code': auth['returncode'],
              'prompt_inspection': observed, 'effective_tools_verified': False,
              'prompt_verified': False, 'blockers': []}
    if observed['returncode']==0:
        try:
            payload = json.loads(Path(observed['stdout']).read_text())
            result['prompt_payload_type'] = type(payload).__name__
            # No inference of tool enforcement from prompt prose. Installed debug command
            # exposes prompt items but may not provide actual tool definitions/capabilities.
            text = json.dumps(payload)
            prohibited = ['complete.patch','alternative.patch','private/tests/behavior.py',
                          'oracle_recheck_20261016','h02_contract_review.md']
            kinds = [kind for item in payload for kind in item.get('internal_chat_message_metadata_passthrough', {}).get('content_item_kinds', [])]
            result['prompt_item_kinds'] = kinds
            allowed = {'permissions.instructions','collaboration_mode.instructions',
                       'multi_agent.role_instructions','multi_agent.mode_instructions',
                       'environments.environment_context','user.text'}
            result['unexpected_prompt_kinds'] = sorted(set(kinds)-allowed)
            result['prompt_verified'] = (all(x not in text for x in prohibited)
                and not result['unexpected_prompt_kinds']
                and payload[-1]['content'][0]['text'] == prompt(workspace, sandbox.python))
        except ValueError:
            result['blockers'].append('Prompt debug output was not valid JSON')
    else:
        result['blockers'].append('Fresh prompt inspection did not complete successfully')
    result['blockers'].append('Effective Codex tool definitions and per-tool filesystem enforcement are not exposed by this debug probe; live gate remains closed')
    if not result['prompt_verified']:
        result['blockers'].append('Fresh effective prompt has not been verified')
    if auth['returncode']!=0:
        result['blockers'].append('Dedicated controller Codex home is not authenticated; use supported login, never copy credential files')
    save(folder/'inspection.json', result)
    return result


def execute(sandbox, workspace, folder, model, timeout, inspection):
    if not inspection['prompt_verified'] or not inspection['effective_tools_verified']:
        raise InfrastructureError('Agent context/tool inventory gate is not satisfied')
    if inspection['auth_status_exit_code'] != 0:
        raise InfrastructureError('Dedicated participant controller is not authenticated')
    # Current native runner does not establish detached-child/RAM/PID/disk containment.
    if not all(sandbox.features[k] for k in ['detached_descendant_containment','aggregate_memory','per_trial_process_count','aggregate_disk_quota']):
        raise InfrastructureError('Untrusted agent resource/descendant containment gate is not satisfied')
    folder = Path(folder)
    folder.mkdir(parents=True)
    final = folder/'final.txt'
    command = build_command(sandbox, workspace, folder/'scratch', model, final, inspection['fresh_home'])
    return bounded(command, workspace, client_env(inspection['fresh_home']), timeout,
                   folder/'events', prompt(workspace, sandbox.python))
