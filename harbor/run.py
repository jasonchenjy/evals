"""Run real Harbor trials; no local pytest substitutes."""
import argparse, asyncio, json, os
from pathlib import Path
from harbor.models.trial.config import TrialConfig, TaskConfig, AgentConfig, EnvironmentConfig
from harbor.trial.trial import Trial

ROOT = Path(__file__).resolve().parent
async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=["spike", "pytest_5786", "codex-spike"])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    task = ROOT / ("spike" if args.kind == "spike" else "generated/pytest_5786")
    if args.kind == "codex-spike":
        task = ROOT / "generated/codex-spike"
        controls = [("codex", {}, None)]
    elif args.kind == "spike":
        controls = [("noop", {}, False), ("correct", {"replacement":"def divide(a, b):\n    return a / b\n"}, True), ("incomplete", {"replacement":"def divide(a, b):\n    return abs(a / b)\n"}, False)]
    else:
        expected = json.loads((ROOT.parent / "pytest_5786/private/qualification/summary.json").read_text())
        controls = [(x["control"], {"patch":str(ROOT.parent / "pytest_5786/private/oracle" / (x["control"]+".patch"))}, x["expected_overall"]) for x in expected["controls"]]
    summary = []
    for name, kwargs, expected in controls:
        agent_config = AgentConfig(import_path="harbor_controls:ControlAgent", kwargs=kwargs)
        if args.kind == "codex-spike":
            agent_config = AgentConfig(name="codex", model_name="openai/gpt-6.1-sol", kwargs={"version":"0.162.1"}, env={"CODEX_AUTH_JSON_PATH":"/Users/junyu/.codex/auth.json"})
        cfg = TrialConfig(task=TaskConfig(path=task), trial_name=name, trials_dir=args.output,
            agent=agent_config,
            environment=EnvironmentConfig(import_path="harbor_colima:ColimaEnvironment"))
        trial = await Trial.create(cfg)
        result = await trial.run()
        data = result.model_dump(mode="json")
        reward = (data.get("verifier_result") or {}).get("rewards")
        entry = dict(control=name, expected=expected, rewards=reward, exception=data.get("exception_info"), expectation_met=bool(reward is not None and (expected is None or reward.get("reward") == float(expected)) and not data.get("exception_info")))
        summary.append(entry)
        (args.output / "summary.json").write_text(json.dumps(summary, indent=2)+"\n")
        print(json.dumps(entry), flush=True)
    return all(x["expectation_met"] for x in summary)
if __name__ == "__main__":
    # Avoid shadowing the installed harbor package with this integration folder.
    import sys
    sys.path.insert(0, str(ROOT))
    import importlib.util
    spec = importlib.util.spec_from_file_location("harbor_controls", ROOT / "controls.py")
    mod = importlib.util.module_from_spec(spec); sys.modules["harbor_controls"] = mod; spec.loader.exec_module(mod)
    spec = importlib.util.spec_from_file_location("harbor_colima", ROOT / "colima.py")
    mod = importlib.util.module_from_spec(spec); sys.modules["harbor_colima"] = mod; spec.loader.exec_module(mod)
    raise SystemExit(0 if asyncio.run(main()) else 1)
