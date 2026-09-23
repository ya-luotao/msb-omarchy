#!/usr/bin/env python3
"""Project-owned runtime and desktop lifecycle. Python standard library only."""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
RELEASE = json.loads((ROOT / "config/release.json").read_text())
PROFILES = {"light": "1600x900", "standard": "1920x1080"}


class Error(Exception):
    pass


def say(message):
    print(message, file=sys.stderr, flush=True)


def execute(args, *, env=None, capture=False, timeout=None, check=True):
    try:
        result = subprocess.run(
            [str(arg) for arg in args], env=env, text=True,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise Error(f"{Path(args[0]).name} timed out after {timeout}s") from exc
    except OSError as exc:
        raise Error(str(exc)) from exc
    if check and result.returncode:
        detail = (result.stderr or result.stdout or "").strip()
        raise Error(detail or f"{Path(args[0]).name} exited {result.returncode}")
    return result


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as out:
        json.dump(value, out, indent=2)
        out.write("\n")
        temporary = Path(out.name)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextlib.contextmanager
def lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Error("Another operation is in progress; retry when it finishes.") from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def checksum(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download(spec, path):
    if path.is_file() and checksum(path) == spec["sha256"]:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".part")
    try:
        execute(["curl", "--fail", "--location", "--silent", "--show-error",
                 "--retry", "2", "--connect-timeout", "20", "--max-time", "600",
                 "--output", temporary, spec["url"]])
        if checksum(temporary) != spec["sha256"]:
            raise Error(f"Checksum mismatch for {path.name}; nothing was installed.")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def check_release(candidate, image_id, reports):
    if image_id != candidate.get("image_id"):
        raise Error("The local image changed after build/load. Rebuild and repeat Mac smoke.")
    profiles = {report.get("profile") for report in reports
                if report.get("passed") is True and report.get("image_id") == image_id}
    if not {"light", "standard"} <= profiles:
        raise Error("Run bin/smoke for both light and standard on this exact image before publishing.")


class Desktop:
    def __init__(self):
        self.runtime_dir = ROOT / ".runtime" / RELEASE["runtime"]["version"]
        self.state_dir = Path(os.environ.get("MSB_HOME", ROOT / ".runtime/home")).expanduser().resolve()
        self.binary = Path(os.environ.get("MSB", self.runtime_dir / "msb")).expanduser().resolve()
        self.firmware = Path(os.environ.get("MSB_LIBKRUNFW_PATH", self.runtime_dir / "libkrunfw.5.dylib")).expanduser().resolve()
        self.env = dict(os.environ, MSB_HOME=str(self.state_dir), MSB_PATH=str(self.binary),
                        MSB_CONFIG_PATH=str(self.state_dir / "config.json"),
                        MSB_LIBKRUNFW_PATH=str(self.firmware), MSB_BACKEND="local")

    def check_runtime(self):
        if not self.binary.is_file():
            raise Error("Graphics runtime is not installed. Run bin/setup first.")
        result = execute([self.binary, "display", "--help"], env=self.env,
                         capture=True, check=False, timeout=10)
        if result.returncode:
            raise Error(f"The selected runtime cannot open a desktop: {self.binary}\n"
                        f"{(result.stderr or result.stdout).strip()}\n"
                        "Use bin/setup for the pinned graphics build. Missing Homebrew libraries: "
                        "brew install slp/krun/virglrenderer molten-vk libepoxy")
        if not self.firmware.is_file():
            raise Error("Matching firmware is missing. Run bin/setup first.")

    def msb(self, *args, capture=False, timeout=30, check=True, env=None):
        return execute([self.binary, *args], env=env or self.env, capture=capture,
                       timeout=timeout, check=check)

    def metadata_path(self, name):
        identifier = hashlib.sha256(name.encode()).hexdigest()[:24]
        return self.state_dir / "omarchy" / f"{identifier}.json"

    def find(self, name):
        # A list failure is never interpreted as a missing VM.
        data = json.loads(self.msb("list", "--format", "json", capture=True).stdout)
        return next((item for item in data if item["name"] == name), None)

    def image(self):
        if os.environ.get("TAG"):
            return os.environ["TAG"]
        built = self.state_dir / "omarchy/image.json"
        return json.loads(built.read_text())["tag"] if built.exists() else RELEASE["image"]

    def setup(self):
        if platform.system() != "Darwin" or platform.machine() != "arm64":
            raise Error("The desktop runtime requires an Apple Silicon Mac.")
        with lock(ROOT / ".runtime/setup.lock"):
            downloads = ROOT / ".runtime/downloads"
            archive = downloads / "msb-gpu-m3.tar.gz"
            firmware = downloads / "libkrunfw.5.dylib"
            say("Downloading and checking the pinned graphics runtime…")
            download(RELEASE["runtime"], archive)
            download(RELEASE["firmware"], firmware)
            self.runtime_dir.mkdir(parents=True, exist_ok=True)
            # Extract only expected regular files, never paths or links.
            with tarfile.open(archive) as bundle:
                for name in ("msb", "msb-entitlements.plist"):
                    member = bundle.getmember(name)
                    if not member.isfile():
                        raise Error(f"Unexpected archive entry: {name}")
                    temporary = self.runtime_dir / (name + ".new")
                    with bundle.extractfile(member) as source, temporary.open("wb") as out:
                        shutil.copyfileobj(source, out)
                    temporary.chmod(0o755 if name == "msb" else 0o644)
                    if name == "msb":
                        execute(["codesign", "--verify", temporary], capture=True)
                    os.replace(temporary, self.runtime_dir / name)
            temporary = self.runtime_dir / "libkrunfw.5.dylib.new"
            shutil.copyfile(firmware, temporary)
            os.replace(temporary, self.runtime_dir / "libkrunfw.5.dylib")
        self.check_runtime()
        say(f"Runtime ready. Desktop state: {self.state_dir}\nOpen the desktop with bin/run.")

    def ready(self, name, timeout):
        # No background child retaining exec pipes, no display.sock attachment.
        probe = ('u=$(id -u omarchy); exec runuser -u omarchy -- env '
                 'XDG_RUNTIME_DIR=/run/user/$u DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$u/bus '
                 'OMARCHY_PATH=/usr/share/omarchy timeout 3 omarchy-shell shell ping')
        deadline = time.monotonic() + timeout
        last_error = "No response from the desktop shell"
        while time.monotonic() < deadline:
            try:
                result = self.msb("exec", "--timeout", "4s", name, "--", "sh", "-c", probe,
                                  capture=True, check=False, timeout=5)
                if result.returncode == 0 and result.stdout.strip().lower() == "ok":
                    return
                last_error = (result.stderr or result.stdout).strip() or last_error
            except Error as exc:
                last_error = str(exc)
            time.sleep(0.5)
        raise Error(f"Desktop was not ready after {timeout}s: {last_error}\n"
                    f"The VM is retained. Inspect it with bin/msb logs {name} or bin/doctor.")

    def run(self, args):
        self.check_runtime()
        metadata = self.metadata_path(args.name)
        with lock(metadata.with_suffix(".lock")):
            existing = self.find(args.name)
            if existing:
                if not metadata.exists():
                    raise Error(f"{args.name!r} already exists but was created outside bin/run. "
                                f"Use bin/msb start/display {args.name} to manage it.")
                settings = json.loads(metadata.read_text())
                if args.profile and args.profile != settings["profile"]:
                    raise Error("This VM keeps its original display profile. Use a new --name "
                                "for a different profile, or explicitly reset this VM.")
                launch_env = dict(self.env, MSB_GPU="1", MSB_SND="1",
                                  MSB_GPU_DISPLAY=settings["display"])
                status = existing["status"].lower()
                if status in ("stopped", "crashed"):
                    # "crashed" is what msb records when the VM process died
                    # without a stop, e.g. across a Mac restart; the disk is
                    # kept and msb starts it the same way as a stopped VM.
                    say(f"Starting {args.name} with its saved desktop"
                        f"{' after an unclean shutdown' if status == 'crashed' else ''}…")
                    self.msb("start", args.name, env=launch_env, timeout=120)
                elif status == "running":
                    say(f"Opening the running desktop {args.name}…")
                else:
                    raise Error(f"{args.name} is {status}; inspect it with bin/msb inspect {args.name}.")
            else:
                profile = args.profile or os.environ.get("PROFILE", "light")
                if profile not in PROFILES:
                    raise Error(f"Unknown profile {profile!r}. Choose light or standard.")
                display = os.environ.get("MSB_GPU_DISPLAY", PROFILES[profile])
                if not re.fullmatch(r"[1-9][0-9]{2,3}x[1-9][0-9]{2,3}", display):
                    raise Error("MSB_GPU_DISPLAY must be WIDTHxHEIGHT, for example 1600x900.")
                shared = Path(os.environ.get("SHARED_DIR", ROOT / "Shared")).expanduser().resolve()
                if ":" in str(shared):
                    raise Error("SHARED_DIR cannot contain ':' (the runtime's mount separator).")
                shared.mkdir(parents=True, exist_ok=True)
                settings = {"name": args.name, "profile": profile, "display": display,
                            "image": self.image(), "shared": str(shared)}
                launch_env = dict(self.env, MSB_GPU="1", MSB_SND="1", MSB_GPU_DISPLAY=display)
                say(f"Creating {args.name} · {profile} · {display}…")
                # Record intent first so a failed boot can be resumed.
                write_json(metadata, settings)
                self.msb("run", "--name", args.name, "--init", "auto", "-d",
                         "--cpus", os.environ.get("CPUS", "4"),
                         "--memory", os.environ.get("MEMORY", "4G"),
                         "--root-disk", os.environ.get("ROOT_DISK", "16G"),
                         "-p", f"127.0.0.1:{os.environ.get('VNC_PORT', '5901')}:5900",
                         "-v", f"{shared}:/home/omarchy/Shared:uid=1000,gid=1000",
                         settings["image"], "--", "sleep", "infinity",
                         env=launch_env, timeout=900)
            say("Waiting for the desktop…")
            self.ready(args.name, args.timeout)
        say(f"Desktop ready. Shared files: {settings['shared']}")
        if not args.no_display:
            # Closing the window only ends the viewer; the VM remains running.
            os.execve(self.binary, [str(self.binary), "display", args.name], self.env)

    def reset(self, args):
        if not args.yes:
            raise Error(f"Reset deletes {args.name}'s VM disk and settings. "
                        "The host Shared directory is kept. Repeat with --yes to reset.")
        self.check_runtime()
        metadata = self.metadata_path(args.name)
        with lock(metadata.with_suffix(".lock")):
            existing = self.find(args.name)
            if existing:
                if not metadata.exists():
                    raise Error("Refusing to reset a VM not created by bin/run.")
                if existing["status"].lower() == "running":
                    self.msb("stop", args.name, timeout=60)
                self.msb("remove", args.name, timeout=60)
            metadata.unlink(missing_ok=True)
        say(f"Reset {args.name}. Run bin/run to create a fresh desktop.")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "msb":
        desktop = Desktop()
        desktop.check_runtime()
        os.execve(desktop.binary, [str(desktop.binary), *argv[1:]], desktop.env)
    parser = argparse.ArgumentParser(description="Omarchy desktop on Apple Silicon")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("setup", help="Install the pinned graphics runtime into this project")
    commands.add_parser("doctor", help="Check runtime, firmware and host support")
    run = commands.add_parser("run", help="Create, resume or open a desktop")
    run.add_argument("--name", default=os.environ.get("NAME", "omarchy"))
    run.add_argument("--profile", choices=PROFILES)
    run.add_argument("--timeout", type=float, default=90, help="Desktop readiness timeout in seconds")
    run.add_argument("--no-display", "-d", "--detach", action="store_true")
    run.add_argument("--display", action="store_true", help="Open a window, including with -d")
    for command in ("stop", "reset"):
        sub = commands.add_parser(command)
        sub.add_argument("--name", default=os.environ.get("NAME", "omarchy"))
        if command == "reset":
            sub.add_argument("--yes", action="store_true")
    args = parser.parse_args(argv)
    desktop = Desktop()
    if args.command == "setup":
        desktop.setup()
    elif args.command == "doctor":
        desktop.check_runtime()
        say(f"Runtime: {desktop.binary}\nFirmware: {desktop.firmware}\nState: {desktop.state_dir}")
        desktop.msb("doctor", timeout=60)
    elif args.command == "run":
        if args.display:
            args.no_display = False
        if args.timeout <= 0:
            raise Error("--timeout must be positive")
        desktop.run(args)
    elif args.command == "stop":
        desktop.check_runtime()
        with lock(desktop.metadata_path(args.name).with_suffix(".lock")):
            desktop.msb("stop", args.name, timeout=60)
    elif args.command == "reset":
        desktop.reset(args)


if __name__ == "__main__":
    try:
        main()
    except (Error, ValueError, KeyError, OSError) as error:
        say(f"omarchy: {error}")
        sys.exit(1)
    except KeyboardInterrupt:
        say("Cancelled. Existing desktop data is retained.")
        sys.exit(130)
