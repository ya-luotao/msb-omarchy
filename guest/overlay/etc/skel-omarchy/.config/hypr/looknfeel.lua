-- VM defaults: finished frames and predictable interaction on llvmpipe.
hl.config({
  animations = { enabled = false },
  decoration = {
    blur = { enabled = false },
    shadow = { enabled = false },
    rounding = 4,
  },
  general = { gaps_in = 4, gaps_out = 8, border_size = 2 },
})
-- Omarchy's default window rules otherwise retain 0.985/0.96 opacity.
o.window(".*", { opacity = "1 1" })
