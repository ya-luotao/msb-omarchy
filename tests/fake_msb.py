#!/usr/bin/env python3
"""Small process fixture for testing launcher failures and retained VM state."""
import json
import os
from pathlib import Path
import sys

args = sys.argv[1:]
state_dir = Path(os.environ["MSB_HOME"])
state_dir.mkdir(parents=True, exist_ok=True)
state_path = state_dir / "fake-state.json"
state = json.loads(state_path.read_text()) if state_path.exists() else {}
with (state_dir / "calls.jsonl").open("a") as out:
    out.write(json.dumps({"args": args, "display": os.environ.get("MSB_GPU_DISPLAY"),
                          "config": os.environ["MSB_CONFIG_PATH"]}) + "\n")
command = args[0]
if command == "--version":
    print(os.environ.get("FAKE_VERSION", "msb 0.0.1"))
elif command == "display":
    print("display help")
elif command == "list":
    if os.environ.get("FAKE_LIST_ERROR"):
        sys.exit("database unavailable")
    print(json.dumps(list(state.values())))
elif command == "run":
    name = args[args.index("--name") + 1]
    if name in state:
        sys.exit("already exists")
    state[name] = {"name": name, "status": "Running", "image": args[args.index("--") - 1]}
    (state_dir / "guest-document").write_text("user work")
elif command in ("start", "stop"):
    if command == "stop" and state[args[1]]["status"] == "Paused":
        sys.exit("cannot stop a paused sandbox")
    state[args[1]]["status"] = "Running" if command == "start" else "Stopped"
elif command in ("pause", "resume"):
    state[args[1]]["status"] = "Paused" if command == "pause" else "Running"
elif command == "remove":
    del state[args[1]]
    (state_dir / "guest-document").unlink()
elif command == "exec":
    if os.environ.get("FAKE_NOT_READY"):
        sys.exit("shell not ready")
    print("ok")
else:
    sys.exit("unsupported fixture command")
state_path.write_text(json.dumps(state))
