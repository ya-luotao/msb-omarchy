# Feasibility assessment (2026-08-30)

Facts gathered before starting. Each claim carries where it was checked so it can be re-verified when versions move.

## Guest kernel is ready

`superradcompany/libkrunfw` at the commit pinned by microsandbox's `vendor/libkrunfw` submodule (21cb6dce, Linux 6.12.99), file `config-libkrunfw_aarch64`:

| option | value |
|---|---|
| `CONFIG_DRM` | y |
| `CONFIG_DRM_VIRTIO_GPU` | y |
| `CONFIG_VIRTIO_INPUT`, `CONFIG_INPUT_EVDEV` | y |
| `CONFIG_SND_VIRTIO` | y |
| `CONFIG_VIRTIO_VSOCKETS`, `CONFIG_VIRTIO_FS`, `CONFIG_VIRTIO_BLK`, `CONFIG_VIRTIO_NET` | y |
| `CONFIG_CGROUPS`, `CONFIG_NAMESPACES`, `CONFIG_SECCOMP`, `CONFIG_DEVTMPFS` | y |
| `CONFIG_MODULES` | not set (everything is built in) |
| `CONFIG_FB`, `CONFIG_DRM_FBDEV_EMULATION`, `CONFIG_UDMABUF` | not set |

No kernel rebuild is needed for M0–M2.

## microsandbox host side is the gap

- microsandbox does not link the C libkrun. It uses `msb_krun` 0.1.32, a Rust VMM with an HVF backend (`msb_krun_hvf`).
- `msb_krun` / `msb_krun_devices` ship optional features: `gpu` (pulls `rutabaga_gfx` and `krun_display`, a virtio-gpu display backend with `display.rs` / `edid.rs` / `protocol.rs`), `input` (virtio-input), `snd` (virtio-sound via PipeWire).
- `crates/runtime/Cargo.toml` enables only `blk`. `crates/runtime/lib/vm.rs` wires blk / net / vsock / console and nothing else. `agentd` has no display or Wayland concept.
- Networking is an in-tree smoltcp stack with TCP and UDP; `-p 127.0.0.1:PORT:PORT` forwards a host port to the guest. The documented VNC desktop example (LXQt + TigerVNC + noVNC) already uses this.
- Rootfs can be a directory (virtiofs), an ext4 flat root, or a qcow2 disk; `--init auto` hands PID 1 to systemd.
- Unknown: whether the `gpu` device works at all on the HVF backend. It has no test record. This is M0.

## Hyprland constraints

- No DRM-free mode. Hyprland 0.56.1 registers aquamarine backends as HEADLESS mandatory, DRM if available, Wayland fallback — but `Backend::start()` builds its allocator from a backend `drmFD()`, and the headless backend returns -1. With no `/dev/dri` the log says "Cannot open backend: no allocator available". Issue hyprwm/Hyprland#7917 is closed as not planned; `HYPRLAND_HEADLESS_ONLY` is set by hyprtester but has no reader in the 0.56.1 tree.
- The DRM backend needs a libseat session (seatd or logind) and udev enumeration of `card*`.
- Render-only nodes without connectors can be accepted with `AQ_NO_KMS_REQUIREMENT=1`; Hyprland then creates a `HEADLESS-0` 1920x1080 output, and `hyprctl output create headless <name>` adds more.
- Hyprland's CI runs in a QEMU VM with `-vga none -device virtio-gpu-pci` (no GL, so llvmpipe) and declares `HEADLESS-1..6` outputs — proof that KMS + software rendering works.
- Venus/virgl on Apple Silicon: UTM's `virtio-gpu-gl-pci` freezes (utmapp/UTM#7365); omarchy-arm-utm found GL clients "map but never paint" and shipped ramfb + `LIBGL_ALWAYS_SOFTWARE=1`. Do not depend on acceleration.

## Getting pixels out

- ext-image-capture-source-v1 + ext-image-copy-capture-v1 landed in Hyprland 0.54.0; 0.54.1–0.54.2 had a wayvnc gray-screen regression fixed in 0.54.3. wayvnc 0.9+ uses ext-image-copy-capture. wlr-screencopy remains for grim / wf-recorder.
- wayvnc on `HEADLESS-0` is the most proven interactive path; it also injects keyboard and pointer via virtual-input protocols, so M1 needs no virtio-input.
- Sunshine/Apollo are listed as working but have headless-output regressions in the wild.
- libkrun upstream (1.15.0, 2025-08-29) added `krun_add_display` / `krun_set_display_backend` with a CPU-framebuffer callback vtable (`configure_scanout` / `alloc_frame` / `present_frame`) and a GTK4 reference. At merge the note was "macOS should be supported by the display implementation, but is not supported by the gpu" — the macOS side is unverified. M2 reimplements the same idea on `msb_krun`'s `krun_display`.

## aarch64 packages

- Arch Linux ARM `extra`: hyprland 0.56.1-3, aquamarine 0.14.0-2, quickshell 0.3.1-1, mesa 26.2.1.
- omarchy-pkgs has `--arch aarch64` plumbing but no published database (basecamp/omarchy discussion #7956).
- ggalancs/omarchy-arm-utm (pushed 2026-08-29): Omarchy 4 Quattro on ALARM; 121/148 base packages from ALARM, 17 built from source into `/usr/local/bin`, mako removed; `virtio-ramfb`, `LIBGL_ALWAYS_SOFTWARE=1` (no blur/shadows), single monitor.
- nilszeilon/armarchy is a stale pre-Quattro fork (last push 2025-09). maralcbr/omarchy-mx-mac targets bare-metal Asahi only.

## Prior art

No project runs a full Wayland desktop inside libkrun/krunkit on a Mac as of 2026-08. muvm (Linux only) forwards Wayland to a host compositor. On Mac, Omarchy has been run via lume (Virtualization.framework, VNC, llvmpipe) and via QEMU + HVF + VirGL (try-omarchy).

## Risks

1. `msb_krun` gpu device on HVF is untested.
2. Package gap on aarch64 (source builds, no omarchy-pkgs db).
3. Quickshell/Qt on llvmpipe: works, slow; effects must be off.
4. Hyprland headless outputs regress periodically (#8806, discussion #12690).
5. The omarchy-iso acceptance harness (QEMU + QMP keyboard) does not transfer; graphical tests here will be their own thing.
