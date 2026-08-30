-- microsandbox virtio-gpu scanout (MSB_GPU_DISPLAY, default 1920x1080): no HiDPI.
hl.env("GDK_SCALE", "1")
hl.monitor({ output = "", mode = "preferred", position = "auto", scale = 1 })
