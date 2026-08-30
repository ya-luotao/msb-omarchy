# Plan

Milestones are ordered by how much they de-risk. Each one ends with something you can screenshot.

## M0 — a DRM node in the guest

Goal: prove `msb_krun`'s `gpu` feature produces `/dev/dri/card0` under HVF.

- [ ] In a microsandbox worktree, add `gpu` to the `msb_krun` features in `crates/runtime/Cargo.toml`; wire a virtio-gpu device with one scanout and a no-op display backend in `crates/runtime/lib/vm.rs`
- [ ] Boot any Linux guest, check `ls /dev/dri`, `cat /sys/class/drm/card0/device/driver`, and `drmIsKMS()` (e.g. `modetest -M virtio_gpu`)
- [ ] If the node has no connector: confirm `AQ_NO_KMS_REQUIREMENT=1` is enough for aquamarine (Hyprland log "Cannot open backend" must not appear)
- [ ] Record HVF-specific findings in `docs/assessment.md`

## M1 — Omarchy over VNC

Goal: the Quattro bar visible in Screen Sharing on the Mac.

- [ ] Guest rootfs: Arch Linux ARM base, `--init auto` → systemd, seatd or logind, udev
- [ ] Install Hyprland 0.56 + quickshell from ALARM; Omarchy install per omarchy-arm-utm's package list, source builds for the missing ~17 packages
- [ ] Hyprland env: `LIBGL_ALWAYS_SOFTWARE=1`, effects off (blur, shadows), single `HEADLESS-0` or the virtio-gpu connector
- [ ] wayvnc as a user service on the Hyprland output; `msb run … -p 127.0.0.1:5900:5900`
- [ ] Screen Sharing → desktop; screenshot for the README
- [ ] Script it: `bin/build-rootfs`, `bin/run`

## M2 — native window

Goal: `msb run omarchy` opens a macOS window with keyboard and pointer.

- [ ] Host display backend: connect `krun_display` scanout (`configure_scanout` / `present_frame`) to a winit + Metal window in microsandbox
- [ ] Enable `input`; route window key/pointer events to virtio-input
- [ ] CLI: `msb run --display …` (or config-file key); document the flag
- [ ] Upstream the microsandbox side as PRs

## Later

- Audio via `snd` (PipeWire)
- Clipboard between host and guest
- Multiple outputs
- Whether any of this can become Omarchy's own graphical test runner on Macs
