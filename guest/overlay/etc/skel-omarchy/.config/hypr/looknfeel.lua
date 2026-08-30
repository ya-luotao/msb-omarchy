-- llvmpipe: blur and shadows are too expensive without a GPU.
hl.config({
  decoration = {
    blur = { enabled = false },
    shadow = { enabled = false },
  },

  -- A hardware cursor on this virtual GPU has to come out of a dumb (CPU)
  -- buffer: aquamarine's preferred GBM allocator has no working path on a
  -- 2D-only virtio-gpu, so the cursor swapchain would fail to allocate and
  -- Hyprland would fall back to a software cursor -- which costs a full
  -- scanout flush per pointer move.
  --
  -- Inert as of 2026-08-31 and kept as the correct setting for when it is
  -- not: aquamarine 0.14 never enumerates the cursor plane here, so Hyprland
  -- does not get as far as choosing an allocator. See docs/assessment.md.
  cursor = { use_cpu_buffer = 1 },
})
