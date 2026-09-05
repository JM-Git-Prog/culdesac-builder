# run-brief.py - runs INSIDE headless UPBGE:  blender.exe --background --python run-brief.py -- <job folder>
# Reads <job>/brief.json, builds the neighbourhood, then:
#   1. exports it as a NEW place in THE world (CEO-3D-World/worlds/<slug>/ - mesh-only, the Starlite Diner shape)
#      so the V17 pane can walk it at http://localhost:5173/<slug>   (status.json: world_ready)
#   2. renders aerial + street pictures (the aerial doubles as the place's thumbnail)
#   3. saves neighbourhood.blend
# Writes <job>/status.json + build-log.txt as it goes. Never touches other jobs or existing world folders.
import bpy, os, sys, json, time, traceback, io, contextlib, re, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
WORLDS_CANDIDATES = [r"C:\Users\JohnM\Artificial Intelligence\Projects\CEO-of-My-Life-Inc\CEO-3D-World\worlds"]
WORLDS = next((p for p in WORLDS_CANDIDATES if os.path.isdir(p)), None)
MAX_TEX = 1024            # textures are shrunk to this before export so the GLB stays small enough to stream

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
job = ARGS[0] if ARGS else os.path.join(HERE, "jobs", "manual")
BASE_SLUG = ARGS[ARGS.index("--slug") + 1] if "--slug" in ARGS else None      # build as the next VERSION of this existing place
# --preview (2026-09-03, John: "pictures first, then I choose"): build the brief's houses as
# CANDIDATES, render one picture per house from its own camera, write nothing into the world.
# The pictures hang on the garage wall (the station kit); the chosen house is built for real.
PREVIEW = "--preview" in ARGS
os.makedirs(job, exist_ok=True)
status_path = os.path.join(job, "status.json")
log = open(os.path.join(job, "build-log.txt"), "w", encoding="utf-8")
STATE = {"status": "building", "stage": "build", "images": [], "world": None, "world_url": None, "world_ready": False}

def put(**kw):
    STATE.update(kw); STATE["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    json.dump(STATE, open(status_path, "w", encoding="utf-8"), indent=1)

def slugify(name):
    s = re.sub(r"[^a-z0-9]+", "-", (name or "neighbourhood").lower()).strip("-") or "neighbourhood"
    return s[:40]

def free_slug(base):
    """A NEW folder name - never reuses an existing place."""
    s, n = base, 1
    while os.path.exists(os.path.join(WORLDS, s)):
        n += 1; s = "%s-%d" % (base, n)
    return s

SCATTER_MIN_POLYS = 100000   # a scatter is hundreds of thousands of triangles; a kit prop body is a few thousand

def drop_scatter_objects():
    """Poly Haven packs carry geometry-nodes scatter objects (grass_bermuda's is 3.3M triangles on
    its own - 89% of the whole scene). They are render dressing, not walkable world: hide them so
    use_visible=True leaves them out of the GLB.
    2026-09-03 fix: decide by SIZE, not by the mere presence of a geometry-nodes modifier. The rust
    trash-can body (metal_trash_can_rust, 2,536 polys) carries a NODES modifier for its dents and was
    being hidden too - the GLB got its handles with no can under them (10 of 10 rust picks)."""
    n = 0
    dg = bpy.context.evaluated_depsgraph_get()
    for o in bpy.context.scene.objects:
        if o.type == 'MESH' and any(m.type == 'NODES' for m in o.modifiers):
            try: polys = len(o.evaluated_get(dg).data.polygons)
            except Exception: polys = SCATTER_MIN_POLYS      # cannot measure it: treat as scatter, as before
            if polys < SCATTER_MIN_POLYS:
                log.write("kept %s (%d polys, geometry-nodes but not a scatter)\n" % (o.name, polys)); continue
            o.hide_viewport = True; o.hide_render = True; n += 1
            try: o.hide_set(True)          # parked spare parts sit outside the view layer - hide_viewport already covers them
            except RuntimeError: pass
    return n

def _has_image(node, seen=None):
    seen = seen or set()
    if node.name in seen: return False
    seen.add(node.name)
    if node.type == 'TEX_IMAGE': return True
    return any(_has_image(l.from_node, seen) for i in node.inputs for l in i.links)

def flatten_procedurals():
    """glTF can't carry noise/ramp/bump node chains - the lawn exported WHITE (2026-09-02). For any
    Principled input fed by a chain with no image texture, drop the chain and use the material's
    plain colour instead. Image-backed chains (shelf textures, tints) are left alone."""
    n = 0
    for m in bpy.data.materials:
        if not m.use_nodes or not m.node_tree: continue
        b = next((nd for nd in m.node_tree.nodes if nd.type == 'BSDF_PRINCIPLED'), None)
        if b is None: continue
        for sock in ('Base Color', 'Normal', 'Roughness'):
            inp = b.inputs.get(sock)
            if inp is None or not inp.is_linked or _has_image(inp.links[0].from_node): continue
            for l in list(inp.links): m.node_tree.links.remove(l)
            if sock == 'Base Color': inp.default_value = tuple(m.diffuse_color)
            n += 1
    return n

def shrink_textures():
    n = 0
    for img in bpy.data.images:
        if not img.users:
            continue
        w, h = img.size
        if w > MAX_TEX or h > MAX_TEX:
            k = max(w, h) / float(MAX_TEX); img.scale(max(1, int(w / k)), max(1, int(h / k))); n += 1
    return n

def web_sky(shelf, sky_id):
    """The shelf holds 8k HDRIs (~100 MB) - far too big to stream. Make (once, cached next to the
    source, refreshed if the source is newer) a 2k Radiance .hdr (~6 MB) for the world."""
    import glob
    srcs = sorted(glob.glob(os.path.join(shelf, "hdris", sky_id, "*.hdr")))
    srcs = [s for s in srcs if not s.endswith("_web.hdr")]
    if not srcs: return None
    src = srcs[0]; dst = os.path.join(shelf, "hdris", sky_id, sky_id + "_2k_web.hdr")
    if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src): return dst
    img = bpy.data.images.load(src)            # a fresh datablock: the builder's own sky texture is left alone
    img.scale(2048, 1024)
    img.filepath_raw = dst; img.file_format = 'HDR'; img.save()
    bpy.data.images.remove(img)
    return dst

def sun_block(sky_key):
    """Where the builder's sun lamp actually points, as an engine (Y-up) position - one source of truth."""
    from mathutils import Vector
    so = bpy.data.objects.get("Sun")
    if so is None: return {}
    d = (so.matrix_world.to_3x3() @ Vector((0.0, 0.0, -1.0))).normalized()      # light travel direction, Blender Z-up
    pos = [-d.x * 80.0, -d.z * 80.0, d.y * 80.0]                                  # opposite the light, then (x, z, -y) -> glTF
    warm = sky_key == "sunset"
    return {"position": [round(v, 2) for v in pos], "intensity": 2.0 if warm else {"clear": 3.2, "cloudy": 1.6, "overcast": 0.9}.get(sky_key, 3.0),
            "color": "#ffb070" if warm else "#fff3df"}

def export_world(brief, houses, shelf=None, sky_id=None, sky_key="clear"):
    if WORLDS is None:
        raise RuntimeError("THE world's folder was not found. Looked in: " + " | ".join(WORLDS_CANDIDATES))
    name = brief.get("name") or "New Neighbourhood"
    if BASE_SLUG:
        # a REVISION: the next version index inside the existing place - earlier versions stay on disk untouched
        slug = BASE_SLUG
        out = os.path.join(WORLDS, slug, "output", "world")
        if not os.path.isdir(out): raise RuntimeError("no such place to build on: " + slug)
        taken = [int(f.split("-")[0]) for f in os.listdir(out) if re.match(r"^\d+-world\.(glb|json)$", f)]
        ver = (max(taken) + 1) if taken else 0
    else:
        slug = free_slug(slugify(name)); out = os.path.join(WORLDS, slug, "output", "world"); ver = 0
    V = "%d-world" % ver
    log.write("place %s version %d\n" % (slug, ver))
    log.write("dropped %d geometry-nodes scatter objects from the export\n" % drop_scatter_objects())
    log.write("flattened %d procedural material inputs to plain colour\n" % flatten_procedurals())
    t = time.time(); n = shrink_textures(); log.write("shrunk %d textures to <=%dpx in %.1fs\n" % (n, MAX_TEX, time.time() - t)); log.flush()
    glb = os.path.join(out, V + ".glb")
    if os.path.exists(glb): raise RuntimeError("refusing to overwrite " + glb)
    os.makedirs(out, exist_ok=True)
    t = time.time()
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            bpy.ops.export_scene.gltf(filepath=glb, export_format='GLB', export_apply=True, use_visible=True,
                                      export_materials='EXPORT', export_image_format='JPEG', export_jpeg_quality=80,   # JPEG: 16-bit PNG normal maps were 6 MB EACH (154 of 163 MB); alpha images stay PNG
                                      export_lights=False, export_cameras=False, export_animations=False, export_skins=False,
                                      export_yup=True, export_extras=True)      # extras = the interact tags (door hinges, switches)
    except Exception:
        if not BASE_SLUG and not os.listdir(out): os.removedirs(out)     # only the empty folders this run just made
        raise
    mb = os.path.getsize(glb) / 1e6
    log.write("exported %s  %.1f MB in %.1fs\n" % (glb, mb, time.time() - t)); log.flush()
    # the sky the sentence asked for, as a 2k HDRI beside the mesh (the engine's OutdoorSky reads it)
    sky_url = ""
    if shelf and sky_id:
        try:
            t = time.time(); web = web_sky(shelf, sky_id)
            if web:
                shutil.copyfile(web, os.path.join(out, V + "-sky.hdr"))
                sky_url = "/worlds/%s/output/world/%s-sky.hdr" % (slug, V)
                log.write("sky %s -> %s-sky.hdr (%.1f MB) in %.1fs\n" % (sky_id, V, os.path.getsize(web) / 1e6, time.time() - t))
        except Exception as e:
            log.write("sky skipped: %s\n" % e)
    environment = {"kind": "outdoor", "sky": sky_key if sky_key in ("clear", "cloudy", "sunset", "overcast") else "clear",
                   "sky_url": sky_url, "sun": sun_block(sky_key),
                   "spawn": [0.0, 1.7, 0.0], "look_at": [0.0, 1.6, -10.0], "controller": "walk",
                   "_note": "DATA the chat writes: sky/sun/spawn/controls. Read by app/src/modules/environment/outdoor.ts."}
    manifest = {
        "_note": "Composed by the Neighbourhood Builder (UPBGE 0.50 headless, run-brief.py) from the sentence in brief.json - "
                 "mesh only, the Starlite Diner shape: the dev server's worlds plugin binds the NEWEST indexed world "
                 "manifest and its matching GLB - NOT 0-world.glb by filename convention (see app/vite.config.ts, "
                 "readWorldManifest -> latestIndexedFile); no splat exists, so the GLB's own materials render "
                 "(showRealMaterial). Origin is on the road looking toward the bulb; ground top is y=0. "
                 "[Corrected 2026-09-05: this note claimed the viewer binds 0-world.glb by filename convention. That was "
                 "false, and because it is stamped into EVERY generated world.json it had already misled a reader into "
                 "believing John had been looking at version 0 of his neighbourhood while versions 1-3 sat beside it. "
                 "It was stale Starlite boilerplate that nobody had ever checked against the viewer code.]",
        "display_name": name, "world_id": "neighbourhood-%s-v%d" % (slug, ver), "model": "neighbourhood-builder", "version": ver,
        "brief": brief, "houses": houses, "environment": environment,
        "assets": {"splats": {"spz_urls": {}, "semantics_metadata": {"metric_scale_factor": 1, "ground_plane_offset": 0, "flip_y": False}},
                   "mesh": {"collider_mesh_url": "local: %s.glb (%.1f MB, visible geometry AND walkable collider)" % (V, mb)},
                   "imagery": {"pano_url": ""}, "thumbnail_url": ""}}
    json.dump(manifest, open(os.path.join(out, V + ".json"), "w", encoding="utf-8"), indent=2)
    # project.json LAST - it is the discovery gate, so the world never sees a half-written place.
    # A revision leaves the existing project.json alone (it is John's place already).
    pj = os.path.join(WORLDS, slug, "project.json")
    if not os.path.exists(pj):
        json.dump({"schema_version": 1, "slug": slug, "display_name": name,
                   "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "notes": "built from: " + str(brief.get("request", ""))},
                  open(pj, "w", encoding="utf-8"), indent=2)
    return slug, out, mb, ver

t0 = time.time()
put(status="building", stage="build")
try:
    build = os.path.join(HERE, "build-neighbourhood.py")
    ns = {"bpy": bpy, "__name__": "__main__", "__file__": build, "BRIEF_PATH": os.path.join(job, "brief.json"),
          "GRASS_COUNT": 12000, "GRASS_CHILDREN": 12, "VIEW_MODE": "SOLID"}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile(open(build, encoding="utf-8").read(), build, "exec"), ns)
    log.write(buf.getvalue()); log.flush()
    houses = ns.get("HOUSES", [])
    fallbacks = ns.get("FALLBACKS", [])
    unbuilt = ns.get("UNBUILT", [])          # decision 23: every asked-for phrase the builder could not make - [{"house", "phrase"}]
    placed = ns.get("PLACED", [])            # warehouse GLBs that were stood at anchors
    brief = json.load(open(os.path.join(job, "brief.json"), encoding="utf-8"))
    summary = [{"name": h["name"], "style": h["spec"]["style"], "stories": h["spec"]["stories"], "wall": h["spec"]["wall"], "color": h["spec"]["color"],
                "roof": h["spec"]["roof_mat"], "garage": h["spec"]["garage"] or "none", "porch": h["spec"]["porch"],
                "features_built": h.get("features_built", [])} for h in houses]

    if PREVIEW:
        # candidates only: one picture per house from its own camera; the world is not touched
        sc = bpy.context.scene
        sc.eevee.taa_render_samples = 24
        sc.render.resolution_x = 1280; sc.render.resolution_y = 960
        cands = []
        for i, h in enumerate(houses):
            t = time.time()
            sc.camera = bpy.data.objects["Cam " + h["name"]]
            name = "candidate-%d.png" % (i + 1)
            sc.render.filepath = os.path.join(job, name)
            bpy.ops.render.render(write_still=True)
            # THE PICTURE IS A PROMISE (2026-09-05). Carry the RESOLVED width and depth of the house
            # actually rendered into the candidate record, so choosing it builds THAT house. W and D
            # are drawn per brief (rnd.uniform in norm_house) and the column count follows the width -
            # so identical words gave SIX columns as candidate 1 of 3 and FOUR as house 8 of 8. Same
            # house, different draw. Now the draw travels with the choice instead of being re-rolled.
            chosen = dict(brief["houses"][i]) if i < len(brief.get("houses", [])) else {}
            if chosen:
                chosen["W"] = round(h["spec"]["W"], 3); chosen["D"] = round(h["spec"]["D"], 3)
            cands.append({"tag": "c%d" % (i + 1), "image": os.path.join(job, name), "house": chosen, "summary": summary[i]})
            log.write("render candidate %d (%s) %5.1fs\n" % (i + 1, h["name"], time.time() - t)); log.flush()
            put(stage="picture %d/%d" % (i + 1, len(houses)), images=[c["image"] for c in cands])
        log.write("PREVIEW DONE %.1fs\n" % (time.time() - t0)); log.close()
        put(status="done", stage="done", preview=True, candidates=cands, houses=summary, fallbacks=fallbacks, unbuilt_features=unbuilt, placed=placed,
            images=[os.path.basename(c["image"]) for c in cands], seconds=round(time.time() - t0, 1))
        sys.exit(0)

    put(stage="handing the place to your world", houses=summary, fallbacks=fallbacks, unbuilt_features=unbuilt, placed=placed)
    slug, out, mb, ver = export_world(brief, summary, shelf=ns.get("SHELF"), sky_id=ns.get("sky_id"), sky_key=str(ns.get("sky_key", "clear")))
    put(stage="world ready - rendering pictures", world=slug, world_url="/%s?v=%d" % (slug, ver), version=ver, world_ready=True, glb_mb=round(mb, 1),
        world_seconds=round(time.time() - t0, 1))

    sc = bpy.context.scene
    sc.eevee.taa_render_samples = 24
    images = []
    for i, cam in enumerate(["Cam Aerial", "Cam Street"]):
        t = time.time()
        sc.camera = bpy.data.objects[cam]
        name = "%s.png" % cam.replace("Cam ", "").lower()
        sc.render.filepath = os.path.join(job, name)
        bpy.ops.render.render(write_still=True)
        images.append(name)
        log.write("render %-11s %5.1fs\n" % (cam, time.time() - t)); log.flush()
        if cam == "Cam Aerial":
            shutil.copyfile(os.path.join(job, name), os.path.join(out, "%d-world-thumbnail.png" % ver))
        put(stage="render %d/2" % (i + 1), images=images)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(job, "neighbourhood.blend"))
    log.write("DONE %.1fs\n" % (time.time() - t0)); log.close()
    put(status="done", stage="done", images=images, unbuilt_features=unbuilt, placed=placed, seconds=round(time.time() - t0, 1))
except Exception:
    err = traceback.format_exc()
    log.write("FAILED\n" + err); log.close()
    put(status="failed", stage="failed", error=err[-2000:])
    sys.exit(1)
