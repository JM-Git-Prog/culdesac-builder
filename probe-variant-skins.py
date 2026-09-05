# probe-variant-skins.py - REPRODUCE the "exploded kit props" defect inside headless UPBGE, touching nothing.
#   blender.exe --background --factory-startup -noaudio --python probe-variant-skins.py -- <job folder>
# Builds the neighbourhood from <job>/brief.json exactly the way run-brief.py does (same exec, same
# namespace, same seed - the seed is the brief's checksum, so the same brief always picks the same
# skins), then inspects the scene instead of exporting it. Writes <job>/probe-variant-skins.txt.
#
# Two suspected mechanisms (2026-09-03, Fable), each printed with its evidence:
#   A  build-neighbourhood.py place(): when the randomly chosen main body is the aged/rust skin, the
#      SKIP filter for that word is switched off, so the CLEAN small parts (no word in their name)
#      pass too -> both cap/handle sets are parented under one anchor, 0.6-1.0 m apart.
#   B  run-brief.py drop_scatter_objects(): hides EVERY mesh with a geometry-nodes modifier. If the
#      rust trash-can body carries one, the body is hidden and left out of the GLB while its handles
#      stay -> handles floating with no can.
import bpy, os, sys, io, contextlib, time

HERE = os.path.dirname(os.path.abspath(__file__))
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
job = ARGS[0] if ARGS else os.path.join(HERE, "jobs", "20260903-155702")
out_path = os.path.join(job, "probe-variant-skins.txt")
lines = []
def say(s=""):
    print(s); lines.append(s)

say("PROBE variant skins  -  job %s  -  %s" % (job, time.strftime("%Y-%m-%d %H:%M:%S")))
build = os.path.join(HERE, "build-neighbourhood.py")
ns = {"bpy": bpy, "__name__": "__main__", "__file__": build, "BRIEF_PATH": os.path.join(job, "brief.json"),
      "GRASS_COUNT": 12000, "GRASS_CHILDREN": 12, "VIEW_MODE": "SOLID"}
t = time.time()
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    exec(compile(open(build, encoding="utf-8").read(), build, "exec"), ns)
say("built in %.1fs (build script's own output: %d lines)" % (time.time() - t, buf.getvalue().count("\n")))

TAGS = ("aged", "rust", "dead", "flattened", "geonodes", "twig")
def tags(name): return {w for w in TAGS if w in name.lower()}
def mods(o): return [m.type for m in o.modifiers]
def polys(o):
    try:
        dg = bpy.context.evaluated_depsgraph_get()
        return len(o.evaluated_get(dg).data.polygons)
    except Exception as e:
        return -1

defects = 0
for anchor in [o for o in bpy.data.objects if o.name.startswith(("fire_hydrant @", "metal_trash_can @"))]:
    kids = list(anchor.children)
    say("")
    say("ANCHOR %s  at %s  children=%d" % (anchor.name, tuple(round(v, 2) for v in anchor.location), len(kids)))
    body = None
    for k in sorted(kids, key=lambda k: k.name):
        nodes = "NODES" in mods(k)
        say("   %-40s tags=%-10s local=%s mods=%s polys=%d%s" % (
            k.name, sorted(tags(k.name)) or "-", tuple(round(v, 2) for v in k.location), mods(k) or "-", polys(k),
            "   (geometry-nodes modifier)" if nodes else ""))
        base = k.name.split(".")[0]
        if base in ("fire_hydrant", "fire_hydrant_aged", "metal_trash_can", "metal_trash_can_rust"):
            body = k
    # A: mixed variant tags among the small parts
    part_tagsets = {frozenset(tags(k.name)) for k in kids if k is not body}
    if len(part_tagsets) > 1:
        defects += 1
        say("   DEFECT A REPRODUCED: parts carry %d different skin tags under one anchor (main body: %s)" % (
            len(part_tagsets), body.name if body else "?"))
    else:
        say("   A ok: one skin among the parts")
    # B: would run-brief.py's scatter filter hide the body? Fixed rule (2026-09-03): NODES modifier
    # AND at least SCATTER_MIN_POLYS evaluated polygons. The old rule was NODES alone.
    SCATTER_MIN_POLYS = 100000
    if body is None:
        say("   (no body child found under this anchor)")
    elif "NODES" in mods(body) and polys(body) >= SCATTER_MIN_POLYS:
        defects += 1
        say("   DEFECT B REPRODUCED: body %s has a NODES modifier and %d polys - the scatter filter hides it" % (body.name, polys(body)))
    elif "NODES" in mods(body):
        say("   B ok (fixed rule): body %s has a NODES modifier but only %d polys - kept; the OLD rule would have hidden it" % (body.name, polys(body)))
    else:
        say("   B ok: body %s has no NODES modifier" % body.name)

say("")
say("SHELF ORIGINALS (the LIB collection) - modifiers per object:")
for name in ("fire_hydrant", "fire_hydrant_aged", "metal_trash_can", "metal_trash_can_rust", "metal_trash_can_lid", "metal_trash_can_rust_lid"):
    o = bpy.data.objects.get(name)
    say("   %-28s %s  polys=%s" % (name, (mods(o) or "-") if o else "MISSING", polys(o) if o else "-"))

say("")
say("RESULT: %s" % ("REPRODUCED - %d defect(s) present in the built scene" % defects if defects else "CLEAN - no defect in this build"))
open(out_path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
say("written: " + out_path)
