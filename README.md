# msb-omarchy

Run the [Omarchy](https://omarchy.org) desktop — Hyprland + the Quattro Quickshell shell — inside a [microsandbox](https://github.com/superradcompany/microsandbox) microVM on an Apple Silicon Mac, with graphics.

> Status: **M0 done** (2026-08-30) — a guest under microsandbox/HVF gets a KMS-capable `/dev/dri/card0`; nothing graphical runs yet. See [docs/plan.md](docs/plan.md) for the milestones and [docs/assessment.md](docs/assessment.md) for the evidence behind them.

This is the opposite direction from [omarchy-microsandbox](https://github.com/ya-luotao/omarchy-microsandbox), which is an Omarchy bar plugin for managing microsandbox VMs. This repo puts Omarchy *inside* the VM.

## Why

Nobody has shown a full Linux desktop running inside libkrun/microsandbox on a Mac. The closest existing routes to Omarchy-on-Mac go through Virtualization.framework (lume) or QEMU + HVF. A microVM that boots in seconds and opens a native window would be a new thing.

## Shape of the project

```
Mac (Apple Silicon)
└── msb run omarchy                      ← microsandbox, HVF backend
    ├── virtio-gpu (2D scanout) ──────── M1: wayvnc → -p 5900 → Screen Sharing
    │                                    M2: krun_display → native macOS window
    ├── virtio-input ──────────────────── M2: keyboard / pointer
    └── guest: Arch Linux ARM rootfs
        ├── systemd (msb --init auto), seatd/logind
        ├── Hyprland 0.56 on virtio-gpu KMS, llvmpipe (LIBGL_ALWAYS_SOFTWARE=1)
        └── Omarchy Quattro shell (quickshell), packages per omarchy-arm-utm
```

Two pieces live in other repos and will be contributed there:

- **microsandbox**: enable `msb_krun`'s existing `gpu` / `input` Cargo features in `crates/runtime` and add the host-side display plumbing. The guest kernel (libkrunfw 6.12, aarch64) already ships `CONFIG_DRM_VIRTIO_GPU=y`, `CONFIG_VIRTIO_INPUT=y`, `CONFIG_SND_VIRTIO=y`.
- **omarchy** (upstream): anything that turns out to be a genuine aarch64 or headless fix.

This repo holds the guest image build, the run scripts, the docs, and the findings.

## Milestones

| | Goal | Proof |
|---|---|---|
| M0 ✅ | `/dev/dri/card0` appears in a guest with `gpu` enabled | `modetest -M virtio_gpu -s 37@36:1920x1080` succeeds (KMS on, connector Virtual-1) |
| M1 | Omarchy desktop visible over VNC | `msb run … -p 127.0.0.1:5900` + Screen Sharing shows the Quattro bar |
| M2 | Native macOS window | `msb run omarchy` opens a window with keyboard and pointer |

## Hard constraints (read before designing around them)

- Hyprland cannot run with zero DRM devices: aquamarine's headless backend has no allocator (`drmFD() == -1`), so a virtio-gpu node is mandatory even for software rendering. Upstream issue [#7917](https://github.com/hyprwm/Hyprland/issues/7917) is closed as not planned.
- Software rendering over virtio-gpu KMS is the proven path (it is what Hyprland's own CI does). Venus/virgl acceleration on Apple Silicon is not proven; the plan does not depend on it.
- omarchy-pkgs publishes no aarch64 database; roughly 17 of 148 base packages must be built from source (per omarchy-arm-utm).

## Related

- [ggalancs/omarchy-arm-utm](https://github.com/ggalancs/omarchy-arm-utm) — Omarchy Quattro on Arch Linux ARM under UTM; the package list and the software-rendering settings come from here
- [microsandbox docs: VNC desktop](https://docs.microsandbox.dev/examples/development/vnc-desktop) — the existing framebuffer + port-forward pattern M1 follows
- [libkrun display API](https://github.com/libkrun/libkrun) (1.15+) — reference for M2's host window

## License

MIT
