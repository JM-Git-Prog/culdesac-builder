# build-headless.py - builds Maple Court with NO window: run by BUILD-MAPLE-COURT.bat via
#   blender.exe --background --python build-headless.py
# Renders six pictures and saves a .blend into a fresh renders\headless-<stamp>\ folder, and
# writes headless-log.txt there (last line DONE or FAILED). Nothing from earlier runs is overwritten.
import bpy, os, sys, time, traceback, io, contextlib

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "renders", "headless-" + time.strftime("%Y%m%d-%H%M"))
os.makedirs(OUT, exist_ok=True)
log = open(os.path.join(OUT, "headless-log.txt"), "w", encoding="utf-8")
t0 = time.time()
try:
    build = os.path.join(HERE, "build-culdesac-v1.py")
    ns = {"bpy": bpy, "__name__": "__main__", "GRASS_COUNT": 15000, "GRASS_CHILDREN": 16, "VIEW_MODE": "SOLID"}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile(open(build, encoding="utf-8").read(), build, "exec"), ns)
    log.write(buf.getvalue()); log.flush()
    sc = bpy.context.scene
    sc.eevee.taa_render_samples = 32
    for cam in ("Cam Aerial", "Cam Street", "Cam H1", "Cam H2", "Cam H3", "Cam H4"):
        t = time.time()
        sc.camera = bpy.data.objects[cam]
        sc.render.filepath = os.path.join(OUT, "maple-court-%s.png" % cam.split(" ")[1].lower())
        bpy.ops.render.render(write_still=True)
        log.write("render %-11s %5.1fs  %s\n" % (cam, time.time() - t, os.path.basename(sc.render.filepath))); log.flush()
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "maple-court.blend"))
    log.write("saved maple-court.blend\nDONE %.1fs total\n" % (time.time() - t0))
except Exception:
    log.write("FAILED\n" + traceback.format_exc())
    log.close()
    sys.exit(1)
log.close()
