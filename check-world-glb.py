# check-world-glb.py - is every kit prop in this world GLB ONE skin, with its body present?
#   python check-world-glb.py <path-to-world.glb>
# Reads only the GLB's JSON chunk (12-byte header, then a length/type pair, then that many bytes of
# JSON - no library needed) and inspects every "<asset> @" anchor's children. Exit 0 = clean, 1 = defect.
import json, struct, sys, re, collections

TAGS = ("aged", "rust", "dead", "flattened", "geonodes", "twig")
BODIES = {"fire_hydrant", "fire_hydrant_aged", "metal_trash_can", "metal_trash_can_rust"}

def glb_json(path):
    with open(path, "rb") as f:
        head = f.read(12)
        if head[:4] != b"glTF": raise SystemExit("not a GLB: " + path)
        ln, ty = struct.unpack("<II", f.read(8))
        return json.loads(f.read(ln).decode("utf-8"))

def skin(name): return frozenset(t for t in TAGS if t in name.lower())
def core(name):
    n = re.sub(r"\.\d+$", "", name.lower())
    return re.sub(r"_?(%s)_?" % "|".join(TAGS), "_", n).replace("__", "_").strip("_")

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]   # works under plain python AND blender --python
path = ARGS[0]
if __import__("os").path.isdir(path):   # a place's world folder: check its HIGHEST version (what the viewer loads by default)
    import os
    vers = sorted((int(f.split("-")[0]), f) for f in os.listdir(path) if re.match(r"^\d+-world\.glb$", f))
    if not vers: raise SystemExit("no N-world.glb in " + path)
    path = os.path.join(path, vers[-1][1])
j = glb_json(path); nodes = j.get("nodes", [])
print("GLB %s  generator=%s  nodes=%d" % (path, j.get("asset", {}).get("generator", "?"), len(nodes)))
defects = 0; anchors = 0
for n in nodes:
    name = n.get("name", "")
    if not re.search(r" @(\.\d+)?$", name) or not n.get("children"): continue
    anchors += 1
    kids = [nodes[c].get("name", "") for c in n["children"]]
    # A: twins with different skins under one anchor
    by_core = collections.defaultdict(set)
    for k in kids: by_core[core(k)].add(skin(k))
    mixed = sorted(c for c, s in by_core.items() if len(s) > 1)
    # B: a hydrant / trash-can anchor must carry its body
    base = name.split(" @")[0]
    needs_body = base in ("fire_hydrant", "metal_trash_can")
    has_body = any(re.sub(r"\.\d+$", "", k) in BODIES for k in kids)
    if mixed:
        defects += 1
        print("  DEFECT A  %-24s two skins of: %s" % (name, ", ".join(mixed)))
    if needs_body and not has_body:
        defects += 1
        print("  DEFECT B  %-24s body missing; children: %s" % (name, ", ".join(sorted(kids))))
    if needs_body and not mixed and has_body:
        print("  ok        %-24s %s" % (name, ", ".join(sorted(kids))))
print("RESULT: %s  (%d anchors checked)" % ("CLEAN - one skin per prop, bodies present" if not defects else "%d DEFECT(S)" % defects, anchors))
sys.exit(1 if defects else 0)
