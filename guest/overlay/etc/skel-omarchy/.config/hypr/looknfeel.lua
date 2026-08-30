-- llvmpipe: blur and shadows are too expensive without a GPU.
hl.config({
  decoration = {
    blur = { enabled = false },
    shadow = { enabled = false },
  },
})
