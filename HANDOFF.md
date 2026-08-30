# Handoff — 2026-08-30

Session state for whoever picks this up next. Delete before making the repo public.

## 1. Status

| Item | State | Where |
|---|---|---|
| M0 — DRM node in the guest | done 2026-08-30 | `docs/assessment.md` "M0 results", `docs/plan.md` |
| M1 — Omarchy over VNC | done 2026-08-30 — desktop visible from the host over VNC | `docs/assessment.md` "M1 results", `docs/images/` |
| M2 — native macOS window | not started | `docs/plan.md` |
| Local msb | fixed: `~/.microsandbox/bin/msb` is the `gpu-m0` build (0.6.16); old binary kept as `msb-0.6.14.bak` | §3 |
| Running sandbox | `omarchy` (image `msb-omarchy:dev`, VNC on 127.0.0.1:5901) — `msb stop omarchy` when not needed | `bin/run` |

## 2. Where things live

- microsandbox branch `gpu-m0`, worktree `~/.herdr/worktrees/microsandbox/gpu-m0` (commit 77dea1f9): `MSB_GPU=1|venus`, `MSB_GPU_DISPLAY=WxH`. The workspace `[patch.crates-io]` points at `~/.cache/msb-omarchy/msb_krun-0.1.32-patched` (a local git repo holding the published crate plus `ConsoleBuilder::gpu_display`). The upstream fork is cloned at `~/.cache/msb-omarchy/libkrun` (zerocore-ai/libkrun, HEAD dc9f5f1 = 0.1.32, crate in `src/krun`) for the eventual PR.
- Build: `brew install slp/krun/virglrenderer` (done), then in the worktree `LIBRARY_PATH=/opt/homebrew/lib cargo build --profile ci --no-default-features --features net,ssh -p microsandbox-cli` and `codesign --entitlements msb-entitlements.plist --force -s - target/ci/msb`. `build/agentd` is the v0.6.16 release `agentd-aarch64` (agentd unchanged since the release).
- Guest sources: `~/.cache/msb-omarchy/omarchy` (omacom/omarchy at 13f18b2, the commit omarchy-pkgs 4.0.1 pins), `~/.cache/msb-omarchy/omarchy-pkgs` (sparse: `pkgbuilds/omarchy`, `pkgbuilds/omarchy-settings`), `~/.cache/msb-omarchy/omarchy-arm-utm` (reference for the ALARM package set and software-rendering settings).
- Kept sandbox `gpu-m0-modetest` (python:3.12-slim + `libdrm-tests`): `MSB_GPU=1 msb run --name gpu-m0-modetest public.ecr.aws/docker/library/python:3.12-slim -- modetest -M virtio_gpu`.

## 3. M2 next steps

1. `msb_krun_devices` (fork at `~/.cache/msb-omarchy/libkrun`): route 2D resources through rutabaga's `Rutabaga2D` component when virgl is off, so RESOURCE_CREATE_2D / ATTACH_BACKING / TRANSFER_TO_HOST_2D / SET_SCANOUT / FLUSH stop failing on macOS (M0 finding). Verify with `gpu-m0-modetest` (`modetest -s 37@36:1920x1080` must stop producing `response 0x1200` in dmesg).
2. Replace `NoopDisplayBackend` with a `krun_display` backend that owns a CPU framebuffer per scanout and hands frames to a winit + Metal window in microsandbox; then `input` feature → virtio-input from window events.
3. Only then think about `msb run --display`.

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
