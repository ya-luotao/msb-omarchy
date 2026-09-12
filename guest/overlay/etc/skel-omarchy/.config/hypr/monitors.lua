-- Both profiles divide evenly at 1.25: light 1600x900, standard 1920x1080.
-- This changes UI size, not scanout pixel count. Change the latter on the Mac.
hl.env("GDK_SCALE", "1")
hl.monitor({ output = "", mode = "preferred", position = "auto", scale = 1.25 })
