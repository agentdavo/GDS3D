/*
 * GDS3D headless renderer -- EGL offscreen, no X server.
 *
 * WHY THIS EXISTS
 * ---------------
 * linux/main.cpp implements WindowManager as Wm_X11 on raw X11 + GLX: it calls
 * XOpenDisplay, creates a window, and drives an XNextEvent loop. That cannot
 * run without a display, so the viewer is unusable over SSH, in CI, or from an
 * agent. This file provides Wm_EGL, the same WindowManager interface backed by
 * an EGL pbuffer, which renders one or more frames and writes a PPM.
 *
 * It is a SEPARATE BINARY (GDS3D_egl, built by Makefile.egl) rather than a flag
 * on the existing one, because main.cpp owns `int main()` and the X11 path is
 * known-good. Nothing here changes the interactive viewer.
 *
 * WHAT IS STUBBED, AND WHY THAT IS HONEST
 *   render_text  -- no-op. The X11 path builds a font with glXUseXFont, which
 *                   needs a display. Overlays (legend, rulers, performance
 *                   counter) therefore DO NOT APPEAR in headless output. The
 *                   geometry does. Do not read a missing legend as a bug.
 *   cursor/mouse -- no-ops; there is no pointer.
 *   query_update -- always false; file monitoring is meaningless for one shot.
 *
 * OUTPUT is binary PPM (P6), which needs no image library. Convert with
 * ImageMagick if you want a PNG:
 *     convert out.ppm out.png
 *
 * Usage:
 *     GDS3D_egl -p <process.txt> -i <file.gds> [-t <topcell>] \
 *               [--egl-size W H] [--egl-out out.ppm] [--egl-frames N] \
 *               [--egl-view RX RY] [--egl-fit] [--egl-margin M] \
 *               [--egl-explode F] [--egl-ui] \
 *               [--egl-video out.mp4 --egl-seconds S --egl-fps N --egl-spin DEG]
 *
 * True isometric is --egl-view -54.74 <ry>: that elevation makes the forward
 * vector (+-0.577, +-0.577, 0.577), i.e. equal parts x/y/z.
 *
 * --egl-frames defaults to 3: the first draw() often runs before the camera
 * and display lists have settled, so a couple of warm-up frames give a stable
 * image. Raise it if the result looks half-built.
 *
 * CAMERA STATUS -- READ THIS BEFORE TRUSTING --egl-fit
 * ---------------------------------------------------
 * WORKS: the default top-down view (no --egl-view) frames the design correctly,
 * because that is the framing GDS3D computes for itself.
 *
 * WORKS WITH TUNING: --egl-view rx ry renders genuine tilted 3D, but you will
 * have to find a workable --egl-pos/--egl-margin by hand.
 *
 * DOES NOT RELIABLY WORK: --egl-fit. Two reasons, both verified:
 *   1. _xmin/_xmax come back 0.0 on the shipped example, so the bounding box
 *      cannot be used to derive a target.
 *   2. The startup (_x,_y,_z) is a camera POSITION, not a look-at target, so
 *      treating it as one and offsetting by the tilt puts the design out of
 *      frame. Empirically both offset signs give a black frame at rx=-45,
 *      while rx=-55 with ry=25 happens to land on geometry -- i.e. the ry
 *      rotation was compensating for the wrong offset, not confirming it.
 * Fixing this properly means working out GDS3D's actual pan/orbit semantics
 * from gdsparse_ogl.cpp rather than inferring them from the view matrix.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/time.h>
#include <math.h>
#include <vector>
#include <map>

#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GL/gl.h>

#include "../gdsoglviewer/windowmanager.h"
#include "../gdsoglviewer/gdsparse_ogl.h"
#include "../gdsoglviewer/gdsobject_ogl.h"
#include "../libgdsto3d/gdspolygon.h"        /* GDSBB */

/* Real bounds of every vertex handed to the renderer -- see renderer.cpp. */
extern float gds3d_vmin[3];
extern float gds3d_vmax[3];
extern unsigned long gds3d_vcount;

/* Disables RenderList's screen-space LOD; see gdsobject_ogl.cpp. */
extern bool gds3d_force_full_detail;   /* exploded_view / _fraction / _accel */

class Wm_EGL : public WindowManager
{
private:
    EGLDisplay egl_dpy;
    EGLContext egl_ctx;
    EGLSurface egl_surf;
    std::vector<htime *> timers;

public:
    Wm_EGL() : egl_dpy(EGL_NO_DISPLAY), egl_ctx(EGL_NO_CONTEXT),
               egl_surf(EGL_NO_SURFACE), msaa_samples(0), fixed_fps(60.0f) {}
    ~Wm_EGL()
    {
        for (size_t i = 0; i < timers.size(); i++)
            free(timers[i]);
        if (egl_dpy != EGL_NO_DISPLAY) {
            eglMakeCurrent(egl_dpy, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
            if (egl_ctx != EGL_NO_CONTEXT) eglDestroyContext(egl_dpy, egl_ctx);
            if (egl_surf != EGL_NO_SURFACE) eglDestroySurface(egl_dpy, egl_surf);
            eglTerminate(egl_dpy);
        }
    }

    void gl_finish() { glFinish(); }
    bool hide_mouse(void) { return true; }
    bool show_mouse(void) { return true; }
    void change_cursor(int) {}
    void move_mouse(int, int) {}
    bool query_update(FILE *) { return false; }

    // No font without a display -- see the header comment.
    void render_text(int, int, const char *, VECTOR4D) {}

    /* DETERMINISM: report a FIXED frame time, not wall clock.
       gdsparse_ogl.cpp computes _fps = 1/timer(), then RenderList does

           if (fps > 10.0) { _Quality = fps; RenderList(view, fps, false); }

       and the inner RenderList gates layer visibility and ALPHA on Quality:

           if (zrel > 1.0f*Quality/10.0) ...
           if (zrel > 0.5f*Quality/10.0) alpha = ...

       so on a software rasteriser, where the measured fps wobbles every frame,
       layers fade and pop between otherwise identical frames -- visible as
       flicker in a rendered video. Pinning the frame time makes _fps constant
       and every frame reproducible. fixed_fps is settable with --egl-lod-fps;
       higher = more detail retained. */
    float fixed_fps;

    float timer(htime *t, int reset)
    {
        if (fixed_fps > 0.0f) {
            if (reset) { /* nothing to advance; frame time is constant */ }
            return 1.0f / fixed_fps;
        }
        struct timeval now;
        gettimeofday(&now, NULL);
        double cur = now.tv_sec + now.tv_usec / 1000000.0;
        double prev = *(double *)t;
        if (reset) *(double *)t = cur;
        return (float)(cur - prev);
    }

    htime *new_timer()
    {
        double *t = (double *)malloc(sizeof(double));
        struct timeval now;
        gettimeofday(&now, NULL);
        *t = now.tv_sec + now.tv_usec / 1000000.0;
        timers.push_back((htime *)t);
        return (htime *)t;
    }

    int msaa_samples;   /* requested; 0 = off */

    bool egl_init(int w, int h)
    {
        egl_dpy = eglGetDisplay(EGL_DEFAULT_DISPLAY);
        if (egl_dpy == EGL_NO_DISPLAY) {
            fprintf(stderr, "eglGetDisplay failed\n");
            return false;
        }
        EGLint major, minor;
        if (!eglInitialize(egl_dpy, &major, &minor)) {
            fprintf(stderr, "eglInitialize failed (0x%x)\n", eglGetError());
            return false;
        }
        fprintf(stderr, "EGL %d.%d  vendor: %s\n", major, minor,
                eglQueryString(egl_dpy, EGL_VENDOR));

        /* MSAA the easy way: ask EGL for a MULTISAMPLED PBUFFER. The pbuffer
           then IS the multisample buffer, the rasteriser resolves on read, and
           glReadPixels returns resolved pixels -- no FBO, no explicit blit.
           (GDS3D does carry its own multisampled-FBO path in renderer.cpp,
           offlineFramebuffer/blitFramebuffer with glRenderbufferStorage-
           MultisampleEXT + glBlitFramebufferEXT, but that needs the renderer
           driving it; this stays out of its way entirely.)
           Falls back to 0 samples if the driver offers no such config. */
        EGLConfig cfg;
        EGLint n = 0;
        int want = msaa_samples;
        while (true) {
            const EGLint cfg_attr[] = {
                EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
                EGL_RENDERABLE_TYPE, EGL_OPENGL_BIT,
                EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8,
                EGL_ALPHA_SIZE, 8, EGL_DEPTH_SIZE, 24,
                EGL_SAMPLE_BUFFERS, want > 0 ? 1 : 0,
                EGL_SAMPLES, want,
                EGL_NONE
            };
            if (eglChooseConfig(egl_dpy, cfg_attr, &cfg, 1, &n) && n >= 1)
                break;
            if (want <= 0) {
                fprintf(stderr, "eglChooseConfig found no OpenGL pbuffer config\n");
                return false;
            }
            fprintf(stderr, "no config with %dx MSAA, trying %d\n", want, want / 2);
            want /= 2;
        }
        if (want != msaa_samples)
            fprintf(stderr, "MSAA: asked %dx, got %dx\n", msaa_samples, want);
        msaa_samples = want;
        const EGLint pb_attr[] = { EGL_WIDTH, w, EGL_HEIGHT, h, EGL_NONE };
        egl_surf = eglCreatePbufferSurface(egl_dpy, cfg, pb_attr);
        if (egl_surf == EGL_NO_SURFACE) {
            fprintf(stderr, "eglCreatePbufferSurface failed (0x%x)\n", eglGetError());
            return false;
        }
        // Desktop GL, not GLES -- GDS3D uses fixed-function calls.
        if (!eglBindAPI(EGL_OPENGL_API)) {
            fprintf(stderr, "eglBindAPI(EGL_OPENGL_API) failed\n");
            return false;
        }
        egl_ctx = eglCreateContext(egl_dpy, cfg, EGL_NO_CONTEXT, NULL);
        if (egl_ctx == EGL_NO_CONTEXT) {
            fprintf(stderr, "eglCreateContext failed (0x%x)\n", eglGetError());
            return false;
        }
        if (!eglMakeCurrent(egl_dpy, egl_surf, egl_surf, egl_ctx)) {
            fprintf(stderr, "eglMakeCurrent failed (0x%x)\n", eglGetError());
            return false;
        }
        if (msaa_samples > 0) {
            glEnable(GL_MULTISAMPLE);      /* renderer.cpp leaves this commented out */
            GLint got = 0, bufs = 0;
            glGetIntegerv(GL_SAMPLES, &got);
            glGetIntegerv(GL_SAMPLE_BUFFERS, &bufs);
            fprintf(stderr, "MSAA enabled: GL_SAMPLES=%d GL_SAMPLE_BUFFERS=%d\n",
                    got, bufs);
        }
        fprintf(stderr, "GL renderer: %s\nGL version : %s\n",
                (const char *)glGetString(GL_RENDERER),
                (const char *)glGetString(GL_VERSION));
        return true;
    }

    bool write_ppm(const char *path, int w, int h)
    {
        std::vector<unsigned char> buf((size_t)w * h * 3);
        glPixelStorei(GL_PACK_ALIGNMENT, 1);
        glReadPixels(0, 0, w, h, GL_RGB, GL_UNSIGNED_BYTE, &buf[0]);
        FILE *f = fopen(path, "wb");
        if (!f) { fprintf(stderr, "cannot write %s\n", path); return false; }
        fprintf(f, "P6\n%d %d\n255\n", w, h);
        // GL origin is bottom-left; PPM is top-down.
        for (int y = h - 1; y >= 0; y--)
            fwrite(&buf[(size_t)y * w * 3], 1, (size_t)w * 3, f);
        fclose(f);
        return true;
    }

    /* Aim the camera at (tx,ty,0) from `dist`, for orientation (rx,ry).
       See the --egl-fit comment in main() for why this is the correct
       placement for GDS3D's free-flying camera. */
    static void aim(GDSParse_ogl *w, float rx, float ry,
                    float tx, float ty, float tz, float dist)
    {
        w->_rx = rx; w->_ry = ry;
        MATRIX4X4 mod, rot;
        mod.SetRotationAxis(ry, VECTOR3D(0.0f, 0.0f, 1.0f));
        rot.SetRotationAxis(rx, VECTOR3D(1.0f, 0.0f, 0.0f));
        mod = rot * mod;
        const GLfloat *m = (const GLfloat *)mod;
        w->_x = tx + dist * m[2];
        w->_y = ty + dist * m[6];
        w->_z = tz + dist * m[10];
    }

    /* WindowManager::draw() renders the world and THEN the 2D overlay:
       draw_info() (the grey info bar along the bottom) plus any ListView
       panels. Headless those come out as bare grey rectangles, because
       render_text is a no-op without an X font -- so --egl-no-ui skips the
       overlay entirely and calls the world's own draw. */
    void draw_world_only() { GDSParse_ogl *w = getWorld(); if (w) w->gl_draw(); }

    /* Box-filter rw x rh RGB down to w x h. Straight average of ssaa^2 samples
       per output pixel -- no weighting, which is what you want for a hard-edged
       CAD render: it is an exact area resample, not a blur. */
    static void downsample(const std::vector<unsigned char> &src, int rw, int rh,
                           std::vector<unsigned char> &dst, int w, int h, int n)
    {
        dst.resize((size_t)w * h * 3);
        const int nn = n * n;
        for (int y = 0; y < h; y++) {
            for (int x = 0; x < w; x++) {
                unsigned int acc[3] = {0, 0, 0};
                for (int dy = 0; dy < n; dy++) {
                    const unsigned char *row =
                        &src[((size_t)(y * n + dy) * rw + (size_t)x * n) * 3];
                    for (int dx = 0; dx < n; dx++) {
                        acc[0] += row[dx * 3 + 0];
                        acc[1] += row[dx * 3 + 1];
                        acc[2] += row[dx * 3 + 2];
                    }
                }
                unsigned char *o = &dst[((size_t)y * w + x) * 3];
                o[0] = (unsigned char)(acc[0] / nn);
                o[1] = (unsigned char)(acc[1] / nn);
                o[2] = (unsigned char)(acc[2] / nn);
            }
        }
    }

    void grab_rgb(std::vector<unsigned char> &buf, int w, int h)
    {
        buf.resize((size_t)w * h * 3);
        glPixelStorei(GL_PACK_ALIGNMENT, 1);
        glReadPixels(0, 0, w, h, GL_RGB, GL_UNSIGNED_BYTE, &buf[0]);
    }

    int main(int argc, char *argv[]);
};

int Wm_EGL::main(int argc, char *argv[])
{
    int w = 1600, h = 1200, frames = 3;
    const char *out = "gds3d.ppm";
    bool set_view = false, set_pos = false, set_zoom = false, fit = false;
    float rx = -60.0f, ry = 0.0f;      // rx=0 is straight down
    float px = 0, py = 0, pz = 0, zoom = 1.0f, margin = 1.15f;
    float tgt_x = 0, tgt_y = 0, tgt_z = 0, tgt_dist = 0, tgt_bx = 0, tgt_by = 0;
    float explode = 0.0f, seconds = 10.0f, spin = 360.0f;
    int fps = 30;
    const char *video = NULL;
    int crf = 26;
    const char *preset = "veryslow";
    /* DEFAULT ON. WindowManager::draw() paints draw_info() and the ListView
       panels over the scene, but render_text is a no-op without an X font, so
       headless they land as bare grey rectangles -- the info bar across the
       bottom being the obvious one. Offscreen output wants the world only.
       --egl-ui restores the overlay if you actually want the (textless) panels. */
    bool no_ui = true;
    bool probe = false;
    bool use_lod = false;
    int ssaa = 1;

    // Pull our own options out before handing the rest to the stock parser,
    // which prefix-matches with strncmp and would mis-read them.
    std::vector<char *> passthru;
    passthru.push_back(argv[0]);
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--egl-size") && i + 2 < argc) {
            w = atoi(argv[i + 1]); h = atoi(argv[i + 2]); i += 2;
        } else if (!strcmp(argv[i], "--egl-out") && i + 1 < argc) {
            out = argv[++i];
        } else if (!strcmp(argv[i], "--egl-frames") && i + 1 < argc) {
            frames = atoi(argv[++i]);
        } else if (!strcmp(argv[i], "--egl-view") && i + 2 < argc) {
            rx = (float)atof(argv[i + 1]); ry = (float)atof(argv[i + 2]);
            i += 2; set_view = true;
        } else if (!strcmp(argv[i], "--egl-pos") && i + 3 < argc) {
            px = (float)atof(argv[i + 1]); py = (float)atof(argv[i + 2]);
            pz = (float)atof(argv[i + 3]); i += 3; set_pos = true;
        } else if (!strcmp(argv[i], "--egl-zoom") && i + 1 < argc) {
            zoom = (float)atof(argv[++i]); set_zoom = true;
        } else if (!strcmp(argv[i], "--egl-fit")) {
            fit = true;
        } else if (!strcmp(argv[i], "--egl-margin") && i + 1 < argc) {
            margin = (float)atof(argv[++i]);
        } else if (!strcmp(argv[i], "--egl-no-ui")) {
            no_ui = true;               /* kept for symmetry; now the default */
        } else if (!strcmp(argv[i], "--egl-ui")) {
            no_ui = false;
        } else if (!strcmp(argv[i], "--egl-crf") && i + 1 < argc) {
            crf = atoi(argv[++i]);
        } else if (!strcmp(argv[i], "--egl-preset") && i + 1 < argc) {
            preset = argv[++i];
        } else if (!strcmp(argv[i], "--egl-lod")) {
            use_lod = true;
        } else if (!strcmp(argv[i], "--egl-probe")) {
            probe = true;
        } else if (!strcmp(argv[i], "--egl-msaa") && i + 1 < argc) {
            msaa_samples = atoi(argv[++i]);
        } else if (!strcmp(argv[i], "--egl-ssaa") && i + 1 < argc) {
            ssaa = atoi(argv[++i]);
        } else if (!strcmp(argv[i], "--egl-lod-fps") && i + 1 < argc) {
            fixed_fps = (float)atof(argv[++i]);
        } else if (!strcmp(argv[i], "--egl-explode") && i + 1 < argc) {
            explode = (float)atof(argv[++i]);
        } else if (!strcmp(argv[i], "--egl-video") && i + 1 < argc) {
            video = argv[++i];
        } else if (!strcmp(argv[i], "--egl-seconds") && i + 1 < argc) {
            seconds = (float)atof(argv[++i]);
        } else if (!strcmp(argv[i], "--egl-fps") && i + 1 < argc) {
            fps = atoi(argv[++i]);
        } else if (!strcmp(argv[i], "--egl-spin") && i + 1 < argc) {
            spin = (float)atof(argv[++i]);
        } else {
            passthru.push_back(argv[i]);
        }
    }
    if (w < 1 || h < 1) { fprintf(stderr, "bad --egl-size\n"); return 1; }
    if (ssaa < 1) ssaa = 1;

    /* SUPERSAMPLING. MSAA only antialiases polygon EDGES, and on llvmpipe the
       pbuffer resolve barely shows. Rendering at ssaa x and box-filtering down
       is driver independent, needs no FBO or blit, and -- unlike MSAA -- also
       cleans up dense interior detail (the packed metal lines), because every
       output pixel is an average of ssaa^2 real samples. Cost is ssaa^2 fill,
       which is the honest price on a software rasteriser. */
    const int rw = w * ssaa, rh = h * ssaa;
    if (ssaa > 1)
        fprintf(stderr, "SSAA %dx: rendering %dx%d -> %dx%d\n", ssaa, rw, rh, w, h);

    if (!egl_init(rw, rh))
        return 1;

    screenWidth = rw;
    screenHeight = rh;

    if (!commandLineParameters((int)passthru.size(), &passthru[0])) {
        fprintf(stderr, "commandLineParameters failed\n");
        return 1;
    }

    /* GDS3D culls objects against the frustum and drops detail based on the
       measured framerate. Both are fine interactively; for a deterministic
       offscreen render they make the output depend on how fast the software
       rasteriser happened to be, so turn visibility checking off. */
    visibility_checking = 0;

    /* DEFAULT ON for offscreen rendering: draw the whole database. GDS3D's
       LOD culls and alpha-fades layers by projected size, which silently drops
       real geometry (Metal5/Metal4 vanished at 1024x768 but not 640x480).
       --egl-lod restores the interactive behaviour. */
    gds3d_force_full_detail = !use_lod;

    resize(rw, rh);
    init();

    /* Exploded view FIRST, before the camera is fitted. exploded_fraction
       changes the geometry's Z extent, and the fit reads the emitted-vertex
       bounds -- so setting it afterwards leaves tgt_z at the unexploded centre
       and the raised stack drifts above frame centre and clips at the top.
       exploded_view/_fraction/_accel are globals from gdsobject_ogl.h; _accel
       stays 0 so the value holds instead of animating, and _view is true so the
       decay branch in gdsparse_ogl.cpp does not reset it. */
    if (explode > 0.0f) {
        exploded_view = true;
        exploded_fraction = explode;
        exploded_accel = 0.0f;
        fprintf(stderr, "exploded view: fraction %.2f\n", explode);
    }

    /* One warm-up draw BEFORE touching the camera. GDSObject_ogl's bounding box
       is populated during PrepareRender/RenderList, so querying GetBBox() ahead
       of the first draw returns an empty box and the fit silently falls back. */
    /* Re-enable AFTER init(): GDS3D's renderer init runs its own GL setup
       between our egl_init and the first draw, so enabling multisample only at
       context creation does not survive. Verified with glIsEnabled below. */
    if (msaa_samples > 0) {
        glEnable(GL_MULTISAMPLE);
        GLint smp = 0; glGetIntegerv(GL_SAMPLES, &smp);
        fprintf(stderr, "at draw time: GL_MULTISAMPLE=%d GL_SAMPLES=%d\n",
                (int)glIsEnabled(GL_MULTISAMPLE), smp);
    }

    /* SEVERAL warm-up draws, accumulating. GDS3D builds object geometry
       LAZILY -- the "Object ... created with N triangles" lines appear during
       rendering, not at load -- so a single draw emits only part of the design
       and the vertex bounds come out short, which then mis-frames the fit. The
       accumulator is reset once here and NOT between draws, because addVertex
       only runs at object-creation time: once a recipe is built later frames
       re-use it and emit nothing. */
    /* NOTE: do NOT park the camera far away for the warm-up draws. It looks
       like a way to get everything inside the frustum before fitting, but
       GDSObject_ogl::RenderList also applies a SCREEN-SPACE level of detail --
       it compares a projected size (zrel) against Quality -- so from far enough
       away every object is sub-pixel and detail is dropped instead of built.
       Measured: viewing from z=20000 silently lost Metal5 entirely and cut the
       emitted vertex count from 552k to 344k. Warm up from the default view. */
    gds3d_vmin[0] = gds3d_vmin[1] = gds3d_vmin[2] =  1e30f;
    gds3d_vmax[0] = gds3d_vmax[1] = gds3d_vmax[2] = -1e30f;
    gds3d_vcount = 0;
    for (int k = 0; k < 4; k++) { draw(); glFinish(); }

    // Camera. The default view is straight down (_rx = 0), which is just a
    // layout plot -- for anything that reads as 3D you want _rx around -50..-70.
    GDSParse_ogl *world = getWorld();
    if (world) {
        /* Capture the framing GDS3D chose for itself before we touch it. */
        const float def_x = world->_x, def_y = world->_y, def_z = world->_z;
        const float def_rx = world->_rx, def_ry = world->_ry;
        fprintf(stderr, "startup camera: pos=(%.2f, %.2f, %.2f) rx=%.2f ry=%.2f  "
                "bbox %.1f,%.1f .. %.1f,%.1f\n",
                def_x, def_y, def_z, world->_rx, world->_ry,
                world->_xmin, world->_ymin, world->_xmax, world->_ymax);
        if (set_view) { world->_rx = rx; world->_ry = ry; }
        if (set_pos)  { world->_x = px; world->_y = py; world->_z = pz; }
        if (set_zoom) { world->_z *= zoom; }

        /* --egl-fit: aim the camera at whatever the startup view was aimed at.

           GDS3D's camera is a FREE-FLYING FPS camera, not an orbit camera:
           (_x,_y,_z) is the camera POSITION, (_rx,_ry) its orientation. The
           movement code in gdsparse_ogl.cpp walks with

               _x -= mod[2]*speed;  _y -= mod[6]*speed;  _z -= mod[10]*speed;

           where mod = Rx(_rx) * Rz(_ry), so (mod[2],mod[6],mod[10]) is the
           forward row and the camera looks along MINUS it.

           THE STARTUP VIEW IS NOT TOP-DOWN. On the shipped example it comes up
           at rx=-32, ry=130.1 -- already tilted and yawed. Assuming rx=0 and
           treating (_x,_y) as the target puts the aim point tens of units off
           and renders empty substrate, which is what made earlier attempts
           black. So: trace the startup view ray down to z=0 to recover the
           point it was actually looking at, and use that. */
        /* Recover a target + framing distance.

           PREFERRED: the top cell's real 3D bounding box. GDSParse_ogl::_xmin
           .._ymax are NOT usable -- they come back 0.0 -- but
           GDSObject_ogl::GetBBox() returns a populated AA_BOUNDING_BOX with
           mins/maxes, which is what we actually want.

           Framing uses the BOUNDING SPHERE (half the box diagonal), not the
           box extents, because the camera orbits: a sphere is orientation
           independent, so the design cannot swing out of frame at some yaw
           angle the way a box-extent fit allows. dist = r / tan(fov/2) with the
           50 deg vertical FOV that gdsparse_ogl.cpp sets in SetPerspective.

           FALLBACK: if the box is degenerate, trace the startup view ray down
           to z=0 to recover the point it was looking at. Note the startup view
           is NOT top-down -- on the shipped example it is rx=-32, ry=130.1 --
           so assuming rx=0 and using (_x,_y) as the target is wrong and puts
           the design off screen. */
        /* Design bounds, for orbiting the middle of the design.

           USE GetTotalBoundary(), NOT GetBBox() and NOT _xmin/_xmax:
             * _xmin/_xmax on GDSParse_ogl are vestigial -- grep shows they are
               read in ui_highlight.cpp and never assigned, hence the 0.0s.
             * GetBBox() returns an AA_BOUNDING_BOX in the top cell's own frame;
               aiming at its centre (34.9,-35.3) pushed the design further off
               screen, so it is not the camera's world frame.
             * GetTotalBoundary() IS the world frame: buildSubstrate() feeds it
               straight into renderer.addVertex() for the substrate X/Y (only Z
               is scaled by _units), and the substrate visibly covers the design.

           The framing radius is the BOUNDING SPHERE of that box, because the
           camera orbits: a sphere is orientation independent, so the design
           cannot swing nearer and further -- which is exactly the constant
           zoom-out artefact that aiming at the wrong centre produced. */
        const bool spinning = (video != NULL) && (spin != 0.0f);
        const float rxq = set_view ? rx : world->_rx;
        const float ryq = set_view ? ry : world->_ry;
        fprintf(stderr, "EMITTED VERTICES: %lu   (%.2f, %.2f, %.2f) .. (%.2f, %.2f, %.2f)\n",
                gds3d_vcount, gds3d_vmin[0], gds3d_vmin[1], gds3d_vmin[2],
                gds3d_vmax[0], gds3d_vmax[1], gds3d_vmax[2]);
        /* Fit from the ACTUAL EMITTED VERTICES (renderer.cpp accumulates the
           min/max of every vertex handed to addVertex). Verified against
           GDSObject::GetTotalBoundary(): they agree to within the 5 % margin
           buildSubstrate() adds, which confirms both are in the same space --
           but the vertex bounds are the ground truth, they include Z, and they
           already account for the exploded view. Aiming at the Z centre matters
           once --egl-explode lifts the stack well off the substrate.

           Radius is the BOUNDING SPHERE so the framing cannot change as the
           camera orbits; dist = r / tan(fov/2) for the 50 deg vertical FOV set
           in gdsparse_ogl.cpp. */
        bool have_bbox = false;
        if (gds3d_vcount > 0 && gds3d_vmax[0] > gds3d_vmin[0]) {
            /* Explode is a RENDER-TIME transform, not a geometry rebuild --
               gdsobject_ogl.cpp translates each layer by
               1.5 * layer->Height * Unitu * exploded_fraction -- so the emitted
               vertex bounds never see it. Scale Z by (1 + fraction), which is
               exactly what GDS3D does to its own bounding boxes. Without this
               the target sits at the unexploded mid-height, the raised stack
               drifts above frame centre, and the top of the design clips. */
            float zscale = 1.0f + (explode > 0.0f ? explode : 0.0f);
            float zmin = gds3d_vmin[2] * zscale;
            float zmax = gds3d_vmax[2] * zscale;
            float dx = gds3d_vmax[0] - gds3d_vmin[0];
            float dy = gds3d_vmax[1] - gds3d_vmin[1];
            float dz = zmax - zmin;
            tgt_x = 0.5f * (gds3d_vmin[0] + gds3d_vmax[0]);
            tgt_y = 0.5f * (gds3d_vmin[1] + gds3d_vmax[1]);
            tgt_z = 0.5f * (zmin + zmax);
            /* FIT TO THE PROJECTED BOX, NOT A BOUNDING SPHERE.
               A cell is a thin plate (112 x 406 x 111 um here) and fills very
               little of its own enclosing sphere, so a sphere fit wasted ~70%
               of the frame. Instead solve for the smallest distance at which
               all 8 box corners stay inside the frustum.

               For a corner p, eye coords are R*p + (0,0,-d), so the NDC limits
               |(f/aspect)*ex / (d - rz)| <= 1 and |f*ey / (d - rz)| <= 1 give

                   d >= (f/aspect)*|ex| + rz     and     d >= f*|ey| + rz

               Taking the max over all corners is exact. Sweeping yaw as well
               keeps the scale CONSTANT through a spin -- fitting per frame
               would breathe in and out, which is worse than wasted margin. */
            const float fovy = 50.0f * 3.14159265f / 180.0f;
            const float fcot = 1.0f / tanf(fovy * 0.5f);
            const float aspect = (float)rw / (float)rh;
            float need = 0.0f;
            const int nyaw = spinning ? 72 : 1;
            for (int k = 0; k < nyaw; k++) {
                float yaw = spinning ? (360.0f * k / nyaw) : ryq;
                MATRIX4X4 mm, rr;
                mm.SetRotationAxis(yaw, VECTOR3D(0.0f, 0.0f, 1.0f));
                rr.SetRotationAxis(rxq, VECTOR3D(1.0f, 0.0f, 0.0f));
                mm = rr * mm;
                const GLfloat *M = (const GLfloat *)mm;
                for (int c = 0; c < 8; c++) {
                    float px = ((c & 1) ? gds3d_vmax[0] : gds3d_vmin[0]) - tgt_x;
                    float py = ((c & 2) ? gds3d_vmax[1] : gds3d_vmin[1]) - tgt_y;
                    float pz = ((c & 4) ? zmax : zmin) - tgt_z;
                    /* eye = M * p, with M column-major: row r is M[0*4+r],M[1*4+r],M[2*4+r] */
                    float ex = M[0]*px + M[4]*py + M[8]*pz;
                    float ey = M[1]*px + M[5]*py + M[9]*pz;
                    float rz = M[2]*px + M[6]*py + M[10]*pz;
                    float dx_need = (fcot / aspect) * fabsf(ex) + rz;
                    float dy_need = fcot * fabsf(ey) + rz;
                    if (dx_need > need) need = dx_need;
                    if (dy_need > need) need = dy_need;
                }
            }
            float r = 0.5f * sqrtf(dx * dx + dy * dy + dz * dz);   /* reported only */
            tgt_dist = need;
            have_bbox = true;
            fprintf(stderr, "fit from vertices: centre (%.1f, %.1f, %.1f)"
                    "  size %.1f x %.1f x %.1f  sphere r=%.1f (would give %.1f)"
                    "  projected-box dist=%.1f%s\n",
                    tgt_x, tgt_y, tgt_z, dx, dy, dz, r,
                    r / tanf(25.0f * 3.14159265f / 180.0f), tgt_dist,
                    spinning ? "  yaw-swept" : "");
        }
        if (!have_bbox) {
            MATRIX4X4 m0, r0;
            m0.SetRotationAxis(def_ry, VECTOR3D(0.0f, 0.0f, 1.0f));
            r0.SetRotationAxis(def_rx, VECTOR3D(1.0f, 0.0f, 0.0f));
            m0 = r0 * m0;
            const GLfloat *d = (const GLfloat *)m0;
            float t = (fabsf(d[10]) > 1e-6f) ? def_z / d[10] : def_z;
            tgt_x = def_x - t * d[2];
            tgt_y = def_y - t * d[6];
            tgt_z = 0.0f;
            tgt_dist = t;
            fprintf(stderr, "no vertices seen; fell back to startup view ray\n");
        }
        if (fit) {
            MATRIX4X4 mod, rot;
            mod.SetRotationAxis(world->_ry, VECTOR3D(0.0f, 0.0f, 1.0f));
            rot.SetRotationAxis(world->_rx, VECTOR3D(1.0f, 0.0f, 0.0f));
            mod = rot * mod;
            const GLfloat *m = (const GLfloat *)mod;
            float dist = tgt_dist * margin;
            world->_x = tgt_x + dist * m[2];
            world->_y = tgt_y + dist * m[6];
            world->_z = tgt_z + dist * m[10];
            fprintf(stderr, "fit: target (%.1f, %.1f, 0)  fwd (%.3f, %.3f, %.3f)"
                    "  dist %.1f\n", tgt_x, tgt_y, m[2], m[6], m[10], dist);
        }
    } else {
        fprintf(stderr, "warning: getWorld() is NULL, camera options ignored\n");
    }

    if (video) {
        /* ENCODE BY PIPING RAW RGB TO ffmpeg, not by linking libavcodec.
           libavcodec is present here, but using it means a codec context,
           AVFrame/AVPacket plumbing, swscale for RGB->YUV420 and a muxer --
           several hundred lines and a new link dependency -- for output
           identical to what four lines of pipe achieve. If you ever need to
           drop the ffmpeg binary dependency, that is the trade being made.

           -vf vflip because glReadPixels returns bottom-up rows. */
        int nframes = (int)(seconds * fps + 0.5f);
        char cmd[1024];
        /* ENCODER SETTINGS. crf 26 + preset veryslow, not the old crf 18:
           flat-shaded polygons on a black background compress extremely well,
           and at 1024x768 this gives ~4x smaller files for a mean per-pixel
           difference of 0.69 against crf 18 -- imperceptible, and small enough
           to embed as data URIs in a web page. -movflags +faststart puts the
           moov atom first so a browser can start playing before the whole file
           arrives. Override with --egl-crf / --egl-preset. */
        snprintf(cmd, sizeof(cmd),
                 "ffmpeg -y -loglevel error -f rawvideo -pix_fmt rgb24 "
                 "-s %dx%d -r %d -i - -vf vflip -c:v libx264 -preset %s "
                 "-pix_fmt yuv420p -crf %d -movflags +faststart %s",
                 w, h, fps, preset, crf, video);
        fprintf(stderr, "encoding: libx264 crf %d preset %s\n", crf, preset);
        FILE *pipe = popen(cmd, "w");
        if (!pipe) { fprintf(stderr, "cannot start ffmpeg\n"); return 1; }

        std::vector<unsigned char> buf, dsbuf;
        float ry0 = world ? world->_ry : 0.0f;
        for (int f = 0; f < nframes; f++) {
            float want_x = 0, want_y = 0, want_z = 0;
            if (world) {
                aim(world, world->_rx, ry0 + spin * (float)f / (float)nframes,
                    tgt_x, tgt_y, tgt_z, tgt_dist * margin);
                want_x = world->_x; want_y = world->_y; want_z = world->_z;
            }
            /* Two draws per frame: the first re-runs the camera/LOD update
               after the aim, the second renders with it settled. */
            if (no_ui) { draw_world_only(); glFinish(); draw_world_only(); }
            else       { draw(); glFinish(); draw(); }
            glFinish();
            grab_rgb(buf, rw, rh);
            if (ssaa > 1) { downsample(buf, rw, rh, dsbuf, w, h, ssaa); }
            std::vector<unsigned char> &outbuf = (ssaa > 1) ? dsbuf : buf;
            if (fwrite(&outbuf[0], 1, outbuf.size(), pipe) != outbuf.size()) {
                fprintf(stderr, "short write to ffmpeg at frame %d\n", f);
                pclose(pipe);
                return 1;
            }
            {
                static unsigned long prev = 0;
                if (gds3d_vcount != prev) {
                    fprintf(stderr, "frame %3d: +%lu verts (total %lu)  <-- geometry created mid-video\n",
                            f, gds3d_vcount - prev, gds3d_vcount);
                    prev = gds3d_vcount;
                }
            }
            if ((f % 75) == 0 && world)
                fprintf(stderr, "frame %3d AFTER draws  rx=%.1f ry=%.1f pos=(%.1f, %.1f, %.1f) "
                        "zfar=%.1f expl=%.2f\n", f, world->_rx, world->_ry,
                        world->_x, world->_y, world->_z, 0.0f, exploded_fraction),
                fprintf(stderr, "            aimed at pos=(%.1f, %.1f, %.1f)  drift=(%.2f, %.2f, %.2f)\n",
                        want_x, want_y, want_z,
                        world->_x-want_x, world->_y-want_y, world->_z-want_z);
        }
        int rc = pclose(pipe);
        fprintf(stderr, "\rwrote %s (%dx%d, %d frames @ %d fps, spin %.0f deg)%s\n",
                video, w, h, nframes, fps, spin,
                rc == 0 ? "" : "  [ffmpeg returned non-zero]");
        return rc == 0 ? 0 : 1;
    }

    for (int i = 0; i < frames; i++) {
        if (no_ui) draw_world_only(); else draw();
        glFinish();
    }

    if (world && probe) {
        /* WARNING: THIS READS STALE GL STATE. By the time control returns here
           the modelview is whatever the last overlay left behind -- measured as
           a pure translation of (_z, -_rx, -_ry), not the world view matrix --
           so the projected corners come out as an axis-aligned rectangle, which
           is impossible under a 135 deg yaw and is the tell that the matrix is
           wrong. Kept only as a diagnostic of that fact.
           To check framing properly, recompute view = Rx(_rx)*Rz(_ry)*T(-pos)
           and the 50 deg perspective by hand; doing that confirms the bounds
           centroid lands at (393.6, 326.1) in an 800x600 frame, i.e. centred. */
        GLdouble mv[16], pr[16];
        glGetDoublev(GL_MODELVIEW_MATRIX, mv);
        glGetDoublev(GL_PROJECTION_MATRIX, pr);
        GDSBB tb = world->_topcell->GetTotalBoundary();
        double cx[4] = { tb.min.X, tb.max.X, tb.max.X, tb.min.X };
        double cy[4] = { tb.min.Y, tb.min.Y, tb.max.Y, tb.max.Y };
        fprintf(stderr, "probe: frame %dx%d, centre (%d,%d)\n", w, h, w/2, h/2);
        fprintf(stderr, "  MODELVIEW (column-major):\n");
        for (int r = 0; r < 4; r++)
            fprintf(stderr, "    %8.3f %8.3f %8.3f %8.3f\n",
                    mv[0*4+r], mv[1*4+r], mv[2*4+r], mv[3*4+r]);
        fprintf(stderr, "  PROJECTION:\n");
        for (int r = 0; r < 4; r++)
            fprintf(stderr, "    %8.3f %8.3f %8.3f %8.3f\n",
                    pr[0*4+r], pr[1*4+r], pr[2*4+r], pr[3*4+r]);
        double sxsum = 0, sysum = 0;
        for (int k = 0; k < 4; k++) {
            double v[4] = { cx[k], cy[k], 0.0, 1.0 }, e[4], c[4];
            for (int r = 0; r < 4; r++)
                e[r] = mv[0*4+r]*v[0] + mv[1*4+r]*v[1] + mv[2*4+r]*v[2] + mv[3*4+r]*v[3];
            for (int r = 0; r < 4; r++)
                c[r] = pr[0*4+r]*e[0] + pr[1*4+r]*e[1] + pr[2*4+r]*e[2] + pr[3*4+r]*e[3];
            if (c[3] == 0.0) { fprintf(stderr, "  corner %d: w=0\n", k); continue; }
            double nx = c[0]/c[3], ny = c[1]/c[3];
            double sx = (nx*0.5+0.5)*w, sy = (1.0-(ny*0.5+0.5))*h;
            sxsum += sx; sysum += sy;
            fprintf(stderr, "  corner (%8.1f,%8.1f) -> screen (%8.1f,%8.1f)%s\n",
                    cx[k], cy[k], sx, sy,
                    (sx<0||sx>w||sy<0||sy>h) ? "  OFF-SCREEN" : "");
        }
        fprintf(stderr, "  bounds centroid on screen: (%.1f, %.1f)\n",
                sxsum/4.0, sysum/4.0);
    }
    if (world)
        fprintf(stderr, "at capture: rx=%.2f ry=%.2f pos=(%.2f, %.2f, %.2f)\n",
                world->_rx, world->_ry, world->_x, world->_y, world->_z);
    if (ssaa > 1) {
        std::vector<unsigned char> big, small_;
        grab_rgb(big, rw, rh);
        downsample(big, rw, rh, small_, w, h, ssaa);
        FILE *fp = fopen(out, "wb");
        if (!fp) { fprintf(stderr, "cannot write %s\n", out); return 1; }
        fprintf(fp, "P6\n%d %d\n255\n", w, h);
        for (int y = h - 1; y >= 0; y--)
            fwrite(&small_[(size_t)y * w * 3], 1, (size_t)w * 3, fp);
        fclose(fp);
        fprintf(stderr, "wrote %s (%dx%d, SSAA %dx)\n", out, w, h, ssaa);
        return 0;
    }
    if (!write_ppm(out, w, h))
        return 1;
    fprintf(stderr, "wrote %s (%dx%d, %d frames)\n", out, w, h, frames);
    return 0;
}

int main(int argc, char *argv[])
{
    Wm_EGL *root = new Wm_EGL();

    // MUST be set before commandLineParameters(). UI elements constructed
    // during GDSInit -- UIHighlight in particular -- call wm->new_timer()
    // through this global from their constructors, so leaving it NULL
    // segfaults inside GDSParse_ogl before control returns to us.
    // linux/main.cpp makes the same assignment in its own main().
    wm = root;

    int rc = root->main(argc, argv);
    delete root;
    return rc;
}
