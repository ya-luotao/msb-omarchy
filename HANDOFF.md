# Handoff — 2026-08-30

Session state for whoever picks this up next. Delete before making the repo public.

## 1. Status

| Item | State | Where |
|---|---|---|
| M0 — DRM node in the guest | done 2026-08-30 | `docs/assessment.md` "M0 results", `docs/plan.md` |
| M1 — Omarchy over VNC | done 2026-08-30 — desktop visible from the host over VNC | `docs/assessment.md` "M1 results", `docs/images/` |
| M2 — native macOS window | done 2026-08-30 (`msb display`, keyboard + pointer); `msb run --display` and upstream PRs remain | `docs/assessment.md` "M2 results" |
| Local msb | fixed: `~/.microsandbox/bin/msb` is the `gpu-m0` build (0.6.16); old binary kept as `msb-0.6.14.bak` | §3 |
| Running sandbox | `omarchy` (image `msb-omarchy:dev`, VNC on 127.0.0.1:5901) — `msb stop omarchy` when not needed | `bin/run` |

## 2. Where things live

- microsandbox branch `gpu-m0`, worktree `~/.herdr/worktrees/microsandbox/gpu-m0` (commit 77dea1f9): `MSB_GPU=1|venus`, `MSB_GPU_DISPLAY=WxH`. The workspace `[patch.crates-io]` points at `~/.cache/msb-omarchy/msb_krun-0.1.32-patched` (a local git repo holding the published crate plus `ConsoleBuilder::gpu_display`). The upstream fork is cloned at `~/.cache/msb-omarchy/libkrun` (zerocore-ai/libkrun, HEAD dc9f5f1 = 0.1.32, crate in `src/krun`) for the eventual PR.
- Build: `brew install slp/krun/virglrenderer` (done), then in the worktree `LIBRARY_PATH=/opt/homebrew/lib cargo build --profile ci --no-default-features --features net,ssh -p microsandbox-cli` and `codesign --entitlements msb-entitlements.plist --force -s - target/ci/msb`. `build/agentd` is the v0.6.16 release `agentd-aarch64` (agentd unchanged since the release).
- Guest sources: `~/.cache/msb-omarchy/omarchy` (omacom/omarchy at 13f18b2, the commit omarchy-pkgs 4.0.1 pins), `~/.cache/msb-omarchy/omarchy-pkgs` (sparse: `pkgbuilds/omarchy`, `pkgbuilds/omarchy-settings`), `~/.cache/msb-omarchy/omarchy-arm-utm` (reference for the ALARM package set and software-rendering settings).
- Kept sandbox `gpu-m0-modetest` (python:3.12-slim + `libdrm-tests`): `MSB_GPU=1 msb run --name gpu-m0-modetest public.ecr.aws/docker/library/python:3.12-slim -- modetest -M virtio_gpu`.

## 3. Next steps

M2 code: microsandbox `gpu-m0` commit 5bd45782 (`crates/runtime/lib/gpu_display/{mod,protocol,input,dump}.rs`, `crates/cli/lib/commands/display.rs`, `ipc.rs` display socket), plus vendored patches `msb_krun_devices` (37e5696), `msb_krun` (986266f), `msb_krun_utils` (efad426) under `~/.cache/msb-omarchy/`. Run: `MSB=~/.herdr/worktrees/microsandbox/gpu-m0/build/msb bin/run -d` then `~/.herdr/worktrees/microsandbox/gpu-m0/build/msb display omarchy`. A headless client for tests lives in the session scratchpad only; recreate from `bin/vnc-shot` + the protocol module if needed.

1. `msb run --display`: spawn `msb display <name>` after the sandbox reports ready (the viewer must be a separate process; see assessment).
2. Viewer polish: HiDPI (window is 1920x1080 physical = 960x540 points on Retina), cursor confinement/relative mode, clipboard.
3. Upstream: PRs to zerocore-ai/libkrun from the three patch repos (each has a baseline commit + one change commit, `git diff HEAD~1` is the PR); then a microsandbox PR for `gpu-m0` once the crates are published.
4. Later items in `docs/plan.md`.

## 3a. M1 operating notes

- `bin/run -d` recreates the sandbox (`--replace`), so guest-side experiments are lost; bake changes into `guest/overlay` and rerun `bin/build-rootfs` (Docker layers are cached, save+load ≈ 5 min).
- Environment changes need a sandbox restart (`msb stop omarchy && MSB_GPU=1 msb start omarchy`), not `systemctl restart sddm`.
- Never feed `msb exec` from stdin; it wedged agentd's exec path once and every later exec hung until restart. Heredocs inside `bash -c` and `msb cp` are fine.
- `vncdotool` hangs on wayvnc; use `bin/vnc-shot` (Pillow) or Screen Sharing.

## 4. Environment notes

- Docker (OrbStack) build needs `DisableSandbox` in pacman.conf (pacman 7 Landlock cannot be applied in a container); the Dockerfile handles it.
- Arch Linux ARM has everything except `ttf-jetbrains-mono-nerd-basic` (use `ttf-jetbrains-mono-nerd`), `xdg-terminal-exec` (wrapper in `guest/overlay/usr/local/bin`), `yaru-icon-theme` (skipped).
- Disk got down to 2 GiB during the first `docker save`; APFS reclaimed purgeable space by itself later. Big local consumers: `~/space/heymoney/microsandbox/target` (13 GB cargo cache), `~/.microsandbox/cache` (now ≈7 GB with `msb-omarchy:dev`), the OrbStack data volume. `guest/build/image.tar` (4 GB) is deleted after each load.
- The old "database schema is newer than this msb binary" error was a branch-built DB (`m20260824` marker without `m20260818`); fixed by deleting the marker row (backup `~/.microsandbox/db/msb.db.bak-*`). Don't uninstall the brew `virglrenderer`: the installed msb links it dynamically.
