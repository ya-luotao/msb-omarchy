# Handoff — 2026-08-30

Session state for whoever picks this up next. Delete before making the repo public.

## 1. Status

| Item | State | Where |
|---|---|---|
| M0 — DRM node in the guest | done 2026-08-30 | `docs/assessment.md` "M0 results", `docs/plan.md` |
| M1 — Omarchy over VNC | done 2026-08-30 — desktop visible from the host over VNC | `docs/assessment.md` "M1 results", `docs/images/` |
| M2 — native macOS window | step A done (2D scanout reaches the host, frame-dump backend); viewer process not started | `docs/assessment.md` "M2 progress" |
| Local msb | fixed: `~/.microsandbox/bin/msb` is the `gpu-m0` build (0.6.16); old binary kept as `msb-0.6.14.bak` | §3 |
| Running sandbox | `omarchy` (image `msb-omarchy:dev`, VNC on 127.0.0.1:5901) — `msb stop omarchy` when not needed | `bin/run` |

## 2. Where things live

- microsandbox branch `gpu-m0`, worktree `~/.herdr/worktrees/microsandbox/gpu-m0` (commit 77dea1f9): `MSB_GPU=1|venus`, `MSB_GPU_DISPLAY=WxH`. The workspace `[patch.crates-io]` points at `~/.cache/msb-omarchy/msb_krun-0.1.32-patched` (a local git repo holding the published crate plus `ConsoleBuilder::gpu_display`). The upstream fork is cloned at `~/.cache/msb-omarchy/libkrun` (zerocore-ai/libkrun, HEAD dc9f5f1 = 0.1.32, crate in `src/krun`) for the eventual PR.
- Build: `brew install slp/krun/virglrenderer` (done), then in the worktree `LIBRARY_PATH=/opt/homebrew/lib cargo build --profile ci --no-default-features --features net,ssh -p microsandbox-cli` and `codesign --entitlements msb-entitlements.plist --force -s - target/ci/msb`. `build/agentd` is the v0.6.16 release `agentd-aarch64` (agentd unchanged since the release).
- Guest sources: `~/.cache/msb-omarchy/omarchy` (omacom/omarchy at 13f18b2, the commit omarchy-pkgs 4.0.1 pins), `~/.cache/msb-omarchy/omarchy-pkgs` (sparse: `pkgbuilds/omarchy`, `pkgbuilds/omarchy-settings`), `~/.cache/msb-omarchy/omarchy-arm-utm` (reference for the ALARM package set and software-rendering settings).
- Kept sandbox `gpu-m0-modetest` (python:3.12-slim + `libdrm-tests`): `MSB_GPU=1 msb run --name gpu-m0-modetest public.ecr.aws/docker/library/python:3.12-slim -- modetest -M virtio_gpu`.

## 3. M2 next steps

Done: `~/.cache/msb-omarchy/msb_krun_devices-0.1.32-patched` (2D-only mode + scanout read-back fix, commit 37e5696), `msb_krun-0.1.32-patched` (`gpu_display_backend`, commit 83989de), microsandbox `gpu-m0` commit e4735b6d (`crates/runtime/lib/gpu_display.rs`, `MSB_GPU_DUMP`). `MSB=~/.herdr/worktrees/microsandbox/gpu-m0/build/msb MSB_GPU_DUMP=~/.cache/msb-omarchy/frames bin/run -d` dumps `scanout0.raw` (BGRX); convert with Pillow (`Image.frombytes("RGBA", (1920, 1080), raw, "raw", "BGRA")`).

Design decided for the rest (see assessment): the sandbox process's main thread is consumed by `Vm::enter()` (returns `Infallible`), so the window lives in a separate viewer process. Plan:
1. Display backend in `crates/runtime` that copies each presented frame into a shared-memory file per scanout (in the sandbox runtime dir) and publishes `Configure{scanout,w,h,format,path}` / `Frame{scanout,seq,rect}` over a Unix socket (`display.sock` next to `agent.sock`); `present_frame` must not wait for the viewer.
2. `msb display <sandbox>` (crates/cli, macOS-only deps gated by `cfg(target_os = "macos")`): winit + softbuffer on the main thread, maps the shm, repaints on `Frame`.
3. Input: enable msb_krun's `input` feature, add `ConsoleBuilder::gpu_input(config, events)` to the msb_krun patch, send winit key/pointer events (absolute EV_ABS pointer) back over the socket into a `krun_input` event provider. The fork's `examples/krun_gtk_display/src/input_backend.rs` + `input_constants.rs` are the reference.
4. `msb run --display` = run the viewer after boot.

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
