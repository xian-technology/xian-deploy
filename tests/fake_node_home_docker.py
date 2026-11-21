"""Mock Docker's mount boundary while running the actual home validation script."""

import sys
import types

args = sys.argv[1:]
if args[0] == "run":
    assert args[:7] == [
        "run", "--rm", "--network", "none", "--entrypoint", "python", "--mount"
    ]
    bind, source, target, mode = args[7].split(",")
    assert bind == "type=bind" and mode == "readonly"
    assert args[8].startswith("registry.example/xian-node@sha256:")
    assert args[9] == "-Ic" and args[11] == target.removeprefix("target=")

    policy = types.ModuleType("xian.state_sync_policy")
    policy.validate_comet_state_sync_disabled = lambda config: None
    sys.modules[policy.__name__] = policy
    sys.argv = ["-c", source.removeprefix("source="), *args[12:]]
    exec(compile(args[10], "<node-home-check>", "exec"), {"__name__": "__main__"})
    raise SystemExit
