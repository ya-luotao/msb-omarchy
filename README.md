# msb-omarchy

**An Omarchy desktop on your Apple Silicon Mac.**

msb-omarchy runs [Omarchy](https://omarchy.org)'s Hyprland + Quattro desktop inside a [microsandbox](https://github.com/superradcompany/microsandbox) Linux microVM, with a native macOS window, persistent guest storage and a directory shared with your Mac.

The project combines a pinned graphics runtime with an Arch Linux ARM guest image and a small set of host commands. Desktop configuration, application defaults and lifecycle management live in this repository; using them requires no upstream source changes.

[Quick start](#quick-start) · [Daily use](#daily-use) · [Configuration](#configuration) · [Validation](#validation) · [Architecture](#architecture)

![Omarchy desktop with Chinese input and files shared with macOS](docs/images/m4-desktop.png)

*An actual guest screenshot: Foot with Pinyin input, Nautilus and the shared directory.*

## What you get

- **A persistent desktop.** Create a VM once, close and reopen its window, or stop and resume it with files and settings preserved.
- **Native Mac integration.** The graphics runtime provides a macOS display window, keyboard and pointer input, text clipboard synchronization and audio output.
- **A desktop tuned for software rendering.** Two display profiles, larger text, opaque windows and disabled window animations, blur and shadows.
- **Useful applications from the first boot.** Chromium, Nautilus, Foot, CJK fonts and Fcitx5 Pinyin, with working default browser and file-manager associations.
- **Explicit file sharing.** A writable Shared directory, accessible from the top bar and the file-manager sidebar.
- **An isolated runtime.** Checksummed runtime and firmware downloads, with project-local VM state independent of a global microsandbox installation.
- **Recorded validation.** Launcher and release tests, guest image checks, Mac smoke tests, screenshots and measurements tied to the tested image.

**Status:** experimental desktop integration for Apple Silicon. The current guest has passed both display-profile smoke tests on a Mac. The latest experience layer must be built locally; the configured prebuilt fallback is the earlier Omarchy 4.0.2 baseline. See [validation](#validation) and [current boundaries](#current-boundaries) for the scope of those results.

## Quick start

### Requirements

| Component | Requirement |
| --- | --- |
| Host | Apple Silicon Mac with Hypervisor.framework support |
| Tools | Git, Python 3.9+, Homebrew and the macOS `curl` / `codesign` commands |
| Image build | A running Docker engine capable of building `linux/arm64` images |
| Host libraries | `slp/krun/virglrenderer`, `molten-vk` and `libepoxy` |
| Storage | Space for Docker layers, the runtime cache and each VM's writable disk |

Each VM defaults to **4 vCPUs, 4G RAM and a 16G writable disk**. Docker is used to build and load the image; the desktop itself runs through microsandbox and macOS virtualization.

### Install and launch

```sh
git clone https://github.com/ya-luotao/msb-omarchy.git
cd msb-omarchy

brew install slp/krun/virglrenderer molten-vk libepoxy

bin/setup          # Download and verify the pinned runtime and firmware
bin/doctor         # Check the selected runtime and host support
bin/build-rootfs   # Build, validate and load the guest image
bin/run            # Create the desktop and open its native window
```

Setup and image building are first-time steps. Afterward, use **`bin/run`** to return to the desktop. The launcher waits for the desktop shell to respond before opening the window.

A successfully checked and loaded image becomes this checkout's default for **new** VMs. Existing VMs retain their disk and settings. Skipping `bin/build-rootfs` uses the pinned, published 4.0.2 baseline, which does not contain the applications and desktop refinements shown above.

## Daily use

| Action | Command or behavior |
| --- | --- |
| Create, resume or reopen the default desktop | `bin/run` |
| Start it without opening a window | `bin/run --no-display` |
| Close the window | The VM and its applications keep running |
| Stop the VM | `bin/stop` — files and settings remain; running applications close |
| List this project's VMs | `bin/msb list` |
| Capture the current desktop | `bin/screenshot omarchy desktop.png` |
| Check runtime and host support | `bin/doctor` |

Use **`bin/msb`** for low-level commands in this project. Plain `msb` addresses your separate global installation.

### Separate desktops

Give each desktop a name and each concurrently running VM a different forwarded VNC port:

```sh
VNC_PORT=5902 bin/run --name work --profile standard
bin/stop --name work
bin/run --name work
```

The VM keeps its original display profile, image, shared path and resource settings. Rebuilding the image prepares a new default; it does not migrate existing desktops.

Reset is a separate, explicit operation:

```sh
bin/reset --name work --yes
```

This deletes that VM's guest disk and launcher settings. Files in the host Shared directory remain available.

### Keyboard and first launch

The Mac **Command key (⌘)** maps to **Super** inside Omarchy.

| Shortcut | Action |
| --- | --- |
| ⌘ + Enter | Open a terminal |
| ⌘ + K | Browse keyboard shortcuts |
| ⌘ + Shift + Enter | Open the browser |
| ⌘ + Shift + F | Open the file manager |
| Ctrl + Space | Switch English / Chinese Pinyin input |

Click the top-left logo for the menu. The one-time welcome links to a Mac guide, also available through **Learn → Omarchy on Mac**. macOS shortcuts such as Spotlight can take precedence over guest shortcuts.

Chromium may ask you to create a keyring password on its first launch to protect saved browser credentials.

## Display profiles

| Profile | Output resolution | Desktop scale | Use |
| --- | --- | --- | --- |
| `light` — default | 1600 × 900 | 1.25 | Lower rendering cost for everyday interaction |
| `standard` | 1920 × 1080 | 1.25 | More workspace for multiple applications |

Profiles are selected when creating a VM. The light profile renders **30.6% fewer pixels**; UI scaling by itself does not reduce the output pixel count.

Both profiles use a larger shell font, a 12pt terminal font, opaque windows and a compact top bar with workspaces, time, shared files, tray and audio. Window animations, blur and shadows are disabled. The compositor loads a small `glFlush`→`glFinish` shim so software rendering keeps every vCPU without presenting partially drawn frames; `bin/frame-check` tests for such frames.

In the [recorded Mac test](docs/experience.md), create-to-ready took 5.07 seconds for light and 5.67 seconds for standard. Scripted pointer movement produced approximately 60 and 45 scanout announcements per second, respectively. These are single-run observations on an M3 Pro, not end-to-end latency measurements or a guarantee for other machines.

## Files, clipboard and audio

### Shared files

By default, `Shared/` in the project checkout is mounted at `~/Shared` inside the guest. The top-bar folder and file-manager bookmark open that location.

```sh
SHARED_DIR="$HOME/Projects/my-project" VNC_PORT=5903 bin/run --name project
```

The mount maps guest UID/GID 1000 so files can be read and written from either side. Only the selected directory is shared. Documents elsewhere in the guest home remain on that VM's disk.

Shared paths are saved when a VM is created. Keep the checkout and shared directory at stable paths; runtime state and shared mounts are not automatically relocated when the repository moves.

### Clipboard and sound

Text clipboard synchronization works while the native display window is open. To disable it for the viewer:

```sh
MSB_DISPLAY_CLIPBOARD=0 bin/run
```

Clipboard images are not supported. Audio uses the graphics runtime's virtio-snd and CoreAudio path to the Mac's output device.

### VNC

VNC is available at `vnc://127.0.0.1:5901` for the default desktop. The guest listener has no authentication; the launcher forwards it only to the Mac's loopback interface. Set `VNC_PORT` when creating another VM to avoid a port conflict.

## Architecture

```mermaid
flowchart LR
    CLI["Project commands<br/>bin/run · bin/msb"] --> Runtime["Pinned microsandbox runtime<br/>macOS Hypervisor.framework"]
    Runtime <--> Viewer["Native macOS window<br/>Display · keyboard · pointer"]
    Runtime <--> Guest["Arch Linux ARM guest<br/>systemd · Hyprland · Quattro"]
    Shared["Mac Shared directory"] <--> Guest
```

The host runtime boots the guest using macOS virtualization. The guest renders through software OpenGL and virtio-gpu KMS; the display server exposes scanout frames to the native viewer and sends input back to the guest. Clipboard and audio use the existing gpu-m3 integrations.

The image recipe adds this repository's applications and configuration to an immutable Omarchy 4.0.2 base. Before and after installing packages, it verifies that Hyprland, Aquamarine, Mesa, Quickshell and Qt base remain at their original versions.

`config/release.json` pins the base-image digest, graphics runtime checksum and matching firmware checksum. The runtime is the existing [gpu-m3 graphics build](https://github.com/ya-luotao/microsandbox/tree/gpu-m3); a stock global microsandbox binary may not include its display command.

## Configuration

These settings apply when creating a VM. `--name` and `--profile` take precedence over their environment defaults.

| Variable | Default | Purpose |
| --- | --- | --- |
| `NAME` | `omarchy` | VM name |
| `PROFILE` | `light` | Display profile |
| `CPUS` | `4` | Virtual CPU count |
| `MEMORY` | `4G` | Guest memory |
| `ROOT_DISK` | `16G` | Writable guest disk capacity |
| `SHARED_DIR` | Checkout's `Shared/` | Directory shared with the guest |
| `VNC_PORT` | `5901` | Loopback VNC port on the Mac |
| `TAG` | Last successfully built and loaded image, otherwise the pinned baseline | Image for a new VM; also overrides the build tag |
| `MSB_GPU_DISPLAY` | Profile resolution | Advanced output-size override, e.g. `1600x900` |

Advanced runtime overrides are `MSB` for the binary, `MSB_LIBKRUNFW_PATH` for firmware and `MSB_HOME` for state. The default state directory is `.runtime/home/`. The project explicitly selects its own configuration file, so global microsandbox configuration is not inherited.

## Validation

```sh
bin/check
bin/smoke --profile light
bin/smoke --profile standard
```

| Check | What it establishes |
| --- | --- |
| `bin/check` | Launcher persistence and failure handling, release gates, script syntax, JSON and whitespace checks |
| Image build checks | Required commands, application associations, fonts, generated theme, terminal configuration and shared libraries |
| `bin/smoke` | A real Mac VM boots, maps application windows, shares files in both directions and retains files after stop/start |
| `bin/publish --check` | The current local image matches passing smoke reports for both profiles |

Smoke tests create independent VMs with their own shared directories and retain reports and screenshots under `test-runs/`. By default, successful test VMs are stopped and their disks are retained; `--keep` leaves them running for inspection.

The [2026-09-13 validation record](docs/experience.md) contains 16 passing local tests, both Mac smoke reports, image identity, screenshots and measurements. CI runs the local checks and builds the guest on arm64 Linux, retaining package and image metadata. Hosted CI does not establish the Mac desktop result.

### Inspect and troubleshoot

```sh
bin/msb logs omarchy --tail 100
bin/msb exec omarchy -- journalctl -b
bin/screenshot omarchy desktop.png
```

Readiness failures retain the VM for inspection and retry. Concurrent lifecycle operations are rejected; retry after the active operation finishes. If the selected runtime lacks display support or a library is missing, `bin/doctor` reports the problem; use the prerequisites and `bin/setup` to restore the pinned installation.

For graphics diagnostics on a test VM:

```sh
bin/measure-display TEST_VM
bin/display-shot TEST_VM menu.png --key super+space
```

`bin/measure-display TEST_VM --redraw` measures a continuously redrawing terminal instead of pointer motion, and `bin/frame-check TEST_VM` opens and closes the menu repeatedly and fails if a presented frame was half drawn.

These diagnostics attach to the single `display.sock` viewer slot and **close any existing native viewer for that VM**. Reopen it with `bin/msb display TEST_VM`. `bin/display-shot` requires Pillow. Normal `bin/screenshot` uses guest `grim` and does not displace the viewer.

## Building and publishing

```sh
bin/build-rootfs                          # Build, check and load
NO_LOAD=1 bin/build-rootfs                # Build and check only
TAG=msb-omarchy:experiment bin/build-rootfs
```

Every image records package versions, the base digest, source revision and a hash of the guest build inputs under `/usr/share/msb-omarchy/`. The application repository is still rolling: a future build may resolve different application packages or fail dependency checks. Preserve the tested image as the release artifact.

After building and passing both Mac smoke profiles, maintainers can publish using an existing Docker registry login:

```sh
bin/publish --check
bin/publish
```

Publication tags the exact tested local image ID and pushes it without rebuilding. A changed image or missing profile evidence blocks publication. Promoting a release for fresh checkouts is a separate step: update the `image` field in `config/release.json` to the published immutable digest.

The configured fallback currently remains the earlier 4.0.2 baseline. Follow the full quick start to obtain the current experience layer.

## Current boundaries

- Apple Silicon macOS is the supported desktop host. Hardware-accelerated rendering, cursor-only commits and multiple outputs remain future work.
- Guest autologin is enabled. Automatic guest locking and the screensaver are disabled; host screen locking still applies. Configure a guest password and Omarchy's idle plugin before enabling guest locking.
- The guest time zone remains UTC by default.
- The latest smoke checks confirm clipboard and input services. Audible output, fresh end-to-end Mac clipboard transfers and physical keyboard/trackpad feel were not rechecked in that validation pass.

## Project map

| Path | Contents |
| --- | --- |
| `bin/` | Setup, lifecycle, build, capture, validation and release commands |
| `lib/omarchy.py` | Host runtime selection, VM lifecycle and release validation |
| `config/release.json` | Runtime, firmware, image and upstream provenance pins |
| `guest/Dockerfile` | Image build and graphics-package preservation checks |
| `guest/overlay/` | Guest configuration, applications' defaults and integration helpers |
| `tests/` | Launcher and publication-gate tests |
| `docs/` | Milestones, experiments, screenshots and recorded validation |
| `.runtime/`, `Shared/`, `build/`, `test-runs/` | Local runtime state, shared files and generated artifacts; ignored by Git |

Further reading: [milestones](docs/plan.md), [graphics experiments](docs/assessment.md), [desktop validation](docs/experience.md) and the [unused Aquamarine cursor-plane patch](guest/pkgbuilds/aquamarine/README.md). The original full Arch bootstrap recipe remains in the Git history.

This project complements [omarchy-microsandbox](https://github.com/ya-luotao/omarchy-microsandbox), the Omarchy plugin for managing VMs. Here, the Omarchy desktop itself runs inside the VM.

## License

[MIT](LICENSE). Included runtime and guest software retain their respective upstream licenses.
