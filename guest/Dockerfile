# Extend the project's verified desktop without upgrading the compositor.
# Arch Linux ARM's rolling repository can temporarily contain incompatible
# Hyprland/aquamarine packages. The original bootstrap recipe is in git history.
ARG BASE_IMAGE=ghcr.io/ya-luotao/msb-omarchy@sha256:c53f79040e445f18e8e007b20a0af9756cf6e61d71a5321543470caaeac6290d
FROM ${BASE_IMAGE}

RUN pacman -Q hyprland aquamarine mesa quickshell qt6-base > /tmp/graphics-packages \
 && pacman -Sy --noconfirm \
 && pacman -S --noconfirm --needed \
      chromium nautilus gvfs noto-fonts-cjk adwaita-icon-theme \
      fcitx5 fcitx5-configtool fcitx5-gtk fcitx5-qt fcitx5-chinese-addons \
 && pacman -Q hyprland aquamarine mesa quickshell qt6-base | cmp /tmp/graphics-packages - \
 && rm /tmp/graphics-packages \
 && pacman -Scc --noconfirm
# A dependency requiring a graphics-stack update fails this build, rather than
# silently changing the rendering baseline. Review a new base image separately.

COPY overlay/ /
RUN gcc -shared -fPIC -O2 -Wall -Werror -o /usr/local/lib/msb-glfinish.so /usr/local/src/msb-glfinish.c -ldl \
 && cp -a /etc/skel-omarchy/. /home/omarchy/ && rm -rf /etc/skel-omarchy \
 && chmod +x /usr/local/bin/xdg-terminal-exec /usr/local/bin/msb-* \
 && test "$(id -u omarchy)" = 1000 \
 && mkdir -p /home/omarchy/Shared /home/omarchy/Projects /home/omarchy/Downloads /home/omarchy/Pictures /home/omarchy/Videos \
 && sed -i '/-- omarchy_preinstalled_bindings = false/c\omarchy_preinstalled_bindings = false' /home/omarchy/.config/hypr/hyprland.lua \
 && mkdir -p /home/omarchy/.local/state/omarchy/done \
 && touch /home/omarchy/.local/state/omarchy/done/first-run-user \
 && chown -R omarchy:omarchy /home/omarchy \
 && sudo -H -u omarchy env OMARCHY_PATH=/usr/share/omarchy OMARCHY_THEME_HEADLESS=1 omarchy-theme-set "Tokyo Night" \
 && mkdir -p /home/omarchy/.config/systemd/user/graphical-session.target.wants \
 && ln -sf ../wayvnc.service /home/omarchy/.config/systemd/user/graphical-session.target.wants/wayvnc.service \
 && ln -sf ../msb-clipboard.service /home/omarchy/.config/systemd/user/graphical-session.target.wants/msb-clipboard.service \
 && ln -sf /usr/lib/systemd/user/omarchy-fcitx5.service /home/omarchy/.config/systemd/user/graphical-session.target.wants/omarchy-fcitx5.service \
 && chown -R omarchy:omarchy /home/omarchy \
 && cp /usr/share/msb-omarchy/versions /usr/share/msb-omarchy/base-versions

COPY build/versions /usr/share/msb-omarchy/versions
RUN pacman -Q > /usr/share/msb-omarchy/packages \
 && ldconfig && systemd-hwdb update && journalctl --update-catalog \
 && touch /etc/.updated /var/.updated
# Nothing may touch /usr after these ConditionNeedsUpdate stamps.
CMD ["/bin/bash"]
