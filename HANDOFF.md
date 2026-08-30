# Handoff — 2026-08-30

Session state for whoever picks this up next. Delete before making the repo public.

## 1. Status

| Item | State | Where |
|---|---|---|
| M0 — DRM node in the guest | done 2026-08-30 | `docs/assessment.md` "M0 results", `docs/plan.md` |
| M1 — Omarchy over VNC | image builds; first boot not attempted yet | `guest/`, `bin/build-rootfs`, `bin/run` |
| Local msb | fixed: `~/.microsandbox/bin/msb` is the `gpu-m0` build (0.6.16); old binary kept as `msb-0.6.14.bak` | §3 |
| Host disk | nearly full (≈2 GiB free) — `docker save` of the guest image failed; OrbStack stopped | §4 |

## 2. Where things live

- microsandbox branch `gpu-m0`, worktree `~/.herdr/worktrees/microsandbox/gpu-m0` (commit 77dea1f9): `MSB_GPU=1|venus`, `MSB_GPU_DISPLAY=WxH`. The workspace `[patch.crates-io]` points at `~/.cache/msb-omarchy/msb_krun-0.1.32-patched` (a local git repo holding the published crate plus `ConsoleBuilder::gpu_display`). The upstream fork is cloned at `~/.cache/msb-omarchy/libkrun` (zerocore-ai/libkrun, HEAD dc9f5f1 = 0.1.32, crate in `src/krun`) for the eventual PR.
- Build: `brew install slp/krun/virglrenderer` (done), then in the worktree `LIBRARY_PATH=/opt/homebrew/lib cargo build --profile ci --no-default-features --features net,ssh -p microsandbox-cli` and `codesign --entitlements msb-entitlements.plist --force -s - target/ci/msb`. `build/agentd` is the v0.6.16 release `agentd-aarch64` (agentd unchanged since the release).
- Guest sources: `~/.cache/msb-omarchy/omarchy` (omacom/omarchy at 13f18b2, the commit omarchy-pkgs 4.0.1 pins), `~/.cache/msb-omarchy/omarchy-pkgs` (sparse: `pkgbuilds/omarchy`, `pkgbuilds/omarchy-settings`), `~/.cache/msb-omarchy/omarchy-arm-utm` (reference for the ALARM package set and software-rendering settings).
- Kept sandbox `gpu-m0-modetest` (python:3.12-slim + `libdrm-tests`): `MSB_GPU=1 msb run --name gpu-m0-modetest public.ecr.aws/docker/library/python:3.12-slim -- modetest -M virtio_gpu`.

## 3. M1 next steps

1. Free disk, restart OrbStack, rerun `bin/build-rootfs` (the Docker image `msb-omarchy:dev` is already built; only `docker save` + `msb load` failed).
2. `bin/run` (detached `sleep infinity` under `--init auto`), then `msb exec omarchy -- journalctl -b` and `systemctl status sddm`; user session logs via `journalctl --user` as `omarchy`.
3. Expected first problems: SDDM autologin in the microVM (fallback: getty@tty1 autologin + `uwsm start hyprland`); mesa picking the virgl driver because the device advertises `+virgl` while the host rejects every command — try `MESA_LOADER_DRIVER_OVERRIDE=kms_swrast` in `guest/overlay/etc/environment.d/90-vm-graphics.conf`; `omarchy-provision-first-run` / `omarchy-hook post-boot` doing something network- or hardware-dependent.
4. Screen Sharing → `vnc://127.0.0.1:5900`; screenshot for the README.

Pipeline already verified with the bare `menci/archlinuxarm:base` image: `docker save | msb load`, `--init auto` gives systemd as PID 1 in `running` state, eth0 + DNS configured by agentd, `/dev/dri` present.

## 4. Environment notes

- Docker (OrbStack) build needs `DisableSandbox` in pacman.conf (pacman 7 Landlock cannot be applied in a container); the Dockerfile handles it.
- Arch Linux ARM has everything except `ttf-jetbrains-mono-nerd-basic` (use `ttf-jetbrains-mono-nerd`), `xdg-terminal-exec` (wrapper in `guest/overlay/usr/local/bin`), `yaru-icon-theme` (skipped).
- Big local consumers when disk is short: `~/space/heymoney/microsandbox/target` (13 GB cargo cache), `~/.microsandbox/cache` (2.8 GB), the OrbStack data volume.
- The old "database schema is newer than this msb binary" error was a branch-built DB (`m20260824` marker without `m20260818`); fixed by deleting the marker row (backup `~/.microsandbox/db/msb.db.bak-*`). Don't uninstall the brew `virglrenderer`: the installed msb links it dynamically.
