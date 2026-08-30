# Patched aquamarine — not built into the image

`aquamarine-cursor-plane-hotspot.patch` (against 0.14.0) makes aquamarine see
and program the virtio-gpu cursor plane. It is kept here as an artifact:
`bin/build-rootfs` does **not** stage it and the Dockerfile does not build it,
so the shipped image uses Arch's stock aquamarine and Omarchy keeps its
software cursor.

## What it fixes

virtio_gpu sets `DRIVER_CURSOR_HOTSPOT`, and the kernel hides cursor planes
from any atomic client that has not set `DRM_CLIENT_CAP_CURSOR_PLANE_HOTSPOT`
— `drm_mode_getplane_res()` (`drm_plane.c:808-812`) skips them outright,
because a client that positions the plane by its top-left corner would put the
guest's pointer in the wrong place. aquamarine 0.14 sets only
`UNIVERSAL_PLANES` and `ATOMIC`, so on this GPU it never sees a cursor plane,
never advertises a pointer capability, and Hyprland silently falls back to a
software cursor.

The patch sets the cap once atomic is confirmed and writes `HOTSPOT_X`/
`HOTSPOT_Y` next to `CRTC_X/Y` on the cursor plane, on both the shape and the
move path. The properties were already in aquamarine's plane property table;
nothing wrote them. `CRTC_X/Y` math is unchanged, so real hardware is
unaffected, and the legacy path already passed the hotspot through
`drmModeSetCursor2`. Same shape as KWin's `7fdf0fb792` and `bd2728fac1`.

## Verified

Built and installed in a test VM: aquamarine logs `drm: Plane 33 has type 2`
(nothing at all for plane 33 without the patch), `/sys/kernel/debug/dri/0/state`
shows `plane[33]` bound to `crtc-0` with an `AR24` fb, and the device receives
Hyprland's real 64x64 cursor with its `(3,1)` hotspot plus `MOVE_CURSOR` at the
pointer rate.

## Why it is not enabled

It makes things slower. Same boot, same pointer sweep: software cursor
**45.5 frames/s**, patched hardware cursor **73.6 frames/s** against 74 pointer
moves/s — 1:1 with the input rate, on top of 73.6 `MOVE_CURSOR`/s. Idle is
0 frames/s either way.

The cause is upstream behaviour rather than the plane:
`CMonitor::shouldSkipScheduleFrameOnMouseEvent()` (`Monitor.cpp:1161-1179`)
only skips the frame when adaptive sync is on, so without VRR every
hardware-cursor move reaches aquamarine's `CDRMAtomicImpl::moveCursor` with
`skipSchedule=false`, which calls `scheduleFrame(AQ_SCHEDULE_CURSOR_MOVE)` → a
full `renderMonitor` into a fresh swapchain buffer (`GLRenderer.cpp:108-109`) →
`fb != old fb` (`virtgpu_plane.c:203-208`) → a full-plane flush. And
`CDRMAtomicRequest::addConnector` (`Atomic.cpp:216-238`) adds the primary plane
to every commit regardless.

Making this pay off needs cursor-only commits in Hyprland/aquamarine — KWin
already does plane-selective commits (`drm_pipeline.cpp:64-83`) — which is an
upstream change, not something to carry here.

## Enabling it anyway

Stage this directory into `guest/build/pkgbuilds/` from `bin/build-rootfs`, add
aquamarine's makedepends (`cmake`, `pkgconf`, `hyprwayland-scanner`) to the
Dockerfile's `pacman -S` list, and `makepkg` + `pacman -U` it in the same layer
that builds the omarchy packages, after `hyprland` is installed.
