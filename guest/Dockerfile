# Omarchy (Quattro) guest for microsandbox on Apple Silicon.
# Arch Linux ARM + Hyprland + quickshell, with the real omarchy /
# omarchy-settings packages built from the pinned upstream commit.
FROM docker.io/menci/archlinuxarm:base

# pacman 7's Landlock sandbox cannot be applied inside a Docker build.
RUN sed -i '/^\[options\]/a DisableSandbox' /etc/pacman.conf \
 && pacman -Syu --noconfirm \
 && pacman -S --noconfirm --needed \
      base-devel sudo git perl jq gum fakeroot pacman-contrib imagemagick curl \
      hyprland hyprland-guiutils hypridle hyprlock hyprpaper hyprpicker hyprsunset \
      quickshell uwsm sddm xdg-desktop-portal-hyprland xdg-desktop-portal-gtk \
      mesa vulkan-swrast vulkan-icd-loader xorg-xwayland qt6-wayland qt6-imageformats \
      qt6-svg qt6-declarative qt6-multimedia qt6-5compat \
      pipewire pipewire-pulse wireplumber \
      wayvnc grim slurp wl-clipboard wtype foot polkit gnome-keyring libsecret \
      xdg-user-dirs xdg-utils lua51 libnotify swayosd brightnessctl pamixer playerctl \
      upower udiskie inotify-tools socat qrencode python-gobject \
      ttf-jetbrains-mono-nerd woff2-font-awesome noto-fonts noto-fonts-emoji \
      hicolor-icon-theme plymouth \
      starship zoxide fzf eza bat ripgrep fd btop fastfetch neovim tmux less unzip wget \
 && pacman -Scc --noconfirm

# Build the omarchy + omarchy-settings packages from the staged source tree.
# `--nodeps` twice is pacman's -dd: skip all dependency checks, not just versions
# (omarchy depends on omarchy-keyring, limine-* and an AUR font that do not exist here).
RUN useradd -m build && echo 'build ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/build
COPY --chown=build:build build/omarchy /src/omarchy
COPY --chown=build:build build/pkgbuilds /src/pkgbuilds
RUN cd /src/pkgbuilds/omarchy-settings \
 && sudo -u build env OMARCHY_SRC=/src/omarchy makepkg -f --nodeps --noconfirm \
 && pacman -U --noconfirm --nodeps --nodeps omarchy-settings-*.pkg.tar.* \
 && cd /src/pkgbuilds/omarchy \
 && sudo -u build env OMARCHY_SRC=/src/omarchy makepkg -f --nodeps --noconfirm \
 && pacman -U --noconfirm --nodeps --nodeps omarchy-*.pkg.tar.* \
 && rm -rf /src /home/build /etc/sudoers.d/build && userdel build

# Desktop user; /etc/skel (seeded by omarchy-settings) provides ~/.config.
RUN useradd -m -G wheel,video,input,audio,render -s /bin/bash omarchy \
 && passwd -d omarchy \
 && echo 'omarchy ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/omarchy \
 && mkdir -p /home/omarchy/.local/state/omarchy/migrations \
 && for m in /usr/share/omarchy/migrations/*.sh; do touch "/home/omarchy/.local/state/omarchy/migrations/$(basename "$m")"; done \
 && chown -R omarchy:omarchy /home/omarchy

# VM-specific overrides: software rendering, 1x scale, SDDM autologin, wayvnc,
# host clipboard sync.
COPY overlay/ /
RUN cp -a /etc/skel-omarchy/. /home/omarchy/ && rm -rf /etc/skel-omarchy \
 && chown -R omarchy:omarchy /home/omarchy \
 && chmod +x /usr/local/bin/xdg-terminal-exec /usr/local/bin/msb-clipboard \
 && mkdir -p /home/omarchy/.config/systemd/user/graphical-session.target.wants \
 && ln -sf ../wayvnc.service /home/omarchy/.config/systemd/user/graphical-session.target.wants/wayvnc.service \
 && ln -sf ../msb-clipboard.service /home/omarchy/.config/systemd/user/graphical-session.target.wants/msb-clipboard.service \
 && chown -R omarchy:omarchy /home/omarchy/.config/systemd \
 && systemctl enable sddm.service \
 && systemctl set-default graphical.target \
 && systemctl mask plymouth-start.service plymouth-quit.service plymouth-quit-wait.service systemd-firstboot.service

# What went in: pacman is unpinned (Arch Linux ARM keeps no archive), so the
# image records its own package list next to the omarchy commit it was built from.
COPY build/versions /usr/share/msb-omarchy/versions
RUN pacman -Q > /usr/share/msb-omarchy/packages \
 && ldconfig && systemd-hwdb update && journalctl --update-catalog \
 && touch /etc/.updated /var/.updated
# The last line is what systemd-update-done.service would do on first boot: with
# the stamps newer than /usr, ldconfig/hwdb/catalog/sysusers/update-done skip
# (ConditionNeedsUpdate), about 0.5 s of every boot. Nothing may touch /usr after it.

CMD ["/bin/bash"]
