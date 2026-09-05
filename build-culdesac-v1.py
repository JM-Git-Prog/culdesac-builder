# build-culdesac-v1.py - "Maple Court": a four-house cul-de-sac, built inside UPBGE 0.50 through the
# Claude Bridge from the CC0 starter shelf (Poly Haven textures + models). Draft v1, 2026-09-02.
# Run from chat via:  exec(open(THIS_FILE, encoding="utf-8").read(), {"bpy": bpy, "__name__": "__main__"})
import bpy, bmesh, math, json, os, glob, random, time
from mathutils import Vector, Matrix

SHELF = r"E:\Software Development\Video Game Development\02 Asset Shelf\Landing\polyhaven"
OUT = r"E:\Software Development\Video Game Development\03 Projects\Cul-de-sac"
os.makedirs(OUT, exist_ok=True)
sc = bpy.context.scene
rnd = random.Random(7)
T0 = time.time()
# staged build switches (set in the calling namespace before exec): the first run froze UPBGE at render
WANT_MODELS = globals().get("WANT_MODELS", True)     # shelf models (trees, props)
WANT_GRASS = globals().get("WANT_GRASS", True)       # hair grass on the lawn
GRASS_COUNT = globals().get("GRASS_COUNT", 8000)
GRASS_CHILDREN = globals().get("GRASS_CHILDREN", 12)

# ---------------------------------------------------------------- wipe the scene, keep the bridge
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
for c in list(bpy.data.collections):
    bpy.data.collections.remove(c)
for blk in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.textures, bpy.data.particles,
            bpy.data.lights, bpy.data.cameras, bpy.data.node_groups):
    for d in list(blk):
        if d.users == 0:
            blk.remove(d)
COL = bpy.data.collections.new("Maple Court"); sc.collection.children.link(COL)
LIB = bpy.data.collections.new("Library"); sc.collection.children.link(LIB)
sc.view_layers[0].layer_collection.children["Library"].exclude = True

# ---------------------------------------------------------------- materials from the shelf
_mats = {}

def shelf_mat(asset):
    """Append the Poly Haven material for <asset>; returns (material, tile_size_m)."""
    if asset in _mats:
        return _mats[asset]
    d = os.path.join(SHELF, "textures", asset)
    blend = sorted(glob.glob(os.path.join(d, "*.blend")))[0]
    dims = json.load(open(os.path.join(d, "asset.json"), encoding="utf-8")).get("dimensions_mm") or [2000, 2000]
    tile = max(0.25, float(dims[0]) / 1000.0)
    with bpy.data.libraries.load(blend, link=False) as (df, dt):
        dt.materials = list(df.materials)
    m = [x for x in dt.materials if x][0]
    m.name = "PH " + asset
    for n in m.node_tree.nodes:
        if n.type == 'MAPPING':
            n.inputs['Scale'].default_value = (1, 1, 1)
    _mats[asset] = (m, tile)
    return _mats[asset]

def solid(name, rgb, rough=0.5, metal=0.0, emit=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs['Base Color'].default_value = (*rgb, 1); b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    if emit:
        b.inputs['Emission Color'].default_value = (*rgb, 1); b.inputs['Emission Strength'].default_value = emit
    m.diffuse_color = (*rgb, 1)
    return (m, 1.0)

def lawn_mat():
    """Procedural lawn: two greens through noise + fine bump. No tiling, no texture needed."""
    m = bpy.data.materials.new("Lawn Green"); m.use_nodes = True
    nt = m.node_tree; b = nt.nodes["Principled BSDF"]
    b.inputs['Roughness'].default_value = 0.9
    tc = nt.nodes.new('ShaderNodeTexCoord'); nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = 0.35; nz.inputs['Detail'].default_value = 10.0; nz.inputs['Roughness'].default_value = 0.65
    cr = nt.nodes.new('ShaderNodeValToRGB'); e = cr.color_ramp.elements
    e[0].position = 0.35; e[0].color = (0.09, 0.26, 0.05, 1); e[1].position = 0.7; e[1].color = (0.24, 0.42, 0.10, 1)
    fine = nt.nodes.new('ShaderNodeTexNoise'); fine.inputs['Scale'].default_value = 40.0; fine.inputs['Detail'].default_value = 8.0
    bp = nt.nodes.new('ShaderNodeBump'); bp.inputs['Strength'].default_value = 0.3
    nt.links.new(tc.outputs['Object'], nz.inputs['Vector']); nt.links.new(tc.outputs['Object'], fine.inputs['Vector'])
    nt.links.new(nz.outputs['Fac'], cr.inputs['Fac']); nt.links.new(cr.outputs['Color'], b.inputs['Base Color'])
    nt.links.new(fine.outputs['Fac'], bp.inputs['Height']); nt.links.new(bp.outputs['Normal'], b.inputs['Normal'])
    m.diffuse_color = (0.18, 0.36, 0.08, 1)
    return (m, 1.0)

GLASS = solid("Glass", (0.05, 0.08, 0.12), 0.05)
STEEL = solid("Steel", (0.35, 0.36, 0.38), 0.35, 1.0)
LAMP_GLOW = solid("Lamp Glow", (1.0, 0.85, 0.6), 0.3, 0.0, 6.0)
ASPHALT = shelf_mat("asphalt_01")
CONCRETE = shelf_mat("brushed_concrete_03")
CURB = shelf_mat("brushed_concrete")
DRIVE = shelf_mat("brushed_concrete_04")
PATH = shelf_mat("cobblestone_02")
GRASS = lawn_mat()
GRAVEL = shelf_mat("bicolour_gravel")

# ---------------------------------------------------------------- geometry helpers (box-projected UVs in local space)
def box_uv(bm, tile):
    uv = bm.loops.layers.uv.verify()
    bm.normal_update()
    for f in bm.faces:
        n = f.normal; ax = max(range(3), key=lambda i: abs(n[i]))
        for l in f.loops:
            c = l.vert.co
            u, v = ((c.y, c.z), (c.x, c.z), (c.x, c.y))[ax]     # x-facing -> (y,z); y-facing -> (x,z); z-facing -> (x,y)
            l[uv].uv = (u / tile, v / tile)

def finish(name, bm, mt, xform=None, smooth=False, col=None):
    m, tile = mt
    box_uv(bm, tile)
    if xform is not None:
        bmesh.ops.transform(bm, matrix=xform, verts=bm.verts)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    if smooth: me.shade_smooth()
    ob = bpy.data.objects.new(name, me); (col or COL).objects.link(ob)
    if m: me.materials.append(m)
    return ob

def cube_into(bm, center, size, rot_z=0.0):
    r = bmesh.ops.create_cube(bm, size=1.0)
    M = Matrix.Translation(center) @ Matrix.Rotation(rot_z, 4, 'Z') @ Matrix.Diagonal((*size, 1))
    bmesh.ops.transform(bm, matrix=M, verts=r['verts'])
    return r['verts']

def box(name, center, size, mt, xform=None, rot_z=0.0):
    bm = bmesh.new(); cube_into(bm, center, size, rot_z); return finish(name, bm, mt, xform)

def disc(name, center, r, h, mt, segs=64):
    bm = bmesh.new()
    res = bmesh.ops.create_cone(bm, cap_ends=True, segments=segs, radius1=r, radius2=r, depth=h)
    bmesh.ops.translate(bm, vec=(center[0], center[1], center[2] + h / 2), verts=res['verts'])
    return finish(name, bm, mt)

def ring(name, center, r1, r2, a0, a1, h, mt, segs=48):
    """Flat ring sector between radii r1..r2 from angle a0..a1 (degrees), extruded h upward."""
    bm = bmesh.new()
    inner, outer = [], []
    for i in range(segs + 1):
        a = math.radians(a0 + (a1 - a0) * i / segs)
        inner.append(bm.verts.new((center[0] + r1 * math.cos(a), center[1] + r1 * math.sin(a), center[2])))
        outer.append(bm.verts.new((center[0] + r2 * math.cos(a), center[1] + r2 * math.sin(a), center[2])))
    for i in range(segs):
        bm.faces.new((inner[i], outer[i], outer[i + 1], inner[i + 1]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.normal_update()
    if bm.faces[0].normal.z < 0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
    ob = finish(name, bm, mt)
    s = ob.modifiers.new("Height", 'SOLIDIFY'); s.thickness = h; s.offset = 1.0
    return ob

def prism(name, W, D, z0, hh, mt, xform, overhang=0.5, cx=0.0, cy=0.0):
    """Gable roof, ridge along local X, centred on (cx, cy)."""
    bm = bmesh.new(); w, d = W / 2 + overhang, D / 2 + overhang
    v = [bm.verts.new((cx + p[0], cy + p[1], p[2])) for p in
         [(-w, -d, z0), (w, -d, z0), (w, d, z0), (-w, d, z0), (-w, 0, z0 + hh), (w, 0, z0 + hh)]]
    for f in [(0, 1, 2, 3), (0, 1, 5, 4), (3, 2, 5, 4), (0, 4, 3), (1, 2, 5)]:
        bm.faces.new([v[i] for i in f])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = finish(name, bm, mt, xform)
    s = ob.modifiers.new("Thickness", 'SOLIDIFY'); s.thickness = 0.12; s.offset = 1.0
    return ob

def hip(name, W, D, z0, hh, mt, xform, overhang=0.5):
    bm = bmesh.new(); w, d = W / 2 + overhang, D / 2 + overhang
    rl = max(0.0, (w - d))     # ridge half-length
    v = [bm.verts.new(p) for p in [(-w, -d, z0), (w, -d, z0), (w, d, z0), (-w, d, z0), (-rl, 0, z0 + hh), (rl, 0, z0 + hh)]]
    for f in [(0, 1, 2, 3), (0, 1, 5, 4), (3, 2, 5, 4), (0, 4, 3), (1, 2, 5)]:
        bm.faces.new([v[i] for i in f])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = finish(name, bm, mt, xform)
    s = ob.modifiers.new("Thickness", 'SOLIDIFY'); s.thickness = 0.12; s.offset = 1.0
    return ob

def cyl(name, center, r, h, mt, xform=None, segs=16):
    bm = bmesh.new()
    res = bmesh.ops.create_cone(bm, cap_ends=True, segments=segs, radius1=r, radius2=r, depth=h)
    bmesh.ops.translate(bm, vec=(center[0], center[1], center[2] + h / 2), verts=res['verts'])
    return finish(name, bm, mt, xform, smooth=True)

# ---------------------------------------------------------------- models from the shelf
_groups = {}

def shelf_model(asset):
    """Append every object of a Poly Haven model into the hidden Library; returns (objects, dims_m)."""
    if asset in _groups:
        return _groups[asset]
    d = os.path.join(SHELF, "models", asset)
    blend = sorted(glob.glob(os.path.join(d, "*.blend")))[0]
    dims = json.load(open(os.path.join(d, "asset.json"), encoding="utf-8")).get("dimensions_mm") or [1000, 1000, 1000]
    with bpy.data.libraries.load(blend, link=False) as (df, dt):
        dt.objects = list(df.objects)
    obs = [o for o in dt.objects if o]
    for o in obs:
        LIB.objects.link(o)
    _groups[asset] = (obs, [float(x) / 1000.0 for x in dims])
    return _groups[asset]

def place(asset, pos, yaw_deg=None, height=None, scale=None, lod="LOD1"):
    """Instance ONE variant of a shelf model. Poly Haven packs ship several variants (a/b/c) each with
    LOD0/1/2 meshes - the first build copied all 47 objects of a fir tree per placement (39 M triangles)."""
    obs, dims = shelf_model(asset)
    s = scale if scale else ((height / dims[2]) if height else 1.0)
    yaw = math.radians(yaw_deg if yaw_deg is not None else rnd.uniform(0, 360))
    root = bpy.data.objects.new(asset + " @", None); COL.objects.link(root)
    root.location = pos; root.rotation_euler = (0, 0, yaw); root.scale = (s, s, s)
    meshes = [o for o in obs if o.type == 'MESH']
    if any("LOD" in o.name for o in meshes):
        pool = [o for o in meshes if lod in o.name] or [o for o in meshes if "LOD0" in o.name] or [o for o in meshes if "LOD" not in o.name]
    else:
        pool = meshes
    # A pack = alternates (a/b/c, all big) + parts (wheels) + loose source pieces parked off to the side (twig tips).
    vol = lambda o: max(1e-9, o.dimensions.x * o.dimensions.y * o.dimensions.z)
    biggest = max(pool, key=vol)
    alts = [o for o in pool if vol(o) >= 0.5 * vol(biggest)]
    main = rnd.choice(alts)
    centre = main.matrix_world @ (sum((Vector(b) for b in main.bound_box), Vector()) / 8)
    reach = max(main.dimensions) * 0.75
    SKIP = ("aged", "rust", "dead", "flattened", "geonodes", "twig")        # alternate finishes / scatter pieces
    parts = [o for o in pool if o not in alts and vol(o) < 0.1 * vol(biggest)
             and (o.matrix_world.translation - centre).length <= reach
             and not any(t in o.name.lower() for t in SKIP if t not in main.name.lower())]
    if len(pool) > 12:                       # a scatter set (grass, flowers): one clump, no pile of pieces
        parts = []
    origin = main.matrix_world.translation.copy()
    for o in [main] + parts:
        c = o.copy(); COL.objects.link(c); c.parent = root
        c.location = c.location - origin                      # the variant sits at the root, wherever it was parked
        c.hide_render = False; c.hide_viewport = False        # Poly Haven ships LOD1/LOD2 hidden
        try: c.hide_set(False)
        except Exception: pass
    return root

# ---------------------------------------------------------------- the house builder
def house(hn, pos, yaw_deg, W, D, stories, roof, wall_tex, roof_tex, trim_rgb, garage, chimney=True, porch=False):
    yaw = math.radians(yaw_deg)
    X = Matrix.Translation(Vector(pos)) @ Matrix.Rotation(yaw, 4, 'Z')
    H = 2.9 * stories
    WALL = shelf_mat(wall_tex); ROOF = shelf_mat(roof_tex)
    TRIM = solid("Trim " + hn, trim_rgb, 0.4)
    FOUND = CONCRETE

    box(hn + " Foundation", (0, 0, 0.2), (W + 0.3, D + 0.3, 0.4), FOUND, X)
    walls = box(hn + " Walls", (0, 0, 0.4 + H / 2), (W, D, H), WALL, X)

    # openings: front door + windows on every face, per story
    cut = bmesh.new()
    door_x = -W / 4 if garage != 'L' else W / 4
    cube_into(cut, (door_x, -D / 2, 0.4 + 1.05), (1.0, 0.4, 2.1))
    wins = []      # (x, y, z, axis, sign)
    for s in range(stories):
        z = 0.4 + 1.7 + 2.9 * s
        n = max(2, int(W // 2.6))
        for i in range(n):
            x = -W / 2 + W * (i + 0.5) / n
            if s == 0 and abs(x - door_x) < 1.3:
                continue
            wins.append((x, -D / 2, z, 'y', -1))
            wins.append((x, D / 2, z, 'y', 1))
        m = max(1, int(D // 3.0))
        for i in range(m):
            y = -D / 2 + D * (i + 0.5) / m
            if garage != 'R' or s > 0:
                wins.append((W / 2, y, z, 'x', 1))
            if garage != 'L' or s > 0:
                wins.append((-W / 2, y, z, 'x', -1))
    for (x, y, z, ax, sg) in wins:
        cube_into(cut, (x, y, z), (1.2, 0.4, 1.3) if ax == 'y' else (0.4, 1.2, 1.3))
    cutter = finish(hn + " Cutters", cut, TRIM, X)
    cutter.display_type = 'WIRE'; cutter.hide_render = True; cutter.hide_set(True)
    mod = walls.modifiers.new("Openings", 'BOOLEAN'); mod.operation = 'DIFFERENCE'; mod.object = cutter; mod.solver = 'EXACT'

    for i, (x, y, z, ax, sg) in enumerate(wins):
        if ax == 'y':
            d = lambda off: (x, y + sg * off, z)
            box(hn + " WF%d" % i, d(-0.12), (1.30, 0.06, 1.40), TRIM, X)
            box(hn + " WG%d" % i, d(-0.06), (1.16, 0.03, 1.26), GLASS, X)
            box(hn + " WM%d" % i, d(-0.03), (0.04, 0.02, 1.26), TRIM, X)
            box(hn + " WS%d" % i, (x, y + sg * 0.04, z - 0.7), (1.40, 0.18, 0.06), TRIM, X)
        else:
            d = lambda off: (x + sg * off, y, z)
            box(hn + " WF%d" % i, d(-0.12), (0.06, 1.30, 1.40), TRIM, X)
            box(hn + " WG%d" % i, d(-0.06), (0.03, 1.16, 1.26), GLASS, X)
            box(hn + " WM%d" % i, d(-0.03), (0.02, 0.04, 1.26), TRIM, X)
            box(hn + " WS%d" % i, (x + sg * 0.04, y, z - 0.7), (0.18, 1.40, 0.06), TRIM, X)
    # door: real wood veneer from the shelf, a raised panel, a brass knob
    DOOR = shelf_mat("american_walnut_veneer")
    box(hn + " Door", (door_x, -D / 2 + 0.10, 0.4 + 1.03), (0.94, 0.06, 2.06), DOOR, X)
    box(hn + " Door Panel", (door_x, -D / 2 + 0.06, 0.4 + 1.25), (0.62, 0.02, 1.2), DOOR, X)
    bm = bmesh.new(); r = bmesh.ops.create_icosphere(bm, subdivisions=2, radius=0.035)
    bmesh.ops.translate(bm, vec=(door_x + 0.36, -D / 2 + 0.05, 0.4 + 1.05), verts=r['verts'])
    finish(hn + " Knob", bm, solid("Brass", (0.85, 0.65, 0.25), 0.25, 1.0), X, smooth=True)
    box(hn + " Jamb L", (door_x - 0.53, -D / 2 - 0.03, 0.4 + 1.07), (0.07, 0.10, 2.15), TRIM, X)
    box(hn + " Jamb R", (door_x + 0.53, -D / 2 - 0.03, 0.4 + 1.07), (0.07, 0.10, 2.15), TRIM, X)
    box(hn + " Header", (door_x, -D / 2 - 0.03, 0.4 + 2.15), (1.13, 0.10, 0.08), TRIM, X)
    box(hn + " Step", (door_x, -D / 2 - 0.55, 0.15), (1.6, 0.9, 0.3), CONCRETE, X)
    if porch:
        box(hn + " Porch Deck", (0, -D / 2 - 1.1, 0.35), (W * 0.7, 2.2, 0.15), DRIVE, X)
        box(hn + " Porch Roof", (0, -D / 2 - 1.1, 0.4 + 2.75), (W * 0.7 + 0.6, 2.6, 0.12), ROOF, X)
        for px in (-W * 0.35 + 0.15, W * 0.35 - 0.15):
            box(hn + " Post", (px, -D / 2 - 2.05, 0.4 + 1.4), (0.18, 0.18, 2.7), TRIM, X)
    # corners + fascia
    for (cx, cy) in [(-W / 2, -D / 2), (W / 2, -D / 2), (-W / 2, D / 2), (W / 2, D / 2)]:
        box(hn + " Corner", (cx, cy, 0.4 + H / 2), (0.16, 0.16, H), TRIM, X)
    # roof
    if roof == 'gable':
        hh = D * 0.32
        prism(hn + " Roof", W, D, 0.4 + H, hh, ROOF, X)
        ang = math.atan2(hh, D / 2 + 0.5)
        for sx in (-W / 2 - 0.55, W / 2 + 0.55):
            for sy, a in ((-(D / 2 + 0.5) / 2, ang), ((D / 2 + 0.5) / 2, -ang)):
                bm = bmesh.new(); r = bmesh.ops.create_cube(bm, size=1.0)
                L = math.hypot(D / 2 + 0.5, hh) + 0.2
                M = Matrix.Translation((sx, sy, 0.4 + H + hh / 2 + 0.06)) @ Matrix.Rotation(a, 4, 'X') @ Matrix.Diagonal((0.08, L, 0.24, 1))
                bmesh.ops.transform(bm, matrix=M, verts=r['verts']); finish(hn + " Bargeboard", bm, TRIM, X)
        box(hn + " Ridge", (0, 0, 0.4 + H + hh + 0.12), (W + 1.1, 0.36, 0.10), solid("Ridge " + hn, (0.2, 0.1, 0.08), 0.8), X)
        box(hn + " Fascia F", (0, -D / 2 - 0.55, 0.4 + H + 0.05), (W + 1.1, 0.10, 0.22), TRIM, X)
        box(hn + " Fascia B", (0, D / 2 + 0.55, 0.4 + H + 0.05), (W + 1.1, 0.10, 0.22), TRIM, X)
    elif roof == 'hip':
        hh = min(W, D) * 0.28
        hip(hn + " Roof", W, D, 0.4 + H, hh, ROOF, X)
        for (cx, cy, sz) in [(0, -D / 2 - 0.55, (W + 1.1, 0.10, 0.22)), (0, D / 2 + 0.55, (W + 1.1, 0.10, 0.22)),
                             (-W / 2 - 0.55, 0, (0.10, D + 1.1, 0.22)), (W / 2 + 0.55, 0, (0.10, D + 1.1, 0.22))]:
            box(hn + " Fascia", (cx, cy, 0.4 + H + 0.05), sz, TRIM, X)
    else:  # flat with parapet; upper floor clad in wood, a canopy over the door
        box(hn + " Roof Slab", (0, 0, 0.4 + H + 0.06), (W - 0.1, D - 0.1, 0.12), ROOF, X)
        CLAD = shelf_mat("angli_veneer")
        if stories > 1:
            zc = 0.4 + 2.9 + (H - 2.9) / 2
            box(hn + " Clad F", (0, -D / 2 - 0.06, zc), (W + 0.12, 0.12, H - 2.9), CLAD, X)
            box(hn + " Clad B", (0, D / 2 + 0.06, zc), (W + 0.12, 0.12, H - 2.9), CLAD, X)
            box(hn + " Clad L", (-W / 2 - 0.06, 0, zc), (0.12, D + 0.12, H - 2.9), CLAD, X)
            box(hn + " Clad R", (W / 2 + 0.06, 0, zc), (0.12, D + 0.12, H - 2.9), CLAD, X)
            clad_cut = bmesh.new()
            for (x, y, z, ax, sg) in wins:
                if z > 3.0:
                    cube_into(clad_cut, (x, y, z), (1.3, 0.5, 1.4) if ax == 'y' else (0.5, 1.3, 1.4))
            cc = finish(hn + " Clad Cutters", clad_cut, TRIM, X); cc.display_type = 'WIRE'; cc.hide_render = True; cc.hide_set(True)
            for nm in ("F", "B", "L", "R"):
                m2 = bpy.data.objects[hn + " Clad " + nm].modifiers.new("Openings", 'BOOLEAN'); m2.operation = 'DIFFERENCE'; m2.object = cc; m2.solver = 'EXACT'
        box(hn + " Canopy", (door_x, -D / 2 - 0.9, 0.4 + 2.55), (2.6, 1.8, 0.12), TRIM, X)
        for (cx, cy, sz) in [(0, -D / 2, (W + 0.2, 0.25, 0.7)), (0, D / 2, (W + 0.2, 0.25, 0.7)),
                             (-W / 2, 0, (0.25, D + 0.2, 0.7)), (W / 2, 0, (0.25, D + 0.2, 0.7))]:
            box(hn + " Parapet", (cx, cy, 0.4 + H + 0.35), sz, WALL, X)
            box(hn + " Coping", (cx, cy, 0.4 + H + 0.73), (sz[0] + 0.1, sz[1] + 0.1, 0.06), TRIM, X)
    if chimney and roof != 'flat':
        cz = 0.4 + H + (D * 0.32 if roof == 'gable' else min(W, D) * 0.28) * 0.55
        box(hn + " Chimney", (W * 0.3, D * 0.2, cz + 0.6), (0.7, 0.7, 2.2), shelf_mat("brick_4"), X)
        box(hn + " Chimney Cap", (W * 0.3, D * 0.2, cz + 1.75), (0.9, 0.9, 0.1), CONCRETE, X)
    # garage (attached, one story)
    gfront = None
    if garage:
        gx = (W / 2 + 2.9) * (1 if garage == 'R' else -1)
        GW, GD = 5.8, min(D, 6.5)
        gy = -D / 2 + GD / 2
        box(hn + " Garage", (gx, gy, 0.4 + 1.45), (GW, GD, 2.9), WALL, X)
        box(hn + " Garage Found", (gx, gy, 0.2), (GW + 0.3, GD + 0.3, 0.4), FOUND, X)
        prism(hn + " Garage Roof", GW, GD, 0.4 + 2.9, GD * 0.28, ROOF, X, overhang=0.4, cx=gx, cy=gy)
        box(hn + " Garage Door", (gx, -D / 2 - 0.02, 0.4 + 1.15), (4.6, 0.12, 2.3), TRIM, X)
        for k in range(4):
            box(hn + " GD line", (gx, -D / 2 - 0.09, 0.4 + 0.45 + k * 0.56), (4.5, 0.03, 0.03), solid("GD line", (0.6, 0.6, 0.6), 0.5), X)
        box(hn + " Garage Fascia", (gx, -D / 2 - 0.45, 0.4 + 2.95), (GW + 0.9, 0.10, 0.22), TRIM, X)
        gfront = X @ Vector((gx, -D / 2 - 0.2, 0))
    door_w = X @ Vector((door_x, -D / 2 - 1.0, 0))
    return {"X": X, "W": W, "D": D, "door": door_w, "garage": gfront, "pos": Vector(pos), "yaw": yaw, "name": hn, "porch": porch}

# ---------------------------------------------------------------- the street
BULB = Vector((0, 10, 0)); RB = 11.0
box("Ground", (0, 0, -0.06), (400, 400, 0.1), GRASS)
box("Road", (0, -22, 0.02), (7.0, 46, 0.04), ASPHALT)
disc("Bulb", (BULB.x, BULB.y, 0.0), RB, 0.04, ASPHALT)
for sx in (-1, 1):
    box("Curb", (sx * 3.65, -22.5, 0.075), (0.3, 45, 0.15), CURB)
    box("Sidewalk", (sx * 4.55, -22.5, 0.07), (1.5, 45, 0.14), CONCRETE)
ring("Bulb Curb", BULB, RB, RB + 0.3, -70, 250, 0.15, CURB, 64)
ring("Bulb Sidewalk", BULB, RB + 0.3, RB + 1.8, -70, 250, 0.14, CONCRETE, 64)
disc("Island Curb", (BULB.x, BULB.y, 0.0), 3.6, 0.15, CURB, 48)
disc("Island Lawn", (BULB.x, BULB.y, 0.15), 3.3, 0.04, GRASS, 48)
for (x, y) in [(0, -40), (0, -30), (0, -20), (0, -10), (0, -4)]:
    box("Center line", (x, y, 0.045), (0.15, 3.0, 0.005), solid("Paint", (0.9, 0.85, 0.5), 0.6))

# ---------------------------------------------------------------- four houses around the bulb
def facing(pos):
    v = BULB - Vector(pos); return math.degrees(math.atan2(v.y, v.x)) + 90.0   # local -Y looks at the bulb

def spot(angle_deg, dist):
    a = math.radians(angle_deg); return (BULB.x + dist * math.cos(a), BULB.y + dist * math.sin(a), 0.0)

p1 = spot(140, 25); p2 = spot(90, 26); p3 = spot(40, 25); p4 = (-22.0, -22.0, 0.0)
h1 = house("H1", p1, facing(p1), 10.0, 8.0, 2, 'gable', "brick_floor_003", "clay_roof_tiles", (0.93, 0.92, 0.88), 'R')
h2 = house("H2", p2, facing(p2), 13.0, 8.5, 1, 'hip', "beige_wall_001", "ceramic_roof_01", (0.55, 0.30, 0.18), 'L')
h3 = house("H3", p3, facing(p3), 11.0, 9.0, 2, 'flat', "brushed_concrete_04", "bitumen", (0.12, 0.12, 0.13), 'R', chimney=False)
h4 = house("H4", p4, 90.0, 9.5, 8.0, 1, 'gable', "blue_plaster_weathered", "box_profile_metal_sheet", (0.95, 0.95, 0.93), None, porch=True)

def slab(name, a, b, width, mt, z=0.0, h=0.12):
    a, b = Vector(a), Vector(b); d = b - a; L = d.length + 0.4
    yaw = math.atan2(d.y, d.x)
    return box(name, ((a + b) / 2 + Vector((0, 0, z))), (L, width, h), mt, None, yaw)

def to_bulb_edge(p, r):
    v = Vector(p) - BULB; v.z = 0; return BULB + v.normalized() * r

for hn, h in (("H1", h1), ("H2", h2), ("H3", h3)):
    slab(hn + " Driveway", h["garage"], to_bulb_edge(h["garage"], RB + 1.9), 4.0, DRIVE, 0.075, 0.15)
    slab(hn + " Path", h["door"], to_bulb_edge(h["door"], RB + 2.0), 1.3, PATH, 0.07, 0.14)
slab("H4 Path", h4["door"], Vector((-5.4, h4["door"].y, 0)), 1.3, PATH, 0.07, 0.14)
slab("H4 Drive", Vector((-16.5, -27.5, 0)), Vector((-5.4, -27.5, 0)), 3.8, GRAVEL, 0.075, 0.15)

# ---------------------------------------------------------------- street furniture (procedural)
def lamp(pos):
    cyl("Lamp Pole", pos, 0.09, 5.0, STEEL)
    box("Lamp Arm", (pos[0], pos[1] + 0.6, 5.0), (0.12, 1.4, 0.12), STEEL)
    box("Lamp Head", (pos[0], pos[1] + 1.2, 4.85), (0.5, 0.7, 0.25), STEEL)
    box("Lamp Glass", (pos[0], pos[1] + 1.2, 4.72), (0.42, 0.62, 0.03), LAMP_GLOW)
    L = bpy.data.lights.new("Lamp Light", 'POINT'); L.energy = 400; L.color = (1.0, 0.85, 0.6); L.shadow_soft_size = 0.4
    L.use_shadow = False      # daytime scene: four shadow-casting point lights cost more than they show
    lo = bpy.data.objects.new("Lamp Light", L); lo.location = (pos[0], pos[1] + 1.2, 4.6); COL.objects.link(lo)

for lp in [(5.6, -36, 0), (-5.6, -14, 0), (12.5, 16, 0), (-12.5, 16, 0)]:
    lamp(lp)

def mailbox(pos, yaw_deg):
    X = Matrix.Translation(Vector(pos)) @ Matrix.Rotation(math.radians(yaw_deg), 4, 'Z')
    box("Mailbox Post", (0, 0, 0.5), (0.08, 0.08, 1.0), solid("MB post", (0.25, 0.18, 0.1), 0.7), X)
    box("Mailbox", (0, 0, 1.12), (0.5, 0.25, 0.24), solid("MB", (rnd.uniform(0.1, 0.5), rnd.uniform(0.1, 0.3), rnd.uniform(0.1, 0.5)), 0.4, 0.6), X)

for h in (h1, h2, h3):
    e = to_bulb_edge(h["door"], RB + 2.4); mailbox(e, math.degrees(math.atan2((e - BULB).y, (e - BULB).x)))
mailbox((-5.9, -25.5, 0), 90)

# ---------------------------------------------------------------- shelf models: trees, plants, props
def add_models():
    for (asset, pos, hgt) in [("fir_tree_01", (-24, 4, 0), 9.5), ("fir_tree_01", (26, 6, 0), 8.5), ("fir_tree_01", (12, 36, 0), 10.0),
                              ("fir_sapling_medium", (-11, 30, 0), 5.5), ("fir_sapling_medium", (20, -18, 0), 6.0),
                              ("fir_sapling_medium", (-16, -8, 0), 5.0), ("fir_tree_01", (-30, -32, 0), 9.0),
                              ("fir_sapling_medium", (BULB.x, BULB.y, 0.18), 4.5), ("fir_tree_01", (28, -40, 0), 8.0)]:
        place(asset, pos, height=hgt)
    for h in (h1, h2, h3, h4):
        for k in range(3):
            lp = h["X"] @ Vector((rnd.uniform(-h["W"] / 2, h["W"] / 2), -h["D"] / 2 - rnd.uniform(0.9, 1.6), 0))
            place("grass_bermuda_01", lp, scale=0.55)
        dp = h["door"] + (h["X"].to_3x3() @ Vector((1.8, 0.3, 0)))      # beside the path, not on it
        place(rnd.choice(["planter_box_01", "planter_box_02", "planter_pot_clay"]), dp, yaw_deg=math.degrees(h["yaw"]))
        fp = h["X"] @ Vector((h["W"] / 2 + 0.8, -h["D"] / 2 - 0.5, 0))
        place("celandine_01", fp, scale=0.5)
    for (asset, pos, kw) in [("fire_hydrant", (4.9, -12, 0), {"yaw_deg": 0, "scale": 1.0}), ("metal_trash_can", (-5.0, -33, 0), {"scale": 0.9}),
                             ("boulder_01", (17, 30, 0), {"scale": 1.2}), ("boulder_01", (19.5, 27, 0), {"scale": 0.8}),
                             ("painted_wooden_bench", (BULB.x + 1.6, BULB.y - 1.6, 0.19), {"yaw_deg": 225}),
                             ("covered_car", tuple((h2["garage"] + to_bulb_edge(h2["garage"], RB + 1.9)) / 2 + Vector((0, 0, 0.16))),
                              {"yaw_deg": math.degrees(h2["yaw"])}),
                             ("old_tyre", (-14.5, -30.5, 0), {"scale": 1.0}), ("wine_barrel_01", (-17, -18.5, 0), {"scale": 1.0}),
                             ("wooden_ladder", tuple(h4["X"] @ Vector((h4["W"] / 2 + 0.3, 1.0, 0))), {"yaw_deg": 270})]:
        place(asset, pos, **kw)

def prop_radius(root):
    r = 0.0
    for c in root.children:
        r = max(r, max(c.dimensions.x, c.dimensions.y) * root.scale.x / 2)
    return max(r, 0.25)

def house_clear(h, p, margin):
    """Push distance needed to get point p (world) out of house h's footprint (+garage, +porch), or 0."""
    l = h["X"].inverted() @ Vector((p.x, p.y, 0))
    xmin, xmax = -h["W"] / 2 - margin, h["W"] / 2 + margin
    if h["garage"] is not None:
        gl = h["X"].inverted() @ h["garage"]
        if gl.x > 0: xmax = max(xmax, gl.x + 2.9 + margin)
        else: xmin = min(xmin, gl.x - 2.9 - margin)
    ymin, ymax = -h["D"] / 2 - (2.6 if h.get("porch") else 0.0) - margin, h["D"] / 2 + margin
    if xmin < l.x < xmax and ymin < l.y < ymax:
        return True
    return False

def qa_props():
    """No prop may sit inside a house, garage, porch or another prop. Nudge away from the house; drop if it won't fit."""
    roots = [o for o in COL.objects if o.type == 'EMPTY' and " @" in o.name]
    fixed, dropped = [], []
    for root in roots:
        r = prop_radius(root)
        for h in (h1, h2, h3, h4):
            if not house_clear(h, root.location, r):
                continue
            ok = False
            away = (Vector(root.location) - h["pos"]); away.z = 0; away.normalize()
            for step in range(1, 13):
                cand = Vector(root.location) + away * 0.5 * step
                if not house_clear(h, cand, r):
                    root.location = (cand.x, cand.y, root.location.z); ok = True; break
            if ok: fixed.append("%s -> moved %.1f m off %s" % (root.name, 0.5 * step, h["name"]))
            else:
                dropped.append("%s (no room near %s)" % (root.name, h["name"]))
                for c in list(root.children): bpy.data.objects.remove(c, do_unlink=True)
                bpy.data.objects.remove(root, do_unlink=True); break
    roots = [o for o in COL.objects if o.type == 'EMPTY' and " @" in o.name]
    for i, a in enumerate(roots):
        for b in roots[i + 1:]:
            if a.name.split(" @")[0].startswith("grass") and b.name.split(" @")[0].startswith("grass"):
                continue                       # shrubs may touch each other
            d = Vector(a.location) - Vector(b.location); d.z = 0
            need = prop_radius(a) + prop_radius(b) + 0.15
            if 0 < d.length < need:
                push = d.normalized() * (need - d.length)
                b.location = (b.location.x - push.x, b.location.y - push.y, b.location.z)
                fixed.append("%s <-> %s separated %.1f m" % (a.name, b.name, push.length))
    print("QA props: %d moved, %d dropped" % (len(fixed), len(dropped)))
    for f in fixed + dropped: print("   ", f)

if WANT_MODELS:
    add_models()
    qa_props()

# ---------------------------------------------------------------- lawn grass (hair), kept off hard surfaces
def hard(x, y):
    if abs(x) < 4.6 and y < 1.0: return True
    if (Vector((x, y, 0)) - BULB).length < RB + 2.0: return True
    for h in (h1, h2, h3, h4):
        l = h["X"].inverted() @ Vector((x, y, 0))
        if abs(l.x) < h["W"] / 2 + 3.6 and abs(l.y) < h["D"] / 2 + 1.2: return True
    if -17 < x < -5 and -29.5 < y < -25.5: return True
    return False

def add_grass(count, children):
    bm = bmesh.new(); bmesh.ops.create_grid(bm, x_segments=90, y_segments=90, size=45.0)
    lawn = finish("Lawn", bm, GRASS); lawn.location.z = 0.004
    vg = lawn.vertex_groups.new(name="Density")
    for v in lawn.data.vertices:
        vg.add([v.index], 0.0 if hard(v.co.x, v.co.y) else 1.0, 'REPLACE')
    lawn.modifiers.new("Grass", 'PARTICLE_SYSTEM')
    ps = lawn.particle_systems[-1]; s = ps.settings
    s.type = 'HAIR'; s.count = count; s.hair_length = 0.14; s.length_random = 0.5; s.use_advanced_hair = True
    s.hair_step = 3; s.use_hair_bspline = True; s.child_type = 'INTERPOLATED'; s.rendered_child_count = children; s.child_percent = max(1, children // 6)
    s.clump_factor = 0.2; s.roughness_2 = 0.25; s.roughness_2_size = 0.35; s.root_radius = 1.0; s.tip_radius = 0.0; s.radius_scale = 0.004
    ps.vertex_group_density = "Density"
    sc.render.hair_type = 'STRIP'; sc.render.hair_subdiv = 2
    return lawn

if WANT_GRASS:
    add_grass(GRASS_COUNT, GRASS_CHILDREN)

# ---------------------------------------------------------------- sky, sun, cameras, render settings
w = sc.world or bpy.data.worlds.new("World"); sc.world = w; w.use_nodes = True
nt = w.node_tree; nt.nodes.clear()
out = nt.nodes.new('ShaderNodeOutputWorld'); bg = nt.nodes.new('ShaderNodeBackground'); env = nt.nodes.new('ShaderNodeTexEnvironment')
env.image = bpy.data.images.load(os.path.join(SHELF, "hdris", globals().get("SKY", "abandoned_pathway"), globals().get("SKY", "abandoned_pathway") + "_8k.hdr"), check_existing=True)
bg.inputs['Strength'].default_value = 1.0
nt.links.new(env.outputs['Color'], bg.inputs['Color']); nt.links.new(bg.outputs[0], out.inputs[0])
sun = bpy.data.lights.new("Sun", 'SUN'); sun.energy = 3.5; sun.angle = math.radians(1.5)
so = bpy.data.objects.new("Sun", sun); so.rotation_euler = (math.radians(50), 0, math.radians(-40)); COL.objects.link(so)

def camera(name, pos, aim, lens):
    c = bpy.data.cameras.new(name); c.lens = lens; c.dof.use_dof = True; c.dof.focus_distance = (Vector(aim) - Vector(pos)).length; c.dof.aperture_fstop = 8.0
    o = bpy.data.objects.new(name, c); o.location = pos
    o.rotation_euler = (Vector(aim) - Vector(pos)).to_track_quat('-Z', 'Y').to_euler(); COL.objects.link(o); return o
cam_air = camera("Cam Aerial", (36, -44, 24), (0, 8, 1.5), 32)
cam_street = camera("Cam Street", (1.8, -40, 1.7), (-2, 12, 2.5), 26)
for h in (h1, h2, h3, h4):     # QA close-ups: 16 m out from each front door, eye height 4 m, looking at the house
    fwd = h["X"].to_3x3() @ Vector((0, -1, 0))
    at = h["pos"] + Vector((0, 0, 2.0))
    camera("Cam " + h["name"], tuple(h["pos"] + fwd * 24 + Vector((4, 0, 5))), tuple(at), 28)
sc.camera = cam_air
sc.render.engine = 'BLENDER_EEVEE'
for k, val in (("use_raytracing", True), ("use_shadows", True), ("taa_samples", 16), ("taa_render_samples", 64), ("shadow_ray_count", 2), ("shadow_step_count", 4)):
    try: setattr(sc.eevee, k, val)
    except Exception as e: print("eevee", k, e)
sc.render.resolution_x = 1920; sc.render.resolution_y = 1080; sc.render.resolution_percentage = 100
try: sc.view_settings.look = 'AgX - Medium High Contrast'
except Exception: pass
for win in bpy.data.window_managers[0].windows:
    for area in win.screen.areas:
        if area.type == 'VIEW_3D':
            sp = area.spaces.active; sp.shading.type = globals().get("VIEW_MODE", "SOLID"); sp.region_3d.view_perspective = 'CAMERA'; sp.overlay.show_overlays = False
print("BUILT Maple Court: %d objects, %d shelf materials, %d shelf models, %.1fs" % (len(COL.objects), len(_mats), len(_groups), time.time() - T0))
