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
- Whether the `gpu` device works on the HVF backend was the M0 unknown — answered below: it does.

## M0 results (2026-08-30, HVF, Apple Silicon)

Setup: microsandbox `main` @ 5b1c63d9 in a worktree (`gpu-m0`), `crates/runtime/Cargo.toml` with `msb_krun` features `["blk", "gpu"]`, and an opt-in `MSB_GPU=1` gate in `crates/runtime/lib/vm.rs` that calls `gpu_virgl_flags(VIRGL_RENDERER_NO_VIRGL)` + `gpu_shm_size(256 MiB)` on the console builder. Guest: cached `public.ecr.aws/docker/library/alpine:latest`, kernel libkrunfw 6.12.99.

- **Build**: the `gpu` feature links `libvirglrenderer` unconditionally (`#[link(name = "virglrenderer")]` in `msb_krun_rutabaga_gfx`'s generated bindings; the device hard-codes `RutabagaComponentType::VirglRenderer`). On macOS the library comes from `brew install slp/krun/virglrenderer` (0.10.4e-krunkit, pulls `libepoxy` + `molten-vk`). rutabaga's pkg-config probe is compiled out (it sits under rutabaga's own `gpu` feature, which `msb_krun_devices` does not enable), so the build needs `LIBRARY_PATH=/opt/homebrew/lib`. `krun_display` needs libclang for bindgen (Xcode CLT is enough). `cargo build --profile ci` of `microsandbox-cli` then succeeds and the binary dynamically links `/opt/homebrew/opt/virglrenderer/lib/libvirglrenderer.1.dylib`.
- **Boot with 0 scanouts** (`msb_krun` 0.1.32 API exposes no display configuration): guest gets `/dev/dri/card0` and `/dev/dri/renderD128`, driver `virtio-mmio` → `virtio_gpu`, dmesg `features: +virgl +edid +resource_blob +host_visible -fence_passing`, `+context_init`, `KMS disabled`, 5 cap sets (ids 1, 2, 4, 6, 5). No host-side warnings; the fallback path ("Failed to create virtio_gpu backend") did not trigger. Boot time unchanged (~0.3 s).
- **Answer to the M0 unknown**: `msb_krun`'s virtio-gpu device works on the HVF backend. The gpu worker thread, the macOS `GpuAddMapping` worker, and the SHM window (`Host memory window: 0xc0000000 +0x10000000`) all come up.
- **Boot with 1 scanout** (local `msb_krun` patch adding `ConsoleBuilder::gpu_display(w, h)`, see `docs/plan.md`): dmesg `number of scanouts: 1`, KMS on, connector `card0-Virtual-1` (`status=connected` after `echo detect > status`), 128-byte EDID (`krun-display`), 9 modes with 1920x1080@59.98 preferred. `modetest -M virtio_gpu` (Debian `libdrm-tests`, installed over the guest's own network) lists encoder 38 / connector 37 / CRTC 36; `modetest -s 37@36:1920x1080` returns 0 and the CRTC reports 1920x1080 afterwards. So `drmIsKMS()` passes and `AQ_NO_KMS_REQUIREMENT` is **not** needed.
- **Host side rejects 2D content**: after the modeset the guest logs `response 0x1200 (command 0x101)` (RESOURCE_CREATE_2D), `0x106` (ATTACH_BACKING), `0x105` (TRANSFER_TO_HOST_2D), `0x200/0x202` (ctx create/attach) and `0x1202/0x1203` for `0x103/0x104` (SET_SCANOUT / RESOURCE_FLUSH). The device always builds a `RutabagaComponentType::VirglRenderer` and, with `VIRGL_RENDERER_NO_VIRGL`, virglrenderer has no vrend state, so non-blob resources fail with EINVAL; there is no EGL on macOS to enable virgl. The guest keeps working (dumb buffers are guest-backed; the kernel only logs the error responses), so M1 — Hyprland rendering with llvmpipe into GBM/dumb buffers and wayvnc reading back from the compositor — is not blocked. M2 (frames on the host) needs the 2D path routed to rutabaga's `Rutabaga2D` component (or an equivalent) in `msb_krun_devices`; that is the actual gap upstream libkrun's "display works, gpu on macOS does not" note describes.
- **`MSB_GPU=venus`** (`NO_VIRGL | VENUS`, virglrenderer 0.10.4e-krunkit + MoltenVK): initializes without host errors and the guest sees the same device. Whether Venus contexts work is untested and not on the plan's critical path.
- **Not required**: no guest kernel change.
- **Host environment fixes on the way**: `~/.microsandbox/db/msb.db` had `m20260824_000001_mount_owner_config` applied but not `m20260818_000001_sandbox_network_slot` (a branch build migrated it); `m20260824` is a no-op marker and `m20260818` is idempotent, so deleting the `m20260824` row and letting a `main` build re-apply both fixed the "database schema is newer than this msb binary" error.

## M1 results (2026-08-30)

- **Pipeline**: `docker build --platform linux/arm64` on `menci/archlinuxarm:base` → `docker save` → `msb load` → `msb run --init auto`. systemd is PID 1 (`is-system-running` = `running`), agentd still configures eth0 + DNS and serves `msb exec`/`msb cp`. pacman 7 needs `DisableSandbox` inside Docker (Landlock cannot be applied there).
- **Session**: SDDM with `[Autologin] User=omarchy Session=omarchy` starts `uwsm start … Hyprland` on tty1/seat0 without any extra work; the microVM has a VT (`tty1` active) and logind hands the DRM device to the session. No `/dev/input` exists (no virtio-input yet); Hyprland does not mind and wayvnc injects input through the virtual-keyboard/pointer protocols.
- **Rendering — the one real trap**: with `LIBGL_ALWAYS_SOFTWARE=1` (what omarchy-arm-utm ships for UTM) mesa's `eglQueryDevicesEXT` returns only the software device, so aquamarine's `eglDeviceFromDRMFD` finds no device whose `EGL_DRM_DEVICE_FILE_EXT` is `/dev/dri/card0` and logs `CDRMRenderer(drm): Can't create renderer, no matching devices found`; Hyprland then runs with no renderer. `MESA_LOADER_DRIVER_OVERRIDE=kms_swrast` fixes the compositor but breaks Wayland clients (Qt/quickshell crash with `DRM_IOCTL_MODE_CREATE_DUMB failed: Permission denied` because clients get the render node). With **neither** variable set, mesa 26.2 on this device already falls back to llvmpipe by itself — `kms_swrast` for the compositor (`CDRMRenderer(drm): Using device /dev/dri/card0`) and `swrast` for Wayland clients (`eglinfo -p wayland` → llvmpipe). Keep `WLR_NO_HARDWARE_CURSORS=1` and `AQ_NO_MODIFIERS=1`.
- **Environment changes need a sandbox restart**, not `systemctl restart sddm`: the user's `systemd --user` instance keeps the old environment and uwsm re-imports it.
- **Result**: Hyprland 0.56.1 on `Virtual-1` 1920x1080@59.98, quickshell (Omarchy shell) stable, wayvnc listening on 5900 in the guest, idle CPU ≈1.5 % for Hyprland. Screenshot via `grim` inside the guest: `docs/images/m1-omarchy-desktop.png`. Remaining shell warnings are expected in this image: no NetworkManager backend, no bluez.
- **Host-side proof**: `bin/vnc-shot` (a 60-line RFB client, RAW encoding) receives the full frame through the msb port forward in 0.2 s. `vncdotool capture` connects but never completes a frame against wayvnc; not investigated further.
- **Host port**: macOS Screen Sharing (`com.apple.screensharing`) answers `RFB 003.889` on 127.0.0.1:5900 when enabled, so `bin/run` publishes the guest's 5900 on host **5901**.
- **Operational**: an `msb exec` fed from stdin (`cmd < file`) hung and left later execs hanging until the sandbox was restarted; pass scripts inline (heredoc in `bash -c`) and use `msb cp` for files.

## M2 progress (2026-08-30): host-side 2D scanout works

- `msb_krun_devices` patch: when `virgl_flags` has `VIRGL_RENDERER_NO_VIRGL` and not `VENUS`, `VirtioGpu::create_rutabaga` (and the fallback) build `RutabagaBuilder::new(RutabagaComponentType::Rutabaga2D, 0, 0)` with no channels or export table; the device advertises only `VERSION_1 | EDID` and `num_capsets = 0`. The guest now logs `features: -virgl +edid -resource_blob +host_visible -fence_passing`, `-context_init`, and mesa never probes the virgl driver (the M1 note about `+virgl` no longer applies to this build).
- Level 1: `modetest -M virtio_gpu -s 37@36:1920x1080` in the `gpu-m0-modetest` sandbox returns 0 with **zero** `virtio_gpu_dequeue_ctrl_func` errors (M0 had ten).
- Level 2 exposed a real device bug: `flush_resource` read the whole resource with `stride = resource.width * 4` into a frame buffer sized by the SET_SCANOUT rectangle, and rutabaga's `transfer_2d` returned `InvalidIovec` ("an iovec is outside of guest memory's range"), which the device then `unwrap()`ed — the gpu worker thread panicked on Hyprland's first flush. Fixed by recording the scanout rectangle in `VirtioGpuScanout` and transferring `min(resource, scanout)` with the destination stride; a failed read-back is now an `ErrUnspec` response instead of a panic. Both belong in the upstream PR.
- With the fix, the `MSB_GPU_DUMP` backend (`crates/runtime/lib/gpu_display.rs`, `ConsoleBuilder::gpu_display_backend` from the msb_krun patch) receives `configure_scanout(1920, 1080, 1920, 1080, BGRX)` followed by `present_frame` with `rect 1920x1080+0+0`; the dumped BGRX frame is the live Omarchy desktop (bar, clock, notifications), byte-for-byte the same picture wayvnc serves. Hyprland only flushes on damage, so an idle desktop presents about once a minute (clock).
- Present is synchronous: `FLUSH` is answered after `present_frame` returns, so the viewer must never block in `present_frame` (copy into shared memory, signal, return).

## M2 results (2026-08-30): native window and input

- **Architecture**: `msb sandbox`'s main thread is consumed by `msb_krun::Vm::enter()` (`Result<Infallible>`), so the window lives in a separate process. The sandbox's display backend (`crates/runtime/lib/gpu_display/mod.rs`) writes frames into `<runtime_dir>/display/scanout<N>.fb` (2 slots of `w*h*4` bytes) and serves `hello` / `configure` / `frame{slot,seq,rect}` / `disable` as JSON lines on `display.sock` in the canonical socket dir; `present_frame` only copies (rutabaga's `transfer_read` into the mapped slot) and sends a ~60-byte line, with a 200 ms write timeout so a stalled viewer cannot hold the guest's FLUSH. `msb display <name>` (winit + softbuffer, macOS-only dependencies) maps the file and repaints on `frame`. The M1 VNC number (8 MiB frame in 0.2 s) already showed copying is not the bottleneck; here nothing crosses the socket but metadata.
- **Page flips**: Hyprland issues SET_SCANOUT with a new resource on every flip, so `configure_scanout` runs per frame; it must be idempotent (keep the mapping when size/format are unchanged) or the file is truncated and remapped at the refresh rate.
- **Input**: `msb_krun`'s `input` feature works on macOS once three things are fixed. (1) `msb_krun_utils` macOS `EventFd::new` only honoured `flag == EFD_NONBLOCK`; `pollable_channel` passes `EFD_NONBLOCK | EFD_SEMAPHORE`, so the pipe stayed blocking and the virtio-input worker's second `next_event()` blocked forever — no event ever reached the guest (patched in `~/.cache/msb-omarchy/msb_krun_utils-0.1.32-patched`). (2) The guest writes `select` and `subsel` as two config-space writes; the device re-queries after each, so `query_abs_info` is first asked for a stale axis, and an error there invalidates the config and drops the real query (`ABS_X` came back `min == max == 0`, libinput rejected the device). Backends must answer every axis. (3) The device reports `size_of::<InputDeviceIds>()` for `VIRTIO_INPUT_CFG_ABS_INFO` (harmless, the kernel ignores the size). With those, libinput tags the devices `Keyboard` and `Mouse` (absolute), and Super+K over the socket opens the Omarchy cheatsheet — `docs/images/m2-cheatsheet-via-display.png` is that frame read back through the display path.
- **Verified on the Mac** (2026-08-30): the `msb display` window shows the Omarchy desktop and keyboard/pointer input from the window works (Super+K, mouse), confirmed by the user on the machine; the automated checks above cover the frame files and socket-injected input only.
- **Cleanup**: `run/sandboxes/<hash>/` removal is an openat-hardened unlink of known names; the new `display.sock` had to be added or `msb rm`/`--replace` fails with "Directory not empty".
- **Operational**: `msb exec` silently never runs some long or multi-line `bash -c` commands and then wedges later execs until the sandbox restarts; use `msb cp` for scripts and keep exec commands short. `screencapture` of the viewer window needs Screen Recording permission for the terminal, so the window was verified through the frame files and the headless client rather than a screenshot.
- **Upstream PR material** (all against zerocore-ai/libkrun): `msb_krun_devices` 2D-only mode + scanout read-back fix (37e5696), `msb_krun` `gpu_display` / `gpu_display_backend` / `input_device` builder methods (986266f), `msb_krun_utils` eventfd flag fix (efad426).

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

1. ~~`msb_krun` gpu device on HVF is untested.~~ Resolved (M0): DRM node + KMS work; host-side 2D scanout does not (needs a `Rutabaga2D` path for M2).
2. Package gap on aarch64 (source builds, no omarchy-pkgs db).
3. Quickshell/Qt on llvmpipe: works, slow; effects must be off.
4. Hyprland headless outputs regress periodically (#8806, discussion #12690).
5. The omarchy-iso acceptance harness (QEMU + QMP keyboard) does not transfer; graphical tests here will be their own thing.
