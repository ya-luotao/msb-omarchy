# Desktop experience layer — 2026-09-13

The experience layer is implemented and verified locally on an Apple M3 Pro running macOS 27.0 (26A5425a). No Omarchy, Hyprland, Aquamarine or microsandbox source was changed.

## Delivered behavior

- Project-local, checksummed graphics runtime and matching firmware, isolated from the global microsandbox database.
- Create once, reopen, stop and resume without replacing the guest disk; reset is a separate explicit action. Concurrent lifecycle operations are rejected.
- Light 1600×900 and standard 1920×1080 profiles, both at 1.25 UI scale. Opaque windows, larger text, no window animation, blur or shadow; the existing compositor-only LP_NUM_THREADS=0 workaround remains.
- Compact VM bar, one-time welcome, Mac shortcut guide, Chromium, Nautilus, CJK fonts and Fcitx5 Pinyin.
- UID/GID 1000 shared directory, sidebar bookmark and top-bar entry.
- Image checks, isolated Mac smoke tests, screenshots, a pointer measurement tool and a release gate tied to the exact tested image.

![Final desktop: Pinyin input and shared files](images/m4-desktop.png)

## Validation

`bin/check` passed all 16 tests plus script syntax, JSON and whitespace checks. Four release tests reject changed images, evidence from a different image and failed smoke reports, and accept a matching pair.

`bin/build-rootfs` built and checked the guest, then imported it successfully. The final image is:

`sha256:e5423bab020807d7f88fcb89bec8bfff4609e60f9eb1458367b954237d826bff`

Both `bin/smoke --profile light --keep` and `bin/smoke --profile standard --keep` passed all 13 live checks on that image: shell readiness, installed entry points/libraries, Hyprland config, monitor geometry, rendering environment, clipboard/input services, bidirectional shared files, three mapped desktop apps, a new boot ID and retained files after stop/start.

| Profile | Create to ready | Resume to ready | Pointer scanout frames/s |
| --- | ---: | ---: | ---: |
| light | 5.07 s | 4.76 s | 59.62 |
| standard | 5.67 s | 4.77 s | 45.00 |

The pointer measurement used `bin/measure-display TEST_VM`: 2 s warm-up, 8 s sample, 480 absolute pointer events at a scheduled 60 Hz, empty desktop, 4 vCPUs and 4 GiB guest RAM. Other project test VMs were stopped. This measures scanout announcements, not end-to-end latency or a physical mouse. It is a single sample per profile on this Mac, not a benchmark against a previous release. The light profile renders 30.6% fewer pixels.

Machine-readable evidence: [light](validation/m4/light.json), [standard](validation/m4/standard.json). Complete local logs/screenshots remain under `test-runs/` and `build/`.

Additional live observations:

- Through the display input protocol, Ctrl+Space followed by `nihao` and Space produced `你好` in Foot. The final screenshot above has no deprecated-config warning.
- Super+Space opened the [menu](images/m4-menu.png).
- `bin/run` reopened an existing VM. The native viewer logged a connected 1600×900 BGRX scanout and a macOS window at display scale 2.
- `bin/publish --check` accepted the final image and both matching smoke reports. No image was pushed or release digest promoted.
- The default `omarchy` desktop was then created from the final image. The test VMs were stopped; their disks and evidence were retained.

## Build boundary and remaining checks

A fresh build from the rolling Arch Linux ARM graphics packages failed because Hyprland required an unavailable `libaquamarine.so=13-64` dependency. The default recipe now adds this repository's experience layer to the published, immutable 4.0.2 base:

`ghcr.io/ya-luotao/msb-omarchy@sha256:c53f79040e445f18e8e007b20a0af9756cf6e61d71a5321543470caaeac6290d`

The package transaction retained Hyprland 0.56.1-3, Aquamarine 0.14.0-2, Mesa 1:26.2.1-1, Quickshell 0.3.1-1 and Qt base 6.11.2-3. The build checks those five packages before and after adding apps, then checks shared libraries and real application windows. Application repositories remain rolling; the tested image is the release artifact. A future dependency resolution can fail and should be reviewed, not silently update the graphics stack.

Chromium's first launch asks for a keyring password. That initialization is left to the user; no empty password or weaker password store was configured. Guest time zone currently remains the base image's UTC setting.

Physical keyboard/trackpad feel, audible output and fresh end-to-end Mac clipboard transfers were not rechecked in this pass. The native UI automation service was unavailable; viewer startup was verified from its logs, and guest visuals/input were verified through grim and the display protocol. This record covers local validation before the source commit; it does not establish remote CI success or image publication.
