# Findings

What this project learned about running a graphical Linux guest in microsandbox on Apple Silicon, indexed by layer. Each entry gives the cause, what this project does about it, where it stands upstream, and the section of the [assessment](assessment.md) that holds the evidence: commands, versions, source lines and numbers.

Tested on Apple Silicon (M3 Pro, macOS 27) with microsandbox 0.6.16 and 0.7.2, msb_krun 0.1.32 and 0.1.39, the libkrunfw 6.12 kernel, Mesa 26.2, Hyprland 0.56 and aquamarine 0.14. "Fork" means the runtime branch [`gpu-m4`](https://github.com/ya-luotao/microsandbox/tree/gpu-m4); "image" means this repository's guest image.

Status words: **carried** (fixed in the fork or image), **worked around** (avoided by configuration), **open** (no fix), **constraint** (by design; something to build around).

## Host devices (msb_krun)

**D1. With `NO_VIRGL`, virtio-gpu rejects every 2D command on macOS.** The device always builds rutabaga's virglrenderer component; without virgl, virglrenderer has no state for non-blob resources, so `RESOURCE_CREATE_2D`, `ATTACH_BACKING`, `TRANSFER_TO_HOST_2D`, `SET_SCANOUT` and `RESOURCE_FLUSH` all fail. Guest KMS still works (dumb buffers are guest memory), but the host never receives a pixel. The fork builds the `Rutabaga2D` component when `NO_VIRGL` is set without `VENUS`; the device then offers no capsets and Mesa does not probe the virgl driver.
*Carried · Upstream: withdrawn unreviewed (libkrun #117) · Evidence: [M0](assessment.md#m0-results-2026-08-30-hvf-apple-silicon), [M2 progress](assessment.md#m2-progress-2026-08-30-host-side-2d-scanout-works)*

**D2. Scanout read-back panics the GPU worker when a resource is larger than its scanout.** `flush_resource` read the whole resource (stride `width * 4`) into a buffer sized by the scanout rectangle; rutabaga's `transfer_2d` returned `InvalidIovec`, which the device unwrapped, killing the worker on Hyprland's first flush. The fork records the scanout rectangle, transfers `min(resource, scanout)` with the destination stride, and answers a failed read-back with `ErrUnspec`.
*Carried · Upstream: withdrawn unreviewed (libkrun #117) · Evidence: [M2 progress](assessment.md#m2-progress-2026-08-30-host-side-2d-scanout-works)*

**D3. On macOS, `EventFd` ignores `EFD_NONBLOCK` when another flag is set.** `msb_krun_utils`' macOS `EventFd::new` honoured only `flag == EFD_NONBLOCK`; `pollable_channel` passes `EFD_NONBLOCK | EFD_SEMAPHORE`, so the pipe stayed blocking and the virtio-input worker blocked on its second read: no input event ever reached the guest. Any macOS user of `pollable_channel` is affected, not only input. The fork checks each flag bit.
*Carried · Upstream: withdrawn unreviewed (libkrun #116); independent of the display work · Evidence: [M2 results](assessment.md#m2-results-2026-08-30-native-window-and-input)*

**D4. virtio-input backends must answer every axis.** The guest writes `select` and `subsel` as two config-space writes and the device re-queries after each, so the backend is first asked about a stale axis; an error there invalidates the config and drops the real query (`ABS_X` arrives with `min == max == 0` and libinput rejects the device). The device also reports `size_of::<InputDeviceIds>()` as the size of `VIRTIO_INPUT_CFG_ABS_INFO`, which the kernel ignores.
*Constraint (the fork's backend answers all axes); the size is open and unreported · Evidence: [M2 results](assessment.md#m2-results-2026-08-30-native-window-and-input)*

**D5. Cursor pixels arrive without alpha, then premultiplied.** Linux creates a dumb cursor's host resource as `XRGB8888` whatever the framebuffer format (`virtgpu_gem.c:78`), so an `AR24` cursor reaches the host as an alpha-less format whose bytes do carry alpha; dropping it draws an opaque box. The fork maps each `X` format to its `A` twin on the cursor path, as QEMU effectively does, and un-premultiplies the pixels for winit.
*Carried · Upstream: withdrawn unreviewed (libkrun #119) · Evidence: [Hardware cursor](assessment.md#hardware-cursor-2026-08-31-host-side-done-guest-keeps-the-software-cursor)*

**D6. Present is synchronous.** The device answers the guest's `RESOURCE_FLUSH` only after the display backend's `present_frame` returns, so a slow viewer stalls the guest. The fork's backend copies into a shared-memory slot, sends a 60-byte notice with a 200 ms write timeout, and returns.
*Constraint · Evidence: [M2 progress](assessment.md#m2-progress-2026-08-30-host-side-2d-scanout-works), [M2 results](assessment.md#m2-results-2026-08-30-native-window-and-input)*

**D7. Every page flip reconfigures the scanout.** Hyprland issues `SET_SCANOUT` with a new resource on each flip, so `configure_scanout` runs per frame and must keep its mapping when size and format are unchanged.
*Constraint · Evidence: [M2 results](assessment.md#m2-results-2026-08-30-native-window-and-input)*

**D8. virtio-gpu and virtio-snd cannot quiesce, so a desktop VM cannot be checkpointed.** On microsandbox 0.7.2, `snapshot create --full` and `branch` refuse with `resource virtio_gpu (virtio type 16) cannot quiesce` (virtio-snd likewise). Resident pause and resume work with display, input and sound attached, in about 30 ms each, and keep the desktop.
*Open · Upstream: not reported · Evidence: [v0.7.2 spike](assessment.md#runtime-on-microsandbox-v072-spike-2026-09-24)*

## Guest kernel (libkrunfw)

**K1. No `CONFIG_UDMABUF`, so llvmpipe has no native fences.** llvmpipe exports native fence fds (`EGL_ANDROID_native_fence_sync`) only when it can create a dma-buf through `/dev/udmabuf` (`llvmpipe_init_screen_fence_funcs`). Without explicit sync, a compositor that commits after `glFlush` can scan out a buffer the rasterizer is still writing (G2). Tested 2026-09-26 with a libkrunfw build that sets the option, against the v0.7.2 firmware (both Linux 6.12.109): `/dev/udmabuf` appears (`root:kvm 0660`, granted to the session user by systemd's uaccess rule), EGL reports the extension, Hyprland holds `/dev/udmabuf` and exports sync files, and with the `glFinish` shim removed `bin/frame-check` found 0 half-drawn frames in 60 rounds against 29 of 29 on the control. Full-window redraw rates matched the shim's (47–52 frames/s, light profile, host load around 20). The desktop smoke test passes on that kernel.
*Open · Upstream: [libkrunfw #29](https://github.com/superradcompany/libkrunfw/pull/29) · Evidence: [Guest kernel](assessment.md#guest-kernel-is-ready), [Half-drawn frames](assessment.md#half-drawn-frames-2026-09-03-llvmpipe-races-the-kms-commit)*

**K2. Every page flip flushes the whole plane.** `virtgpu_plane.c` forces full-plane flushes on flips, so damage tracking does not reduce host copies: with the software cursor, pointer motion alone cost 45.5 full 1920×1080 flushes per second.
*Constraint · Evidence: [Hardware cursor](assessment.md#hardware-cursor-2026-08-31-host-side-done-guest-keeps-the-software-cursor)*

**K3. The cursor plane is hidden from atomic clients without the hotspot capability.** virtio_gpu sets `DRIVER_CURSOR_HOTSPOT`, and `drm_mode_getplane_res()` skips cursor planes for atomic clients that have not set `DRM_CLIENT_CAP_CURSOR_PLANE_HOTSPOT`.
*Constraint (clients must set the capability; see G3) · Evidence: [Hardware cursor](assessment.md#hardware-cursor-2026-08-31-host-side-done-guest-keeps-the-software-cursor)*

## Guest graphics stack (Mesa, Hyprland, aquamarine)

**G1. Forcing software rendering breaks the compositor.** `LIBGL_ALWAYS_SOFTWARE=1` leaves aquamarine without an EGL device matching `/dev/dri/card0` ("no matching devices found"), and `MESA_LOADER_DRIVER_OVERRIDE=kms_swrast` fixes the compositor but makes Qt clients fail on the render node. With neither set, Mesa picks `kms_swrast` for the compositor and `swrast` for clients by itself.
*Worked around (neither variable is set) · Evidence: [M1](assessment.md#m1-results-2026-08-30)*

**G2. Hyprland scans out half-drawn llvmpipe frames on virtio-gpu.** Hyprland calls `glFinish()` before committing only when it considers the GPU software, which it decides from the DRM driver name (`virtio_gpu`), never from `GL_RENDERER`. It therefore commits after `glFlush()` while llvmpipe's threads are still rasterizing, and with no fences (K1) nothing re-flushes. The image loads a small `LD_PRELOAD` library into the compositor only, turning its `glFlush()` into `glFinish()`. In the same comparison, `bin/frame-check` flagged 28 of 30 rounds without a fix and none of 30 with the library, which also redraws a full window about twice as fast as the earlier single-thread workaround. The upstream fix is one line in Hyprland; alternatively, a kernel with `CONFIG_UDMABUF` gives llvmpipe fences and makes the shim unnecessary (K1).
*Carried · Upstream: Hyprland does not accept contributions from unvouched contributors · Evidence: [Half-drawn frames](assessment.md#half-drawn-frames-2026-09-03-llvmpipe-races-the-kms-commit), [revisited](assessment.md#half-drawn-frames-revisited-2026-09-24-glfinish-instead-of-one-thread)*

**G3. aquamarine sees no cursor plane.** It sets only `UNIVERSAL_PLANES` and `ATOMIC`, so K3 hides the plane and Hyprland falls back to a software cursor. `guest/pkgbuilds/aquamarine/` has a patch that sets the capability and programs `HOTSPOT_X`/`HOTSPOT_Y`; with it the host receives Hyprland's cursor image and hotspot.
*Carried, not wired in (see G4) · Upstream: aquamarine #372 closed by a bot, unreviewed · Evidence: [Hardware cursor](assessment.md#hardware-cursor-2026-08-31-host-side-done-guest-keeps-the-software-cursor)*

**G4. Without VRR, Hyprland renders a full frame for every hardware-cursor move.** `shouldSkipScheduleFrameOnMouseEvent()` skips only with adaptive sync, and every commit includes the primary plane, so a hardware cursor costs more than the software one (73.6 against 45.5 full frames per second in the same sweep). Moving the plane directly with `modetest` costs 0 frames per second, so the device side is not the limit.
*Open (the image keeps the software cursor) · Upstream: Hyprland issue #16077 closed by a bot · Evidence: [Hardware cursor](assessment.md#hardware-cursor-2026-08-31-host-side-done-guest-keeps-the-software-cursor)*

**G5. Hyprland has no DRM-free mode.** Its backend builds the allocator from a DRM file descriptor and the headless backend has none, so a virtio-gpu node (or another DRM device) is required even for headless use.
*Constraint · Evidence: [Hyprland constraints](assessment.md#hyprland-constraints)*

**G6. `WLR_*` variables do nothing in Hyprland 0.56.** `WLR_RENDERER_ALLOW_SOFTWARE` and `WLR_NO_HARDWARE_CURSORS` have no readers in Hyprland or aquamarine; of the usual VM variables only `AQ_NO_MODIFIERS=1` matters.
*Worked around (dropped) · Evidence: [M3](assessment.md#m3-consolidation-2026-09-03)*

## macOS host

**M1. Binaries linked against the macOS 27 SDK cannot checkpoint.** Any locally built v0.7.x `msb` fails a full checkpoint, even with no extra devices, with `Error reading HVF vCPU interrupt state`; the release binary, which records SDK 14.5, succeeds, and rewriting a local binary's `LC_BUILD_VERSION` to 14.5 made capture and restore work. One trial each way. The fork records 14.5 at link time.
*Carried · Upstream: not reported; affects any local build, not only the display work · Evidence: [v0.7.2 spike](assessment.md#runtime-on-microsandbox-v072-spike-2026-09-24), [release](assessment.md#runtime-on-microsandbox-v072-release-2026-09-24)*

**M2. The guest clock keeps running while paused.** msb_krun_vmm 0.1.39 freezes guest time around `pause_vcpus`/`resume_vcpus_from` only on Windows and Linux/aarch64 (`pause_execution_time` is behind those `cfg`s), so on macOS guest timers treat a long pause as elapsed time. Rechecked 2026-09-26 on the stock v0.7.3 release with an Alpine guest: `/proc/uptime` advanced 45.4 s across a 45.4 s pause, with no soft-lockup warnings. The HVF backend already rebases the virtual counter offset when restoring a snapshot.
*Open · Upstream: not reported · Evidence: [v0.7.2 spike](assessment.md#runtime-on-microsandbox-v072-spike-2026-09-24)*

**M3. Socket paths limit the state directory to 51 bytes.** v0.7.2 places its sockets under `MSB_HOME/run/sandboxes/<24 hex>/`; the longest path is `MSB_HOME` plus 52 bytes and must stay under macOS's 104-byte limit. `msb` refuses longer paths; the launcher checks up front.
*Constraint · Evidence: [v0.7.2 release](assessment.md#runtime-on-microsandbox-v072-release-2026-09-24)*

**M4. Overwriting a signed binary in place gets it killed.** macOS caches code signatures per vnode; copying a rebuilt `msb` over the same inode makes every new exec of it, and possibly running sandboxes on their next page-in, die with SIGKILL. Copy to a new file and rename it.
*Constraint · Evidence: [M3](assessment.md#m3-consolidation-2026-09-03)*

**M5. The `gpu` feature links virglrenderer unconditionally.** On macOS it comes from `brew install slp/krun/virglrenderer` (which also brings MoltenVK and libepoxy), and the build needs `LIBRARY_PATH=/opt/homebrew/lib` because rutabaga's pkg-config probe is compiled out.
*Constraint · Evidence: [M0](assessment.md#m0-results-2026-08-30-hvf-apple-silicon)*

## microsandbox runtime and CLI

**R1. A systemd PID 1 cannot be checkpointed.** Independently of D8, `--init auto` guests are refused with `workload freezer is unavailable: PID 1 handoff workloads are not wholly owned by agentd's cgroup`.
*Constraint · Evidence: [v0.7.2 spike](assessment.md#runtime-on-microsandbox-v072-spike-2026-09-24)*

**R2. `msb exec` can hang.** `msb exec` does not return until its stdin reaches EOF, even after the guest command has exited, so an inherited stdin that never closes hangs it; pass `</dev/null`. Rechecked 2026-09-26 on the stock v0.7.3 release: without `--stream` the command appears to start only at stdin EOF, and `--timeout` counts from then; with `--stream` it starts at once, but `msb exec` still waits for EOF after it exits; a command killed by `--timeout` loses the output it had written. Separately, some long multi-line `bash -c` commands never ran and wedged later execs until the VM restarted (not reduced to a reproducer); a guest command that forks a daemon holding the exec pipes, such as `wl-copy`, does the same unless redirected.
*Open (worked around in this project's scripts) · Upstream: not reported · Evidence: [M1](assessment.md#m1-results-2026-08-30), [M2 results](assessment.md#m2-results-2026-08-30-native-window-and-input), [clipboard](assessment.md#clipboard-results-2026-08-31-text-both-ways)*

**R3. `msb load --input /dev/stdin` fails with "Illegal seek".** Piping without `--input` (`docker save … | msb load`) works.
*Worked around · Evidence: [M3](assessment.md#m3-consolidation-2026-09-03)*

**R4. Runtime upgrades migrate the database one way.** 0.7.2 applies two migrations to a 0.6.16 database, after which 0.6.16 refuses it. The launcher backs the database up before a different runtime first opens it.
*Constraint · Evidence: [v0.7.2 release](assessment.md#runtime-on-microsandbox-v072-release-2026-09-24)*

## Open questions

**V1. Venus graphics on HVF.** `MSB_GPU=venus` initializes without host errors, but this project never ran a Venus context. libkrun [#91](https://github.com/superradcompany/libkrun/pull/91) reports Venus compute working in a microsandbox VM on an M4 Pro once blob mappings are rounded to the 16 KiB host page. Whether Venus can render a desktop and get its frames to the display is [M7](plan.md#m7--venus-on-hvf-graphics-not-only-compute).

## Candidates for upstream reports

Findings that stand alone, without the display work: D3 (macOS `EventFd` flags; libkrun #116 reopened), D8 (virtio-gpu/snd quiesce), K1 (`CONFIG_UDMABUF`; libkrunfw #29), M1 (SDK 27 and HVF checkpoints), M2 (guest clock during pause) and R2 (`msb exec` with an open stdin).
