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

Setup: microsandbox `main` @ 5b1c63d9 on a branch (`gpu-m0`), `crates/runtime/Cargo.toml` with `msb_krun` features `["blk", "gpu"]`, and an opt-in `MSB_GPU=1` gate in `crates/runtime/lib/vm.rs` that calls `gpu_virgl_flags(VIRGL_RENDERER_NO_VIRGL)` + `gpu_shm_size(256 MiB)` on the console builder. Guest: cached `public.ecr.aws/docker/library/alpine:latest`, kernel libkrunfw 6.12.99.

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
- **Rendering — the one real trap**: with `LIBGL_ALWAYS_SOFTWARE=1` (what omarchy-arm-utm ships for UTM) mesa's `eglQueryDevicesEXT` returns only the software device, so aquamarine's `eglDeviceFromDRMFD` finds no device whose `EGL_DRM_DEVICE_FILE_EXT` is `/dev/dri/card0` and logs `CDRMRenderer(drm): Can't create renderer, no matching devices found`; Hyprland then runs with no renderer. `MESA_LOADER_DRIVER_OVERRIDE=kms_swrast` fixes the compositor but breaks Wayland clients (Qt/quickshell crash with `DRM_IOCTL_MODE_CREATE_DUMB failed: Permission denied` because clients get the render node). With **neither** variable set, mesa 26.2 on this device already falls back to llvmpipe by itself — `kms_swrast` for the compositor (`CDRMRenderer(drm): Using device /dev/dri/card0`) and `swrast` for Wayland clients (`eglinfo -p wayland` → llvmpipe). Keep `AQ_NO_MODIFIERS=1`.
- **Hardware cursor**: see the section below; the guest keeps its software cursor for now.
- **Environment changes need a sandbox restart**, not `systemctl restart sddm`: the user's `systemd --user` instance keeps the old environment and uwsm re-imports it. Without restarting the VM, `loginctl terminate-user omarchy` between stopping and starting sddm is what actually clears it.
- **Result**: Hyprland 0.56.1 on `Virtual-1` 1920x1080@59.98, quickshell (Omarchy shell) stable, wayvnc listening on 5900 in the guest, idle CPU ≈1.5 % for Hyprland. Screenshot via `grim` inside the guest: `docs/images/m1-omarchy-desktop.png`. Remaining shell warnings are expected in this image: no NetworkManager backend, no bluez.
- **Host-side proof**: `bin/vnc-shot` (a 60-line RFB client, RAW encoding) receives the full frame through the msb port forward in 0.2 s. `vncdotool capture` connects but never completes a frame against wayvnc; not investigated further.
- **Host port**: macOS Screen Sharing (`com.apple.screensharing`) answers `RFB 003.889` on 127.0.0.1:5900 when enabled, so `bin/run` publishes the guest's 5900 on host **5901**.
- **Operational**: an `msb exec` fed from stdin (`cmd < file`) hung and left later execs hanging until the sandbox was restarted; pass scripts inline (heredoc in `bash -c`) and use `msb cp` for files.

## Hardware cursor (2026-08-31): host side done, guest keeps the software cursor

Pointer motion alone costs **45.5 full 1920x1080 scanout flushes/s**, because
the guest draws its pointer into the scanout and the kernel forces full-plane
flushes on page flips (`virtgpu_plane.c:91-97`). A virtio-gpu cursor plane
should make pointer motion free. The host side now does; the guest does not.

**The device and the ABI work.** `msb_krun_display` gained
`KRUN_DISPLAY_FEATURE_CURSOR` (`set_cursor`/`move_cursor`), the device serves
the cursor queue, and the runtime forwards image and position to `msb display`.
Driving the plane directly with `modetest -C`, no compositor involved:
**113 cursor images/s and 206 moves/s at 0 frames/s** — the pointer moves for
free, which is the whole point.

**The kernel hides the plane from aquamarine.** virtio_gpu sets
`DRIVER_CURSOR_HOTSPOT`, and `drm_mode_getplane_res()` (`drm_plane.c:808-812`)
skips cursor planes for any atomic client that has not set
`DRM_CLIENT_CAP_CURSOR_PLANE_HOTSPOT` — a client that positions the plane by its
top-left corner would misplace the guest's pointer. aquamarine 0.14 sets only
`UNIVERSAL_PLANES` and `ATOMIC`, so it sees no cursor plane, advertises no
pointer capability, and Hyprland silently software-renders.
`guest/pkgbuilds/aquamarine/` carries a patch that sets the cap and programs
`HOTSPOT_X`/`HOTSPOT_Y`; with it, aquamarine logs `drm: Plane 33 has type 2`,
`plane[33]` binds to `crtc-0` with an `AR24` fb, and the device receives
Hyprland's real 64x64 cursor with its `(3,1)` hotspot. `cursor:use_cpu_buffer`
was never needed — the GBM path works here.

**Cursor pixels needed two fixes on the way through.** The guest allocates its
cursor as a dumb buffer, and Linux creates the host resource with a hardcoded
`DRM_FORMAT_HOST_XRGB8888` whatever the framebuffer's format is
(`virtgpu_gem.c:78`), so an `AR24` cursor arrives as an alpha-less `X` resource
whose pixels do carry alpha — dropping it drew an opaque black box around the
pointer. The device now maps each `X` format to its `A` twin on the cursor path,
as QEMU does by ignoring the resource format entirely
(`hw/display/virtio-gpu.c:44`). The pixels are also premultiplied: of Hyprland's
182 antialiased edge pixels, **0 had a colour channel above its alpha** before
the fix and **28 after** the runtime un-premultiplies them, which is what
winit's `CustomCursor::from_rgba` expects.

**But Hyprland renders a frame per cursor move, so it is a regression.** Same
boot, same sweep: software cursor **45.5 frames/s**, patched hardware cursor
**73.6 frames/s** against 74 pointer moves/s — 1:1 with the input rate, plus
73.6 `MOVE_CURSOR`/s, with 0 frames/s idle either way. The cause is upstream
behaviour, not the plane: `CMonitor::shouldSkipScheduleFrameOnMouseEvent()`
(`Monitor.cpp:1161-1179`) only skips the frame when adaptive sync is on, so
without VRR every hardware-cursor move reaches aquamarine's
`CDRMAtomicImpl::moveCursor` with `skipSchedule=false`, which calls
`scheduleFrame(AQ_SCHEDULE_CURSOR_MOVE)` → a full `renderMonitor` into a fresh
swapchain buffer (`GLRenderer.cpp:108-109`) → `fb != old fb`
(`virtgpu_plane.c:203-208`) → a full flush. `CDRMAtomicRequest::addConnector`
(`Atomic.cpp:216-238`) adds the primary plane to every commit regardless. Fixing
it means cursor-only commits in Hyprland/aquamarine (KWin already does plane-
selective commits, `drm_pipeline.cpp:64-83`) — an upstream change, out of scope
here.

So the patch stays an unwired artifact and the image keeps the software cursor.

## M2 progress (2026-08-30): host-side 2D scanout works

- `msb_krun_devices` patch: when `virgl_flags` has `VIRGL_RENDERER_NO_VIRGL` and not `VENUS`, `VirtioGpu::create_rutabaga` (and the fallback) build `RutabagaBuilder::new(RutabagaComponentType::Rutabaga2D, 0, 0)` with no channels or export table; the device advertises only `VERSION_1 | EDID` and `num_capsets = 0`. The guest now logs `features: -virgl +edid -resource_blob +host_visible -fence_passing`, `-context_init`, and mesa never probes the virgl driver (the M1 note about `+virgl` no longer applies to this build).
- Level 1: `modetest -M virtio_gpu -s 37@36:1920x1080` in the `gpu-m0-modetest` sandbox returns 0 with **zero** `virtio_gpu_dequeue_ctrl_func` errors (M0 had ten).
- Level 2 exposed a real device bug: `flush_resource` read the whole resource with `stride = resource.width * 4` into a frame buffer sized by the SET_SCANOUT rectangle, and rutabaga's `transfer_2d` returned `InvalidIovec` ("an iovec is outside of guest memory's range"), which the device then `unwrap()`ed — the gpu worker thread panicked on Hyprland's first flush. Fixed by recording the scanout rectangle in `VirtioGpuScanout` and transferring `min(resource, scanout)` with the destination stride; a failed read-back is now an `ErrUnspec` response instead of a panic. Both belong in the upstream PR.
- With the fix, the `MSB_GPU_DUMP` backend (`crates/runtime/lib/gpu_display/dump.rs`, `ConsoleBuilder::gpu_display_backend` from the msb_krun patch) receives `configure_scanout(1920, 1080, 1920, 1080, BGRX)` followed by `present_frame` with `rect 1920x1080+0+0`; the dumped BGRX frame is the live Omarchy desktop (bar, clock, notifications), byte-for-byte the same picture wayvnc serves. Hyprland only flushes on damage, so an idle desktop presents about once a minute (clock).
- Present is synchronous: `FLUSH` is answered after `present_frame` returns, so the viewer must never block in `present_frame` (copy into shared memory, signal, return).

## M2 results (2026-08-30): native window and input

- **Architecture**: `msb sandbox`'s main thread is consumed by `msb_krun::Vm::enter()` (`Result<Infallible>`), so the window lives in a separate process. The sandbox's display backend (`crates/runtime/lib/gpu_display/mod.rs`) writes frames into `<runtime_dir>/display/scanout<N>.fb` (2 slots of `w*h*4` bytes) and serves `hello` / `configure` / `frame{slot,seq,rect}` / `disable` as JSON lines on `display.sock` in the canonical socket dir; `present_frame` only copies (rutabaga's `transfer_read` into the mapped slot) and sends a ~60-byte line, with a 200 ms write timeout so a stalled viewer cannot hold the guest's FLUSH. `msb display <name>` (winit + softbuffer, macOS-only dependencies) maps the file and repaints on `frame`. The M1 VNC number (8 MiB frame in 0.2 s) already showed copying is not the bottleneck; here nothing crosses the socket but metadata.
- **Page flips**: Hyprland issues SET_SCANOUT with a new resource on every flip, so `configure_scanout` runs per frame; it must be idempotent (keep the mapping when size/format are unchanged) or the file is truncated and remapped at the refresh rate.
- **Input**: `msb_krun`'s `input` feature works on macOS once three things are fixed. (1) `msb_krun_utils` macOS `EventFd::new` only honoured `flag == EFD_NONBLOCK`; `pollable_channel` passes `EFD_NONBLOCK | EFD_SEMAPHORE`, so the pipe stayed blocking and the virtio-input worker's second `next_event()` blocked forever — no event ever reached the guest (patched in `third_party/msb_krun_utils` on the `gpu-m0` branch). (2) The guest writes `select` and `subsel` as two config-space writes; the device re-queries after each, so `query_abs_info` is first asked for a stale axis, and an error there invalidates the config and drops the real query (`ABS_X` came back `min == max == 0`, libinput rejected the device). Backends must answer every axis. (3) The device reports `size_of::<InputDeviceIds>()` for `VIRTIO_INPUT_CFG_ABS_INFO` (harmless, the kernel ignores the size). With those, libinput tags the devices `Keyboard` and `Mouse` (absolute), and Super+K over the socket opens the Omarchy cheatsheet — `docs/images/m2-cheatsheet-via-display.png` is that frame read back through the display path.
- **Verified on the Mac** (2026-08-30): the `msb display` window shows the Omarchy desktop and keyboard/pointer input from the window works (Super+K, mouse), confirmed by the user on the machine; the automated checks above cover the frame files and socket-injected input only.
- **Cleanup**: `run/sandboxes/<hash>/` removal is an openat-hardened unlink of known names; the new `display.sock` had to be added or `msb rm`/`--replace` fails with "Directory not empty".
- **Operational**: `msb exec` silently never runs some long or multi-line `bash -c` commands and then wedges later execs until the sandbox restarts; use `msb cp` for scripts and keep exec commands short. `screencapture` of the viewer window needs Screen Recording permission for the terminal, so the window was verified through the frame files and the headless client rather than a screenshot.
- **Upstream PR material** (all against zerocore-ai/libkrun), vendored as `third_party/` on the [`gpu-m0` branch](https://github.com/ya-luotao/microsandbox/tree/gpu-m0): `msb_krun_devices` 2D-only mode + scanout read-back fix, `msb_krun` `gpu_display` / `gpu_display_backend` / `input_device` builder methods, `msb_krun_utils` eventfd flag fix.

## Clipboard results (2026-08-31): text both ways

- **Transport**: the display server owns an in-process `VsockPortBackend` (`crates/runtime/lib/gpu_display/clipboard.rs`) registered on host vsock port 5910. `VmBuilder::vsock()` threads the same `VsockBuilder` (`self.vsock = f(self.vsock)`) and `custom()` pushes onto its route list, so the display server's route is registered in its own `.vsock()` call and simply adds to any user `--vsock` routes rather than replacing them. The device itself needs no user route: an `MSB_GPU=1` sandbox booted with `--init auto` and no `--vsock` already has `/dev/vsock` (crw-rw-rw- 10, 259), because TSI networking rides on it.
- **Wire format**: newline-delimited JSON both ways, `{"t":"set","mime":"text/plain;charset=utf-8","data":"<base64>"}`. `data` is base64 of the raw selection, so images only need a new `mime` later. The viewer sees the same value as `ServerMsg::Clipboard` / `ViewerMsg::Clipboard`; unknown JSON lines were already skipped by both ends, so the addition is wire-compatible with an older viewer.
- **Guest**: `msb-clipboard` (python3, stdlib only) runs as a user service in the graphical session, next to `wayvnc.service`. `wl-paste --watch` runs a command per change and hands it the selection on stdin, so concatenated values would be unsplittable; the agent runs `sh -c 'cat; printf "\0"'` and splits its stdout on NUL, which a Wayland text selection cannot contain.
- **Opt-out**: `MSB_DISPLAY_CLIPBOARD=0` (anything but unset or `1`) makes the viewer skip the pasteboard entirely — it is never read, and a guest selection is dropped before it is decoded. The host pasteboard is pushed into the sandbox on every focus and key press, and the guest can replace what the Mac holds, so an untrusted image needs the switch.
- **Loop prevention** lives at the edges, not in the runtime: the agent records the host's value *before* running `wl-copy` (recording it after races the watcher's echo), and the viewer keeps `last_host_text` / `last_guest_text`.
- **Verified on the Mac** (2026-08-31), sandbox restarted on this branch's `msb`:
  - guest → host: `printf guest-round-two | wl-copy` in the session, then `pbpaste` on the Mac prints `guest-round-two`.
  - host → guest: a `ViewerMsg::Clipboard` line for `hello-from-mac` on `display.sock`, then `wl-paste` in the guest prints `hello-from-mac`.
  - late viewer: a viewer attaching after the guest copied receives the remembered selection right after `configure` (the pasteboard picked up `hello-from-guest` on reconnect).
  - `runtime.log` carries one `gpu display: clipboard agent connected conn=1` line and no warnings; the agent journal carries only `connected to the host on port 5910`.
- **Not driven from a script**: the host→guest leg is meant to fire on the viewer window's `Focused(true)`. `osascript`/System Events could not raise the window here (`AppleEvent timed out (-1712)`, and process queries return nothing without Automation permission for the terminal), so the pasteboard→`ViewerMsg` hop was exercised by writing the protocol message to `display.sock` directly; everything downstream of it is the real path.
- **Operational**: `wl-copy` forks a child that keeps serving the selection and inherits the exec pipes, so a bare `msb exec … -- sh -c 'printf x | wl-copy'` never returns and is eventually killed — which also drops the selection it was serving. Redirect it (`wl-copy >/dev/null 2>&1`) to keep `msb exec` from wedging.

## M3 consolidation (2026-09-03)

- **Branches**: the 2026-08-31 work lived in five stacked fork PRs and never in one runnable build. `gpu-m3` on ya-luotao/microsandbox merges them (display-cursor-plane already contained #1, #2 and #3; virtio-snd merged on top with two trivial conflicts: `third_party/README.md` and `Cargo.lock`, resolved by regenerating the lock). `gpu-m0` is left as is because it is the head of upstream draft #1482; merging into it would grow that PR past what it describes.
- **Installed `msb`**: rebuilt from `gpu-m3` (0.6.16), re-signed with `msb-entitlements.plist`; links CoreAudio/AudioToolbox (cpal) and `libvirglrenderer.1.dylib` as before. The previous binary is `~/.microsandbox/bin/msb-gpu-m0.bak`.
- **`msb load` from stdin works**: `docker save msb-omarchy:dev | msb load` imported the 3.9 GB image (digest changed from `f7aada61` to `e4595de5`), so `bin/build-rootfs` no longer writes `guest/build/image.tar`. The 08-31 note that stdin "imports nothing" was wrong; only `--input /dev/stdin` fails (Illegal seek).
- **4 vCPUs**: `bin/run`'s default `--cpus 4` boots fine (`nproc` = 4). The 08-31 VmCreate failure at 4 vCPUs was not reproducible and is treated as host load at the time.
- **Verified on the Mac with the merged build** (sandbox `omarchy`, `MSB_GPU=1 MSB_SND=1`, `msb display` window open): `/proc/asound/cards` lists `virtio-snd`, PipeWire shows one sink and `pw-play` of a 3 s 440 Hz tone exits 0 with no `virtio_snd` errors in dmesg (the listening test is still a human's); `msb-clipboard.service` is active and connected on port 5910; text set with `pbcopy` before the window took focus appeared in `wl-paste`, and `wl-copy` in the guest landed in `pbpaste` within 2 s. The viewer reports `window: 1920x1080 physical, scale 2`, so HiDPI is a straight 1:1 copy on this Mac.
- **Operational**: `wl-copy` forks a daemon that keeps the selection alive; run it through `msb exec` only with `</dev/null >/dev/null 2>&1 &` or the exec waits on the pipes and the session's later execs wedge. `wayvnc` sends `ServerCutText` (RFB message 3) to a new client whenever the guest clipboard holds text, which broke `bin/vnc-shot` until it learned to skip messages 2 and 3. The Wayland socket in the guest is `wayland-1`, not `wayland-0`; read `WAYLAND_DISPLAY` from `systemctl --user show-environment`.
- **Guest image follows omarchy-pkgs**: `bin/build-rootfs` reads `_commit` from `pkgbuilds/omarchy/PKGBUILD` (4.0.2 = omarchy 346e69e1, 28 commits after the previously hard-coded 13f18b2, all installer/security fixes, no dependency changes) and checks that commit out in the omarchy clone. The image records `/usr/share/msb-omarchy/versions` (omarchy commit, omarchy-pkgs commit, msb-omarchy commit, build time) and `/usr/share/msb-omarchy/packages` (`pacman -Q`, 562 packages) because Arch Linux ARM keeps no package archive and the Dockerfile cannot pin what `pacman -Syu` resolves. `pacman -U --nodeps --nodeps` is deliberate: pacman's `-dd` skips dependency checks entirely, a single `-d` only skips version checks and the omarchy package then fails on `omarchy-keyring`, `limine-*` and `ttf-jetbrains-mono-nerd-basic`.
- **Dead variables**: `WLR_RENDERER_ALLOW_SOFTWARE` joins `WLR_NO_HARDWARE_CURSORS` on the floor. Neither name appears in the Hyprland or aquamarine sources (GitHub code search: 0 hits each; `AQ_NO_MODIFIERS`, kept, has 2), so both env files now set only `AQ_NO_MODIFIERS=1`.

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
