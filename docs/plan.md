# Plan

Milestones are ordered by how much they de-risk. Each one ends with something you can screenshot.

## M0 — a DRM node in the guest

Goal: prove `msb_krun`'s `gpu` feature produces `/dev/dri/card0` under HVF.

- [x] In a microsandbox worktree, add `gpu` to the `msb_krun` features in `crates/runtime/Cargo.toml`; wire a virtio-gpu device with one scanout and a no-op display backend in `crates/runtime/lib/vm.rs` — branch `gpu-m0` (commit 77dea1f9) in `~/.herdr/worktrees/microsandbox/gpu-m0`, opt-in via `MSB_GPU=1|venus`, `MSB_GPU_DISPLAY=WxH`; the scanout API is a local `msb_krun` 0.1.32 patch (`~/.cache/msb-omarchy/msb_krun-0.1.32-patched`, `[patch.crates-io]`)
- [x] Boot any Linux guest, check `ls /dev/dri`, `cat /sys/class/drm/card0/device/driver`, and `drmIsKMS()` (e.g. `modetest -M virtio_gpu`) — card0 + renderD128, `virtio_gpu`, connector Virtual-1 with EDID, `modetest -s` sets 1920x1080
- [x] If the node has no connector: confirm `AQ_NO_KMS_REQUIREMENT=1` is enough for aquamarine — not needed, the node has a connector
- [x] Record HVF-specific findings in `docs/assessment.md` — done, including the host-side 2D rejection that M2 must fix

Done 2026-08-30. Build recipe: `brew install slp/krun/virglrenderer`, then in the worktree `LIBRARY_PATH=/opt/homebrew/lib cargo build --profile ci --no-default-features --features net,ssh -p microsandbox-cli`, `codesign --entitlements msb-entitlements.plist --force -s - target/ci/msb`.

## M1 — Omarchy over VNC

Goal: the Quattro bar visible in Screen Sharing on the Mac.

- [x] Guest rootfs: Arch Linux ARM base, `--init auto` → systemd, logind, udev — `guest/Dockerfile` on `menci/archlinuxarm:base`; SDDM autologin into the `omarchy` session (uwsm)
- [x] Install Hyprland 0.56 + quickshell from ALARM; the real `omarchy` / `omarchy-settings` packages built with `makepkg` from omarchy-pkgs' PKGBUILDs (`OMARCHY_SRC` = omacom/omarchy @ 13f18b2); only 3 packages missing on aarch64 (`ttf-jetbrains-mono-nerd-basic` → `ttf-jetbrains-mono-nerd`, `xdg-terminal-exec` → wrapper, `yaru-icon-theme` skipped)
- [x] Hyprland env: **no** `LIBGL_ALWAYS_SOFTWARE` (see assessment), `WLR_NO_HARDWARE_CURSORS=1`, `AQ_NO_MODIFIERS=1`, blur/shadows off, scale 1 on the virtio-gpu connector `Virtual-1`
- [x] wayvnc as a user service on `graphical-session.target`; `bin/run` publishes `127.0.0.1:5901` (macOS Screen Sharing owns 5900)
- [x] Desktop screenshot: `docs/images/m1-omarchy-desktop.png` (grim inside the guest)
- [x] A VNC client on the Mac shows the same desktop — `bin/vnc-shot` pulls a full 1920x1080 RAW frame from `127.0.0.1:5901` in 0.2 s (`open vnc://127.0.0.1:5901` for Screen Sharing)
- [x] Script it: `bin/build-rootfs`, `bin/run`, `bin/vnc-shot`

Done 2026-08-30.

## M2 — native window

Goal: `msb run omarchy` opens a macOS window with keyboard and pointer.

- [x] `msb_krun_devices`: route 2D resources through rutabaga's `Rutabaga2D` component when virgl is off — local patch `~/.cache/msb-omarchy/msb_krun_devices-0.1.32-patched` (`is_2d_only(virgl_flags)`: `NO_VIRGL` without `VENUS`; features drop VIRGL/BLOB/CONTEXT_INIT/UUID, capsets 0, flush copies only the scanout rectangle). `modetest -s` is error-free and a full Hyprland scanout frame reaches the host (`MSB_GPU_DUMP=<dir>` frame-dump backend)
- [x] Host display path: the sandbox process cannot own a window (`Vm::enter()` takes the main thread), so `crates/runtime/lib/gpu_display/` copies each presented frame into a 2-slot memory-mapped file per scanout and announces slots over `display.sock` (JSON lines, next to `agent.sock`); `present_frame` never waits for a viewer
- [x] `msb display <sandbox>` (`crates/cli/lib/commands/display.rs`, macOS: winit 0.30 + softbuffer 0.4 on the main thread before Tokio): maps the frames into a native window (BGRX is softbuffer's 0RGB, a straight copy; nearest-neighbour scale otherwise)
- [x] Input: two virtio-input devices (keyboard; absolute pointer like QEMU's tablet with `ABS_X/Y` 0..32767, three buttons, two wheels) fed from the viewer's winit events over the same socket; libinput accepts both, Super+K opens the Omarchy cheatsheet (`docs/images/m2-cheatsheet-via-display.png`, captured through the display path by a headless socket client)
- [x] `msb run --display` starts the viewer after boot and turns the GPU on for that sandbox (microsandbox commit ce4d2d5f); `bin/run -d --display`
- [ ] Upstream the microsandbox side as PRs (see the three msb_krun patches in the assessment)

Done 2026-08-30 except upstreaming. Run: `MSB=<gpu-m0 build> bin/run -d --display`.

## Later

- Audio via `snd` (PipeWire)
- Clipboard between host and guest
- Multiple outputs
- Whether any of this can become Omarchy's own graphical test runner on Macs
