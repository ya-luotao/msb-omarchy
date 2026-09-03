# Plan

Milestones are ordered by how much they de-risk. Each one ends with something you can screenshot.

## M0 — a DRM node in the guest

Goal: prove `msb_krun`'s `gpu` feature produces `/dev/dri/card0` under HVF.

- [x] In a microsandbox worktree, add `gpu` to the `msb_krun` features in `crates/runtime/Cargo.toml`; wire a virtio-gpu device with one scanout and a no-op display backend in `crates/runtime/lib/vm.rs` — branch [`gpu-m0`](https://github.com/ya-luotao/microsandbox/tree/gpu-m0) of microsandbox, opt-in via `MSB_GPU=1|venus`, `MSB_GPU_DISPLAY=WxH`; the scanout API is a small `msb_krun` 0.1.32 patch (`third_party/msb_krun` on that branch, applied with `[patch.crates-io]`)
- [x] Boot any Linux guest, check `ls /dev/dri`, `cat /sys/class/drm/card0/device/driver`, and `drmIsKMS()` (e.g. `modetest -M virtio_gpu`) — card0 + renderD128, `virtio_gpu`, connector Virtual-1 with EDID, `modetest -s` sets 1920x1080
- [x] If the node has no connector: confirm `AQ_NO_KMS_REQUIREMENT=1` is enough for aquamarine — not needed, the node has a connector
- [x] Record HVF-specific findings in `docs/assessment.md` — done, including the host-side 2D rejection that M2 must fix

Done 2026-08-30. Build recipe: `brew install slp/krun/virglrenderer`, then on the `gpu-m0` branch `LIBRARY_PATH=/opt/homebrew/lib cargo build --profile ci --no-default-features --features net,ssh -p microsandbox-cli`, `codesign --entitlements msb-entitlements.plist --force -s - target/ci/msb` (plus `build/agentd` from the matching microsandbox release, see the justfile).

## M1 — Omarchy over VNC

Goal: the Quattro bar visible in Screen Sharing on the Mac.

- [x] Guest rootfs: Arch Linux ARM base, `--init auto` → systemd, logind, udev — `guest/Dockerfile` on `menci/archlinuxarm:base`; SDDM autologin into the `omarchy` session (uwsm)
- [x] Install Hyprland 0.56 + quickshell from ALARM; the real `omarchy` / `omarchy-settings` packages built with `makepkg` from omarchy-pkgs' PKGBUILDs (`OMARCHY_SRC` = omacom/omarchy @ 13f18b2); only 3 packages missing on aarch64 (`ttf-jetbrains-mono-nerd-basic` → `ttf-jetbrains-mono-nerd`, `xdg-terminal-exec` → wrapper, `yaru-icon-theme` skipped)
- [x] Hyprland env: **no** `LIBGL_ALWAYS_SOFTWARE` (see assessment), `AQ_NO_MODIFIERS=1`, blur/shadows off, scale 1 on the virtio-gpu connector `Virtual-1` (`WLR_NO_HARDWARE_CURSORS=1` dropped 2026-08-31: nothing reads it — see assessment)
- [x] wayvnc as a user service on `graphical-session.target`; `bin/run` publishes `127.0.0.1:5901` (macOS Screen Sharing owns 5900)
- [x] Desktop screenshot: `docs/images/m1-omarchy-desktop.png` (grim inside the guest)
- [x] A VNC client on the Mac shows the same desktop — `bin/vnc-shot` pulls a full 1920x1080 RAW frame from `127.0.0.1:5901` in 0.2 s (`open vnc://127.0.0.1:5901` for Screen Sharing)
- [x] Script it: `bin/build-rootfs`, `bin/run`, `bin/vnc-shot`

Done 2026-08-30.

## M2 — native window

Goal: `msb run omarchy` opens a macOS window with keyboard and pointer.

- [x] `msb_krun_devices`: route 2D resources through rutabaga's `Rutabaga2D` component when virgl is off — `third_party/msb_krun_devices` on the `gpu-m0` branch (`is_2d_only(virgl_flags)`: `NO_VIRGL` without `VENUS`; features drop VIRGL/BLOB/CONTEXT_INIT/UUID, capsets 0, flush copies only the scanout rectangle). `modetest -s` is error-free and a full Hyprland scanout frame reaches the host (`MSB_GPU_DUMP=<dir>` frame-dump backend)
- [x] Host display path: the sandbox process cannot own a window (`Vm::enter()` takes the main thread), so `crates/runtime/lib/gpu_display/` copies each presented frame into a 2-slot memory-mapped file per scanout and announces slots over `display.sock` (JSON lines, next to `agent.sock`); `present_frame` never waits for a viewer
- [x] `msb display <sandbox>` (`crates/cli/lib/commands/display.rs`, macOS: winit 0.30 + softbuffer 0.4 on the main thread before Tokio): maps the frames into a native window (BGRX is softbuffer's 0RGB, a straight copy; nearest-neighbour scale otherwise)
- [x] Input: two virtio-input devices (keyboard; absolute pointer like QEMU's tablet with `ABS_X/Y` 0..32767, three buttons, two wheels) fed from the viewer's winit events over the same socket; libinput accepts both, Super+K opens the Omarchy cheatsheet (`docs/images/m2-cheatsheet-via-display.png`, captured through the display path by a headless socket client)
- [x] `msb run --display` starts the viewer after boot and turns the GPU on for that sandbox (microsandbox commit ce4d2d5f); `bin/run -d --display`
- [x] Upstream PRs opened 2026-08-30: libkrun [#116](https://github.com/superradcompany/libkrun/pull/116) (macOS eventfd flags), [#117](https://github.com/superradcompany/libkrun/pull/117) (2D-only virtio-gpu + scanout read-back), [#118](https://github.com/superradcompany/libkrun/pull/118) (display/input builder methods); microsandbox [#1482](https://github.com/superradcompany/microsandbox/pull/1482) (draft: display server, `msb display`, `--display`) — to be rebased onto #1194's `--gpu` option once the crates are published

Done 2026-08-30 except upstreaming. Run: `MSB=<gpu-m3 build> bin/run -d --display`.

## M3 — consolidate what exists (2026-09-03)

- [x] `gpu-m3` on the fork = `gpu-m0` + fork PRs #1 (frame path), #2 (hide the Mac cursor over the scanout), #3 (clipboard), #4 (virtio-snd), #5 (cursor plane); `gpu-m0` stays the display-only subset behind microsandbox #1482
- [x] New guest image loaded through `docker save | msb load` (stdin works; only `--input /dev/stdin` fails) and verified on the Mac: clipboard both ways, virtio-snd card + `pw-play` without errors, keyboard/pointer, 4 vCPUs
- [x] Guest follows omarchy-pkgs: `bin/build-rootfs` reads `_commit` from the PKGBUILD (4.0.2 @ 346e69e1), the image records `/usr/share/msb-omarchy/{versions,packages}`
- [x] `bin/display-shot`: headless screenshot + key injection over `display.sock`, the seed of a graphical test runner
- [x] Half-drawn frames: Hyprland commits before llvmpipe finished rasterizing (its software-renderer `glFinish` guard keys on the DRM driver name, not on llvmpipe); `LP_NUM_THREADS=0` on the compositor unit closes the race, a one-line Hyprland patch would be the better fix (assessment, "Half-drawn frames")
- [x] CI: `.github/workflows/guest-image.yml` builds the image on `ubuntu-24.04-arm` (no HVF there, so no boot test)
- [x] Boot: the image pre-runs ldconfig/hwdb/catalog and stamps `/etc/.updated`, `graphical.target` 2.8 s → 2.3 s; the desktop session is up 5.6 s after `msb run` returns, SDDM itself costs ~40 ms so it stays

## Later

- Cursor-only commits in Hyprland/aquamarine, so a hardware cursor stops costing a frame per move (see assessment); the host side and the aquamarine plane patch are already done
- [x] Audio via `snd` — the vendored device only had a PipeWire host backend (Linux-only in practice), so the `gpu-m3` branch adds a cpal/CoreAudio backend and `MSB_SND=1`; `pw-play` in the guest reaches the Mac's default output (fork PR [#4](https://github.com/ya-luotao/microsandbox/pull/4))
- [x] Clipboard between host and guest — text both ways while `msb display` is open: a `msb-clipboard` user service in the guest talks newline-delimited JSON over vsock port 5910 to an in-process backend owned by the display server, which relays it to the viewer as `ServerMsg::Clipboard` / `ViewerMsg::Clipboard`; the viewer uses `arboard` for the macOS pasteboard. Images are not carried yet, but the wire format has a `mime` field for them.
- Multiple outputs
- Whether any of this can become Omarchy's own graphical test runner on Macs
