/*
 * Make Hyprland's glFlush() wait like glFinish().
 *
 * Hyprland commits to KMS right after glFlush(), and llvmpipe rasterizes on
 * worker threads after glFlush() returns. Hyprland's own glFinish() path for
 * software renderers keys on the DRM driver name (virtio_gpu here), so it
 * never runs and the host copies half-drawn frames (docs/assessment.md,
 * "Half-drawn frames"). Loaded with LD_PRELOAD by the compositor unit only.
 * Once loaded into Hyprland it removes LD_PRELOAD from the environment, so
 * the applications Hyprland starts do not load it; any other process that
 * gets it anyway keeps the real glFlush().
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef void (*gl_fn)(void);

static int in_compositor;
static gl_fn target;

__attribute__((constructor)) static void init(void)
{
    char comm[32] = "";
    FILE *f = fopen("/proc/self/comm", "r");

    if (f) {
        if (fgets(comm, sizeof comm, f))
            comm[strcspn(comm, "\n")] = 0;
        fclose(f);
    }
    in_compositor = strcmp(comm, "Hyprland") == 0;
    if (in_compositor)
        unsetenv("LD_PRELOAD");
}

void glFlush(void)
{
    if (!target)
        target = (gl_fn)dlsym(RTLD_NEXT, in_compositor ? "glFinish" : "glFlush");
    if (target)
        target();
}
