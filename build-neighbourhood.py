# build-neighbourhood.py - builds a neighbourhood from a BRIEF (a small JSON order form) inside UPBGE 0.50,
# from the CC0 shelf. Grew out of build-culdesac-v1.py (Maple Court). Draft, 2026-09-02.
#
#   The brief:  {"name": "...", "layout": "cul-de-sac"|"straight", "houses": [ {style, stories 1|2|3, wall, wall_color,
#                roof, garage, porch, features: ["white columns", ...]}, ... ], "trees": "few"|"some"|"many",
#                "sky": "clear"|"cloudy"|"overcast"|"sunset", "other_features": [...],
#                "placements": [{"glb": "<abs path>", "anchor": "island"|"yard:H1"|"roof:H1"|"door:H1"|"roadside", "size_m": 1.2, "yaw": 0}]}
#   Decision 23 (2026-09-03): build what is asked, fill the gaps. Feature phrases are built from primitives by keyword
#   (columns/portico, pediment, dormers, chimneys, balcony, shutters); anything no helper can build lands in UNBUILT
#   (-> status.json unbuilt_features) - nothing is dropped silently. Every key is optional: an old brief builds as before.
#   Where it comes from:  BRIEF_PATH in the calling namespace, else env NB_BRIEF, else brief.json next to this file,
#                         else the built-in Maple Court brief.
#   Missing shelf textures fall back to a family default that IS on disk, then to a plain colour - never a crash.
import bpy, bmesh, math, json, os, glob, random, time, re
from mathutils import Vector, Matrix

SHELF = r"E:\Software Development\Video Game Development\02 Asset Shelf\Landing\polyhaven"
HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else r"E:\Software Development\Video Game Development\03 Projects\Cul-de-sac"
sc = bpy.context.scene
T0 = time.time()
WANT_MODELS = globals().get("WANT_MODELS", True)
WANT_GRASS = globals().get("WANT_GRASS", True)
GRASS_COUNT = globals().get("GRASS_COUNT", 15000)
GRASS_CHILDREN = globals().get("GRASS_CHILDREN", 16)

# ---------------------------------------------------------------- the brief
DEFAULT_BRIEF = {"name": "Maple Court", "layout": "cul-de-sac", "trees": "some", "sky": "clear", "houses": [
    {"style": "colonial", "wall": "brick", "wall_color": "natural", "roof": "clay", "garage": "right", "porch": False},
    {"style": "ranch", "wall": "plaster", "wall_color": "beige", "roof": "ceramic", "garage": "left", "porch": False},
    {"style": "modern", "wall": "concrete", "wall_color": "grey", "roof": "flat", "garage": "right", "porch": False},
    {"style": "cottage", "wall": "plaster", "wall_color": "blue", "roof": "metal", "garage": "none", "porch": True}]}
BRIEF_PATH = globals().get("BRIEF_PATH") or os.environ.get("NB_BRIEF") or os.path.join(HERE, "brief.json")
try:
    brief = json.load(open(BRIEF_PATH, encoding="utf-8"))
    print("brief:", BRIEF_PATH)
except Exception as e:
    brief = DEFAULT_BRIEF
    print("brief: built-in Maple Court (%s)" % e)
import zlib
rnd = random.Random(zlib.crc32(json.dumps(brief, sort_keys=True).encode("utf-8")))   # same brief -> same neighbourhood

STYLE = {  # what a style means; the brief's wall / colour / roof / garage / porch override the defaults
    "colonial":  dict(W=(9.5, 11.0), D=(8.0, 9.0), stories=2, roof="gable", wall="brick", roof_mat="clay", trim="white", porch=False, chimney=True),
    "ranch":     dict(W=(12.0, 14.0), D=(8.0, 9.0), stories=1, roof="hip", wall="plaster", roof_mat="ceramic", trim="brown", porch=False, chimney=True),
    "modern":    dict(W=(10.0, 12.0), D=(9.0, 10.0), stories=2, roof="flat", wall="concrete", roof_mat="flat", trim="dark", porch=False, chimney=False),
    "cottage":   dict(W=(8.5, 10.0), D=(7.5, 8.5), stories=1, roof="gable", wall="plaster", roof_mat="metal", trim="white", porch=True, chimney=True),
    "farmhouse": dict(W=(10.0, 11.5), D=(8.5, 9.5), stories=2, roof="gable", wall="siding", roof_mat="metal", trim="white", porch=True, chimney=True),
    # 2026-09-04. John's Georgian mansion had nowhere to land: he wanted a HIPPED roof with
    # WHITE trim at mansion scale, and only "ranch" had a hip roof — which forces brown trim
    # and a bungalow footprint. So "presidential"/"Georgian" collapsed to colonial (gable,
    # 11 m wide) and the render came back smaller than the house next door. This style is the
    # combination that was unreachable: hip + white + big.
    "georgian":  dict(W=(15.0, 18.0), D=(11.0, 13.0), stories=3, roof="hip", wall="brick", roof_mat="clay", trim="white", porch=False, chimney=True),
}
ROOF_SHAPE_FOR = {"flat": "flat"}          # a roof material can force a shape; otherwise the style decides
TRIM_RGB = {"white": (0.93, 0.92, 0.88), "brown": (0.55, 0.30, 0.18), "dark": (0.12, 0.12, 0.13)}
TINT = {"white": None, "natural": None, "beige": (1.0, 0.92, 0.78), "grey": (0.75, 0.75, 0.75), "blue": (0.55, 0.68, 1.0),
        "red": (1.0, 0.5, 0.45), "yellow": (1.0, 0.92, 0.55), "green": (0.6, 0.85, 0.55)}
# 2026-09-04: WALL_TEX and ROOF_TEX widened using real options from the shelf. All 855 texture folders in
# Landing\polyhaven\textures were listed and every name added below was checked against that listing - none
# invented. Per key, the first entry is the plainest/least stylised default; the rest are genuine alternatives,
# best match first. 'shingle' is untouched below - it was already corrected today and is correct.
WALL_TEX = {"brick": ["brick_floor_003", "brick_4", "brick_wall_001", "red_brick", "brick_wall_005"],
            "plaster": ["beige_wall_001", "beige_wall_002", "blue_plaster_weathered", "plastered_wall", "painted_plaster_wall", "grey_plaster"],
            "concrete": ["brushed_concrete_04", "concrete_floor_painted", "concrete_wall_001", "concrete_panels", "concrete_block_wall"],
            # 'siding' means painted wooden clapboard/weatherboard - bamboo_wall and corrugated_iron_03 are not
            # that (TEX_IS_NOT below already says so): real plank/weatherboard textures now lead the list, and
            # the old two stay, demoted, rather than deleted.
            "siding": ["weathered_plank_siding", "white_planks_clean", "distressed_painted_planks", "wood_plank_wall", "bamboo_wall", "corrugated_iron_03"],
            "stone": ["castle_wall_slates", "castle_wall_varriation", "stone_wall", "stacked_stone_wall", "rustic_stone_wall", "old_stone_wall"]}
ROOF_TEX = {"clay": ["clay_roof_tiles", "clay_roof_tiles_02", "clay_roof_tiles_03", "roof_tiles"],
            "ceramic": ["ceramic_roof_01", "roof_tiles_14", "grey_roof_tiles_02", "patterned_terracotta_tiling"],
            "metal": ["box_profile_metal_sheet", "corrugated_iron_02", "corrugated_iron", "corrugated_iron_03", "rusty_metal_sheet"],
            "flat": ["bitumen", "tarred_gravel", "rubber_tiles", "asphalt_floor"],
            # 2026-09-04: 'shingle' pointed at clay_roof_tiles_02 - orange terracotta for an American shingle
            # roof - and reported nothing, because it was registered here as if it were correct. These four are
            # REAL and already in the same folder the builder reads: 855 textures sit in Landing\polyhaven\textures
            # while the tables here name about twenty. Slate first - grey, flat, laid in courses, the closest
            # thing on the shelf to an asphalt shingle roof seen from the street.
            "shingle": ["roof_slates_02", "roof_slates_03", "grey_roof_tiles", "grey_roof_01"]}

def given_dim(v, lo, hi):
    """A width or depth carried over from the picture John chose (2026-09-05). Honoured when it is
    sane for the style, otherwise the fresh draw is used. Exists because W and D are drawn per brief,
    the column count follows the width, and so the SAME words produced a six-column house in the
    candidate picture and a four-column one when built onto a longer street. The picture is a
    promise: if John picked that house, he gets that house, not another roll of the dice."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if lo * 0.6 <= f <= hi * 1.6 else None

def norm_house(i, h):
    # One persistent world (decision 22): a house's random draws depend on ITS OWN spec and lot, never on the
    # whole brief - before 2026-09-10 the seed was the entire brief, so every new order re-rolled every house
    # (bulb houses drifted up to 1.3 m between v7 and v8, street houses changed size by centimetres).
    rnd.seed(zlib.crc32(("house|%d|%s" % (i, json.dumps(h, sort_keys=True, default=str))).encode("utf-8")))
    st = STYLE.get(str(h.get("style", "")).lower(), STYLE["colonial"])
    g = str(h.get("garage", "auto")).lower()
    garage = {"left": 'L', "right": 'R', "none": None}.get(g, 'R' if i % 2 == 0 else 'L')
    if st["porch"] and g == "auto":
        garage = None
    roof_mat = str(h.get("roof", st["roof_mat"])).lower()
    if st["roof"] == "flat":
        roof_mat = "flat"                       # a flat roof is a flat roof, whatever the brief says about tiles
    if roof_mat not in ROOF_TEX:
        roof_mat = st["roof_mat"]
    stories = int(h["stories"]) if str(h.get("stories", "")).strip() in ("1", "2", "3") else st["stories"]   # the brief's count wins; else the style's usual
    # draw both ALWAYS, then override - so honouring a carried-over size never shifts the random
    # stream for the houses after it, and an unchosen street still builds exactly as it did before
    w_draw, d_draw = rnd.uniform(*st["W"]), rnd.uniform(*st["D"])
    return dict(style=[k for k, v in STYLE.items() if v is st][0],
                W=given_dim(h.get("W"), *st["W"]) or w_draw, D=given_dim(h.get("D"), *st["D"]) or d_draw,
                stories=stories, roof=ROOF_SHAPE_FOR.get(roof_mat, st["roof"] if roof_mat != "flat" else "flat"),
                wall=(str(h.get("wall", st["wall"])).lower() if str(h.get("wall", "")).lower() in WALL_TEX else st["wall"]),
                color=str(h.get("wall_color", "natural")).lower(),
                roof_mat=roof_mat, trim=st["trim"], garage=garage, porch=bool(h.get("porch", st["porch"])), chimney=st["chimney"],
                features=[p.strip()[:80] for p in (h.get("features") or []) if isinstance(p, str) and p.strip()][:12])

# ---------------------------------------------------------------- THE PLAT (John, 2026-09-10: "Phase 1 plat")
# Phase 1 of Mr. John's Neighborhood: the cul-de-sac (four lots on the bulb), the main street south to a T at
# CROSS_Y, a cross street along CROSS_X, and sixteen street lots - the original four plus twelve empty ones,
# every empty lot with road, curb and sidewalk already in and a signboard on it (decision 25). Lots are filled
# in list order; nothing already built ever moves. Phase 2 = append lots and a second cross street here.
# Yaw: 0 = the front faces -y (south), 90 = faces +x (east), 180 = faces +y (north), 270 = faces -x (west).
PLAT_PHASE = 1
CROSS_Y = -80.0
CROSS_X = (-80.0, 80.0)
def _lot(lid, x, y, yaw, side): return {"id": lid, "pos": (float(x), float(y), 0.0), "yaw": float(yaw), "side": side}
STREET_LOTS = [
    _lot("L1", -22, -22, 90, "west"), _lot("L2", 22, -22, 270, "east"),        # the original four (v0-v7): unchanged
    _lot("L3", -22, -40, 90, "west"), _lot("L4", 22, -40, 270, "east"),
    _lot("L5", -22, -58, 90, "west"), _lot("L6", 22, -58, 270, "east"),        # Phase 1: the main street continues
    _lot("L7", -44, -66, 0, "north"), _lot("L8", 44, -66, 0, "north"),         # cross street, north side, fronts face south
    _lot("L9", -66, -66, 0, "north"), _lot("L10", 66, -66, 0, "north"),
    _lot("L11", -22, -94, 180, "south"), _lot("L12", 22, -94, 180, "south"),   # cross street, south side, fronts face north
    _lot("L13", -44, -94, 180, "south"), _lot("L14", 44, -94, 180, "south"),
    _lot("L15", -66, -94, 180, "south"), _lot("L16", 66, -94, 180, "south"),
]
MAX_HOUSES = 4 + len(STREET_LOTS)      # Phase 1 capacity (was a silent [:8] - the 9th house vanished without a word)
_asked = brief.get("houses") or DEFAULT_BRIEF["houses"]
if len(_asked) > MAX_HOUSES:
    print("WARNING: %d houses asked, Phase %d holds %d - the rest wait for the next phase of the plat" % (len(_asked), PLAT_PHASE, MAX_HOUSES))
HOUSE_SPECS = [norm_house(i, h) for i, h in enumerate(_asked[:MAX_HOUSES])]
if not HOUSE_SPECS:
    HOUSE_SPECS = [norm_house(i, h) for i, h in enumerate(DEFAULT_BRIEF["houses"])]
LAYOUT = "straight" if str(brief.get("layout", "")).lower().startswith("str") else "cul-de-sac"
ROAD_MIN = CROSS_Y - 3.5                 # the main road runs from the bulb down into the cross street
TREE_N = {"few": 4, "some": 8, "many": 14}.get(str(brief.get("trees", "some")).lower(), 8)
NAME = str(brief.get("name") or "Neighbourhood")[:40]
PLACEMENTS = [e for e in (brief.get("placements") or []) if isinstance(e, dict)]          # warehouse GLBs to stand at anchors
UNBUILT = [{"house": "grounds", "phrase": p} for p in (brief.get("other_features") or []) if isinstance(p, str) and p.strip()]
# ^ every asked-for thing nothing here can build: {"house", "phrase"} -> status.json unbuilt_features (the receipt reads it)

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
COL = bpy.data.collections.new(NAME); sc.collection.children.link(COL)
LIB = bpy.data.collections.new("Library"); sc.collection.children.link(LIB)
sc.view_layers[0].layer_collection.children["Library"].exclude = True

# ---------------------------------------------------------------- materials from the shelf (with fallbacks)
_mats = {}

def have(asset):
    return bool(glob.glob(os.path.join(SHELF, "textures", asset, "*.blend")))

def shelf_mat(asset):
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

PLAIN = {"brick": (0.5, 0.25, 0.18), "plaster": (0.85, 0.8, 0.7), "concrete": (0.55, 0.55, 0.52), "siding": (0.9, 0.9, 0.85), "stone": (0.5, 0.48, 0.45),
         "clay": (0.55, 0.2, 0.12), "ceramic": (0.6, 0.35, 0.2), "metal": (0.4, 0.42, 0.45), "flat": (0.15, 0.15, 0.15), "shingle": (0.25, 0.22, 0.2)}
FALLBACKS = []
# A shelf texture registered under a material it is NOT (2026-09-04). The twelve-asset shelf holds no
# shingle and no painted siding, so these stand in. They are SUBSTITUTIONS, not matches - the tables
# above list them as if they were correct, so family_mat reported nothing and John's "hipped shingle
# roof" came back as orange clay tiles with a silent receipt. Named here so they use the fallbacks
# channel that already reaches status.json and the receipt.
TEX_IS_NOT = {("shingle", "clay_roof_tiles_02"): "clay tiles", ("shingle", "ceramic_roof_01"): "ceramic tiles",
              ("siding", "bamboo_wall"): "bamboo", ("siding", "corrugated_iron_03"): "corrugated iron"}
# A multiply tint can only darken, so white is unreachable over any photographed wall. White gets paint.
PAINT_RGB = {"white": (0.93, 0.92, 0.88)}

def family_mat(table, key, label):
    for a in table.get(key, []) + [a for k in table for a in table[k]]:
        if have(a):
            if a not in table.get(key, []):
                FALLBACKS.append("%s '%s' -> %s" % (label, key, a))
            elif (key, a) in TEX_IS_NOT:
                FALLBACKS.append("%s '%s' -> %s (no %s texture on the shelf)" % (label, key, TEX_IS_NOT[(key, a)], key))
            return shelf_mat(a)
    FALLBACKS.append("%s '%s' -> plain colour" % (label, key))
    return solid("Plain " + key, PLAIN.get(key, (0.6, 0.6, 0.6)), 0.7)

def tinted(mt, color, name):
    rgb = TINT.get(color)
    if rgb is None:
        return mt
    m, tile = mt
    m2 = m.copy(); m2.name = name
    nt = m2.node_tree
    b = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if b is None:
        return mt
    mix = nt.nodes.new('ShaderNodeMix'); mix.data_type = 'RGBA'; mix.blend_type = 'MULTIPLY'; mix.inputs[0].default_value = 0.85
    mix.inputs[7].default_value = (*rgb, 1)
    link = next((l for l in nt.links if l.to_node == b and l.to_socket.name == 'Base Color'), None)
    if link:
        nt.links.new(link.from_socket, mix.inputs[6]); nt.links.remove(link)
    else:
        mix.inputs[6].default_value = b.inputs['Base Color'].default_value
    nt.links.new(mix.outputs[2], b.inputs['Base Color'])
    m2.diffuse_color = (*rgb, 1)
    return (m2, tile)

def wall_mat(wall, color, hn):
    """One house's wall material. A colour the multiply tint cannot reach - white over photographed
    bamboo, brick or concrete - is PAINTED rather than tinted, and says so through FALLBACKS.
    2026-09-04: John asked for white clapboard, TINT['white'] was None, and he got tan bamboo boards
    with nothing in the receipt about it. Every other colour keeps the photo texture and its tint."""
    if color in PAINT_RGB:
        FALLBACKS.append("%s wall '%s' asked for %s -> painted %s (no %s %s texture on the shelf)"
                         % (hn, wall, color, color, color, wall))
        return solid("Painted %s %s" % (color, wall), PAINT_RGB[color], 0.6)
    return tinted(family_mat(WALL_TEX, wall, hn + " wall"), color, hn + " Wall")

def lawn_mat():
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
BRASS = solid("Brass", (0.85, 0.65, 0.25), 0.25, 1.0)
# 2026-09-04: widened the same way as WALL_TEX/ROOF_TEX above - every added name checked against the 855-texture shelf listing.
ASPHALT = family_mat({"a": ["asphalt_01", "asphalt_02", "asphalt_05", "asphalt_03", "asphalt_04", "clean_asphalt"]}, "a", "road")
CONCRETE = family_mat({"c": ["brushed_concrete_03", "brushed_concrete_04", "anti_slip_concrete", "brushed_concrete_2", "concrete_pavement", "smooth_concrete_floor"]}, "c", "concrete")
CURB = family_mat({"c": ["brushed_concrete", "brushed_concrete_03", "brushed_concrete_2", "concrete_pavement_02"]}, "c", "curb")
DRIVE = family_mat({"c": ["brushed_concrete_04", "brushed_concrete_03", "grooved_concrete_driveway", "slate_driveway", "concrete_pavers"]}, "c", "driveway")
PATH = family_mat({"p": ["cobblestone_02", "cobblestone_03", "brick_crosswalk", "stone_pathway", "cobblestone_01", "grey_stone_path"]}, "p", "path")
GRAVEL = family_mat({"g": ["bicolour_gravel", "gravel_floor", "gravel", "gravel_road", "gravel_floor_02"]}, "g", "gravel")
DOORWOOD = family_mat({"w": ["american_walnut_veneer", "ash_veneer", "angli_veneer", "oak_veneer_01", "cherry_veneer", "rough_pine_door"]}, "w", "door")
CLADWOOD = family_mat({"w": ["angli_veneer", "ash_veneer", "bamboo_veneer", "exterior_wall_cladding", "exterior_wall_cladding_02", "exterior_wall_cladding_03"]}, "w", "cladding")
CHIMNEYBRICK = family_mat({"b": ["brick_4", "brick_floor_003", "red_brick", "brick_wall_001", "castle_brick_01"]}, "b", "chimney")
GRASS = lawn_mat()
PLASTER = solid("Plaster Inside", (0.9, 0.88, 0.82), 0.7)      # room interiors + window/door reveals
PLASTER[0]["interior"] = True                                   # material extra -> the engine dims sky-light indoors
FLOORWOOD = (DOORWOOD[0].copy(), DOORWOOD[1]); FLOORWOOD[0].name = "Floor Wood"; FLOORWOOD[0]["interior"] = True

# ---------------------------------------------------------------- geometry helpers (box-projected UVs in local space)
def box_uv(bm, tile):
    uv = bm.loops.layers.uv.verify()
    bm.normal_update()
    for f in bm.faces:
        n = f.normal; ax = max(range(3), key=lambda i: abs(n[i]))
        for l in f.loops:
            c = l.vert.co
            u, v = ((c.y, c.z), (c.x, c.z), (c.x, c.y))[ax]
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

def ramp(name, center, size, rise, mt, xform=None):
    """A box tilted about its local X axis so its far (+y) end sits `rise` higher - a walk-up to a door."""
    bm = bmesh.new(); r = bmesh.ops.create_cube(bm, size=1.0)
    ang = math.atan2(rise, size[1])
    M = Matrix.Translation(center) @ Matrix.Rotation(ang, 4, 'X') @ Matrix.Diagonal((*size, 1))   # +X rotation lifts the +y end
    bmesh.ops.transform(bm, matrix=M, verts=r['verts'])
    return finish(name, bm, mt, xform)

def gl(v):
    """Blender world (x, y, z) -> the engine's Y-up (x, z, -y), rounded for the manifest."""
    return [round(v.x, 3), round(v.z, 3), round(-v.y, 3)]

def tag(ob, **props):
    """Mark an object interactive: custom properties become glTF extras -> the engine's userData."""
    for k, v in props.items():
        ob[k] = v
    return ob

def parent_to(child, parent):
    child.parent = parent; child.matrix_parent_inverse = parent.matrix_world.inverted()

def disc(name, center, r, h, mt, segs=64):
    bm = bmesh.new()
    res = bmesh.ops.create_cone(bm, cap_ends=True, segments=segs, radius1=r, radius2=r, depth=h)
    bmesh.ops.translate(bm, vec=(center[0], center[1], center[2] + h / 2), verts=res['verts'])
    return finish(name, bm, mt)

def ring(name, center, r1, r2, a0, a1, h, mt, segs=48):
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
    rl = max(0.0, (w - d))
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

def have_model(asset):
    return bool(glob.glob(os.path.join(SHELF, "models", asset, "*.blend")))

def shelf_model(asset):
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
    """Instance ONE variant of a shelf model (Poly Haven packs ship a/b/c variants x LOD0/1/2 + spare parts)."""
    if not have_model(asset):
        FALLBACKS.append("model '%s' not on the shelf yet - skipped" % asset); return None
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
    vol = lambda o: max(1e-9, o.dimensions.x * o.dimensions.y * o.dimensions.z)
    biggest = max(pool, key=vol)
    alts = [o for o in pool if vol(o) >= 0.5 * vol(biggest)]
    main = rnd.choice(alts)
    centre = main.matrix_world @ (sum((Vector(b) for b in main.bound_box), Vector()) / 8)
    reach = max(main.dimensions) * 0.75
    SKIP = ("aged", "rust", "dead", "flattened", "geonodes", "twig")
    # A part belongs to the chosen skin (2026-09-03 fix): its skin words must equal the main body's.
    # The old rule only dropped parts carrying a word the main LACKED, so an aged/rust main let the
    # CLEAN caps/handles through as well - both sets under one anchor, 0.6-1.0 m apart ("exploded"
    # hydrants and trash cans, 18 of 18 worlds matched the random skin pick). An untagged part is
    # still kept for a tagged main when the pack has no tagged twin of it (a shared bolt), so nothing
    # that used to appear disappears.
    skin = lambda n: {t for t in SKIP if t in n.lower()}
    core = lambda n: re.sub(r"_?(%s)_?" % "|".join(SKIP), "_", re.sub(r"\.\d+$", "", n.lower())).replace("__", "_").strip("_")
    main_skin = skin(main.name)
    def same_skin(o):
        if skin(o.name) == main_skin: return True
        if skin(o.name): return False                       # a different skin's part - never
        return not any(core(q.name) == core(o.name) and skin(q.name) == main_skin for q in pool)   # untagged, and no twin in this skin
    parts = [o for o in pool if o not in alts and vol(o) < 0.1 * vol(biggest)
             and (o.matrix_world.translation - centre).length <= reach
             and same_skin(o)]
    if len(pool) > 12:
        parts = []
    origin = main.matrix_world.translation.copy()
    for o in [main] + parts:
        c = o.copy(); COL.objects.link(c); c.parent = root
        c.location = c.location - origin
        c.hide_render = False; c.hide_viewport = False
        try: c.hide_set(False)
        except Exception: pass
    return root

# ---------------------------------------------------------------- feature parts (decision 23: build what is asked, fill the gaps)
# One helper per part, all in the house's LOCAL frame (front = -y, the door at c["door_x"]) and placed through the
# house matrix X exactly like every other house part. A helper returns None when built, or a short reason when it can't.
# Painted parts (John, 2026-09-10: "a red door shouldn't be hard" — his cottage came back "Couldn't build: red front
# door"). A colour word within a few words before a paintable part repaints that part; the nearest colour wins, so
# "white siding with a red front door" paints the door red, not white.
PART_PAINT = {"red": (0.72, 0.10, 0.10), "blue": (0.15, 0.30, 0.65), "navy": (0.08, 0.12, 0.35), "green": (0.15, 0.45, 0.22),
              "yellow": (0.95, 0.80, 0.20), "black": (0.05, 0.05, 0.06), "white": (0.93, 0.92, 0.88), "grey": (0.55, 0.55, 0.55),
              "gray": (0.55, 0.55, 0.55), "brown": (0.40, 0.24, 0.12), "orange": (0.90, 0.45, 0.10), "pink": (0.95, 0.55, 0.65),
              "purple": (0.45, 0.20, 0.55), "teal": (0.10, 0.50, 0.50), "burgundy": (0.45, 0.08, 0.15), "maroon": (0.45, 0.08, 0.15),
              "turquoise": (0.20, 0.70, 0.70)}
PAINT_PART_RX = r"\b(garage door|front door|door|trim|shutters?)\b"
PAINT_RX = r"\b(%s)\b[\w\s,'-]{0,24}?%s" % ("|".join(PART_PAINT), PAINT_PART_RX)
FEATURES = [("columns", r"\bcolumns?\b|\bpillars?\b|\bportico\b|\bcolonnade\b"), ("pediment", r"\bpediments?\b"),
            ("dormers", r"\bdormers?\b"), ("chimneys", r"\bchimneys?\b"), ("balcony", r"\bbalcon(y|ies)\b"), ("shutters", r"\bshutters?\b"),
            ("paint", PAINT_RX)]
COLUMNS_RX = dict(FEATURES)["columns"]   # so the porch/canopy code can tell a portico is coming before the features loop runs
WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8}
WHITE = solid("Classical White", (0.94, 0.93, 0.90), 0.5)       # columns, entablature, pediments, railings
SHUTTER = solid("Shutter", (0.10, 0.12, 0.14), 0.6)

def count(ph, default, lo, hi):
    """The number in a phrase ('6 columns', 'two dormers'); storey counts are not it; clamped to lo..hi."""
    ph = re.sub(r"\b(\d+|one|two|three)[ -]?(stor(e)?ys?|stories|floors?|levels?)\b", " ", ph.lower())
    m = re.search(r"\b(\d+|%s)\b" % "|".join(WORDNUM), ph)
    n = (WORDNUM.get(m.group(1)) or int(m.group(1))) if m else default
    return max(lo, min(hi, n))

def gable_over(name, cx, cy, depth, span, z0, hh, mt, X):
    """A small gable whose triangle faces the street: prism() runs its ridge along x, so turn it 90 degrees."""
    xf = X @ Matrix.Translation((cx, cy, 0)) @ Matrix.Rotation(math.radians(90), 4, 'Z')
    return prism(name, depth, span, z0, hh, mt, xf, overhang=0.0)

def feat_columns(c, ph, pediment):
    """n round white columns, floor to eave, across the entry under a flat entablature (+ a pediment on top if asked).
    Centred on x=0 (2026-09-04: door_x is also always 0 now, but this centres on 0 directly rather than
    trusting that) and spanning the centre bays of the house's own bay grid - 3 bays when there are enough
    of them for a real portico, else just the entry bay - so the row is square about the door and sized off
    the facade's own rhythm, not off the whole house width."""
    hn, W, D, H, X = c["hn"], c["W"], c["D"], c["H"], c["X"]
    n_bays = c["n_bays"]
    bay_w = W / n_bays
    span_bays = 3 if n_bays >= 5 else 1
    half_span = span_bays * bay_w / 2                             # centre (x=0) to the portico's outer edge
    n = count(ph, 4, 2, 8)
    yc = -D / 2 - (2.05 if c["porch"] else 2.5)                  # the column line: the porch's front edge, else just past the ramp
    z0, zt = (0.425 if c["porch"] else 0.0), 0.4 + H - 0.5       # column foot, entablature underside
    far, near = n // 2, n - n // 2                               # a gap at x=0 for the path in and out
    s = max(0.5, min(1.5, (half_span - 1.2) / max(1, far - 1))) # 1.5 m apart, squeezed to stay within the bay span
    xs = sorted([1.2 + s * k for k in range(far)] + [-(1.2 + s * k) for k in range(near)])
    # Column THICKNESS follows the column's own height (2026-09-04). It used to be a flat
    # 0.18 m radius whatever the house: fine on two storeys, but on John's three-storey
    # Georgian the shafts ran ~24:1 and read as scaffolding poles, not masonry. Classical
    # orders sit near 8-10:1, so take height/9 for the diameter, clamped so a bungalow
    # portico does not grow tree trunks. The plinth and capital widen with it.
    shaft_h = zt - z0 - 0.22
    r = max(0.16, min(0.40, shaft_h / 18.0))                     # radius = height/18 => ~9:1 height:diameter
    cap = max(0.5, r * 2.6)                                      # plinth/capital stay proportionate to the shaft
    for i, x in enumerate(xs):
        box(hn + " Plinth %d" % i, (x, yc, z0 + 0.06), (cap, cap, 0.12), WHITE, X)
        cyl(hn + " Column %d" % i, (x, yc, z0 + 0.12), r, shaft_h, WHITE, X, 24)
        box(hn + " Capital %d" % i, (x, yc, zt - 0.05), (cap, cap, 0.10), WHITE, X)
    span, depth = 2 * half_span + 0.9, -D / 2 - (yc - 0.35)      # span comes off the bay grid, not the columns, so it stays square
    cy = (yc - 0.35 - D / 2) / 2
    box(hn + " Entablature", (0.0, cy, zt + 0.25), (span, depth, 0.5), WHITE, X)
    if pediment:
        gable_over(hn + " Pediment", 0.0, cy, depth, span, zt + 0.5, span * 0.2, WHITE, X)
    # The columns hold up a real roof, not a slab flush with the wall (2026-09-04, item 6): a shallow
    # cap sitting directly on the entablature, in the house's own roof material.
    box(hn + " Portico Roof", (0.0, cy, zt + 0.57), (span + 0.3, depth + 0.3, 0.14), c["ROOF"], X)
    # And something to stand on: when the style's own porch deck isn't already there, a low platform
    # at the column bases so the entry reads as a porch, not four poles in the lawn.
    if not c["porch"]:
        box(hn + " Portico Deck", (0.0, cy, z0 - 0.075), (span - 0.2, depth - 0.1, 0.15), CONCRETE, X)

def feat_pediment(c, ph):
    """The triangular gable over the entry on its own: on the porch roof's front edge, else on a slab above the door."""
    hn, D, X, dx = c["hn"], c["D"], c["X"], c["door_x"]
    if c["porch"]:
        cy, z0 = -D / 2 - 2.4 + 0.7, 0.4 + 2.81
    else:
        cy, z0 = -D / 2 - 0.65, 0.4 + 2.62                       # clear of the door header and a modern canopy
        box(hn + " Pediment Slab", (dx, cy, z0 - 0.05), (3.0, 1.3, 0.10), WHITE, X)
    gable_over(hn + " Pediment", dx, cy, 1.4, 2.9, z0, 0.65, WHITE, X)

def feat_dormers(c, ph):
    """n small gabled boxes with a window, low on the front roof slope."""
    hn, W, D, H, X, roof = c["hn"], c["W"], c["D"], c["H"], c["X"], c["roof"]
    if roof == 'flat':
        return "a flat roof has no slope for dormers"
    n = count(ph, 2, 1, 4)
    w, d = W / 2 + 0.5, D / 2 + 0.5
    hh = D * 0.32 if roof == 'gable' else min(W, D) * 0.28
    zs = lambda y: 0.4 + H + hh * (y + d) / d                    # the front slope's height at y (eave at -d, ridge at 0)
    yf = -D / 2 * 0.8                                            # the dormer's front face; its ridge stays under the main ridge
    xm = W / 2 - 0.9 if roof == 'gable' else w - (w - max(0.0, w - d)) * (yf + d) / d - 0.9   # hip: inside the front face, off the hip edges
    if xm < 0.7:
        n = 1
    zb, zt = zs(yf) - 0.15, zs(yf) + 1.3
    for i in range(n):
        x = -xm + 2 * xm * (i + 0.5) / n if n > 1 else 0.0
        box(hn + " Dormer %d" % i, (x, yf + 0.8, (zb + zt) / 2), (1.4, 1.6, zt - zb), c["WALL"], X)
        box(hn + " Dormer WF%d" % i, (x, yf - 0.06, zt - 0.75), (0.96, 0.06, 1.06), c["TRIM"], X)
        box(hn + " Dormer WG%d" % i, (x, yf - 0.03, zt - 0.75), (0.84, 0.03, 0.94), GLASS, X)
        gable_over(hn + " Dormer Roof %d" % i, x, yf + 0.9, 1.9, 1.7, zt, 0.5, c["ROOF"], X)

def feat_chimneys(c, ph):
    """1-2 brick chimneys at the ridge ends; a style that already has its own chimney counts it as one."""
    hn, W, D, H, X, roof = c["hn"], c["W"], c["D"], c["H"], c["X"], c["roof"]
    n = count(ph, 1, 1, 2)
    ex = W / 2 - 1.0 if roof != 'hip' else max(0.8, (W - D) / 2 - 0.2)    # a hip ridge is short: stay on it
    xs = [-ex, ex][:n]
    if c["chimney"]:
        xs = xs[:n - 1]                                          # the style's own chimney (right, back slope) is one of them
    hh = D * 0.32 if roof == 'gable' else min(W, D) * 0.28 if roof == 'hip' else 0.0
    for x in xs:
        z0 = 0.4 + H + 0.1
        box(hn + " Chimney %s" % ("L" if x < 0 else "R"), (x, 0, z0 + (hh + 0.9) / 2), (0.7, 0.7, hh + 0.9), CHIMNEYBRICK, X)
        box(hn + " Chimney Cap %s" % ("L" if x < 0 else "R"), (x, 0, z0 + hh + 0.95), (0.9, 0.9, 0.1), CONCRETE, X)

def feat_balcony(c, ph):
    """A slab with a railing over the entry at the 2nd-storey line (on the porch roof when there is one)."""
    hn, D, X, dx = c["hn"], c["D"], c["X"], c["door_x"]
    if c["stories"] < 2:
        return "a balcony needs a 2nd storey"
    zc = 0.4 + (2.81 if c["porch"] else 2.9) + 0.075
    box(hn + " Balcony", (dx, -D / 2 - 0.7, zc), (3.2, 1.4, 0.15), CONCRETE, X)
    bm = bmesh.new(); zr = zc + 0.075
    for (x, y, sz) in [(dx, -D / 2 - 1.37, (3.2, 0.06, 0.06)), (dx - 1.57, -D / 2 - 0.7, (0.06, 1.4, 0.06)), (dx + 1.57, -D / 2 - 0.7, (0.06, 1.4, 0.06))]:
        cube_into(bm, (x, y, zr + 1.0), sz)
    for i in range(21):
        cube_into(bm, (dx - 1.5 + 0.15 * i, -D / 2 - 1.37, zr + 0.5), (0.03, 0.03, 1.0))
    for i in range(9):
        for sx in (-1.57, 1.57):
            cube_into(bm, (dx + sx, -D / 2 - 0.05 - 0.15 * i, zr + 0.5), (0.03, 0.03, 1.0))
    finish(hn + " Balcony Rail", bm, WHITE, X)

def feat_shutters(c, ph):
    """Thin dark boxes either side of every front window, flat against the wall."""
    bm = bmesh.new()
    for (x, y, z, ax, sg) in c["wins"]:
        if ax == 'y' and sg == -1:
            for s in (-1, 1):
                cube_into(bm, (x + s * 0.88, y - 0.035, z), (0.42, 0.05, 1.42))
    if not len(bm.verts):
        bm.free(); return "no front windows to shutter"
    finish(c["hn"] + " Shutters", bm, SHUTTER, c["X"])

def feat_paint(c, ph):
    """Repaint named parts: every '<colour> ... <door|garage door|trim|shutters>' in the phrase swaps that part's
    material for a solid of that colour. Runs after the parts exist (the features loop follows the door and the
    garage), so it finds them by name in COL. Returns None when something was painted, else the reason."""
    hn = c["hn"]; painted = []
    for m in re.finditer(PAINT_PART_RX, ph, re.I):
        before = ph[max(0, m.start() - 30):m.start()].lower()
        colours = [w for w in re.findall(r"[a-z]+", before) if w in PART_PAINT]
        if not colours:
            continue
        colour, part = colours[-1], m.group(1).lower()
        names = {"door": (hn + " Door", hn + " Door Panel"), "front door": (hn + " Door", hn + " Door Panel"),
                 "garage door": (hn + " Garage Door",), "shutter": (hn + " Shutters",), "shutters": (hn + " Shutters",)}.get(part)
        if part == "trim":
            objs = [o for o in COL.objects if o.name.startswith(hn + " ") and o.data and o.data.materials and o.data.materials[0] == c["TRIM"][0]]
        else:
            objs = [o for o in COL.objects if o.name in names]
        if not objs:
            continue
        mat = solid("%s %s %s" % (hn, colour.title(), part.title()), PART_PAINT[colour], 0.45)[0]
        for o in objs:
            o.data.materials.clear(); o.data.materials.append(mat)
        painted.append("%s %s" % (colour, part))
    return None if painted else "no paintable part named (door, garage door, trim, shutters)"

# ---------------------------------------------------------------- the house builder
def bay_grid(W, target=2.6):
    """The front's own rhythm, computed once: an ODD number of bays (>= 3) spanning width W, evenly spaced
    and symmetric about x=0 - so there is always one true centre bay for the door, and above it the portico,
    with every other bay landing on the same grid. Bay width targets ~2.6 m, the spacing the window loop
    already aimed for."""
    n = max(3, round(W / target))
    if n % 2 == 0:
        n += 1
    bay_w = W / n
    return n, [-W / 2 + bay_w * (i + 0.5) for i in range(n)]

def house(hn, pos, yaw_deg, spec):
    W, D, stories, roof = spec["W"], spec["D"], spec["stories"], spec["roof"]
    garage, porch, chimney = spec["garage"], spec["porch"], spec["chimney"]
    yaw = math.radians(yaw_deg)
    X = Matrix.Translation(Vector(pos)) @ Matrix.Rotation(yaw, 4, 'Z')
    H = 2.9 * stories
    WALL = wall_mat(spec["wall"], spec["color"], hn)
    ROOF = family_mat(ROOF_TEX, spec["roof_mat"], hn + " roof")
    TRIM = solid("Trim " + hn, TRIM_RGB.get(spec["trim"], TRIM_RGB["white"]), 0.4)
    FOUND = CONCRETE
    n_bays, bay_xs = bay_grid(W)                                 # the front's own rhythm - door, windows and portico all read off this
    has_columns = any(re.search(COLUMNS_RX, ph, re.I) for ph in spec.get("features", []))   # needed before the porch/canopy below

    box(hn + " Foundation", (0, 0, 0.2), (W + 0.3, D + 0.3, 0.4), FOUND, X)
    walls = box(hn + " Walls", (0, 0, 0.4 + H / 2), (W, D, H), WALL, X)
    cut = bmesh.new()
    # The front door is always at the CENTRE bay (2026-09-04). This line used to read
    # `-W/4 if garage != 'L' else W/4`, which never centres anything: with garage "none"
    # the test is still true, so the door sat a quarter of the width off to one side. On a
    # Georgian front that is fatal — feat_columns used to centre its portico on door_x, so the
    # columns were symmetrical about the wrong point and the whole facade read crooked. The
    # garage no longer moves the door at all — it stands clear of the main block as its own wing
    # (see the garage block below) instead.
    door_x = 0.0
    # The ground floor is a real room (2026-09-02): hollow the shell (0.25 m walls, 0.25 m ceiling),
    # cut the door and windows THROUGH, and give the inside a wood floor. Starts 2 cm below the
    # wall bottom so the boolean never meets a coplanar face.
    CEIL = 0.4 + 2.9 - 0.25
    cube_into(cut, (0, 0, 0.38 + (CEIL - 0.38) / 2), (W - 0.5, D - 0.5, CEIL - 0.38))
    cube_into(cut, (door_x, -D / 2, 0.4 + 1.05), (1.0, 0.9, 2.1))
    box(hn + " Floor", (0, 0, 0.4 + 0.015), (W - 0.5, D - 0.5, 0.03), FLOORWOOD, X)
    wins = []
    for s in range(stories):
        z = 0.4 + 1.7 + 2.9 * s
        # FRONT face: on the bay grid, not evenly re-spaced, so windows line up with the door and
        # the portico above. Ground floor skips the centre bay (that's the door); upper floors use
        # every bay including the centre.
        for i, x in enumerate(bay_xs):
            if s == 0 and i == n_bays // 2:
                continue
            wins.append((x, -D / 2, z, 'y', -1))
        # REAR face: unchanged - even spacing off the house width, independent of the front.
        n = max(2, int(W // 2.6))
        for i in range(n):
            x = -W / 2 + W * (i + 0.5) / n
            wins.append((x, D / 2, z, 'y', 1))
        m = max(1, int(D // 3.0))
        for i in range(m):
            y = -D / 2 + D * (i + 0.5) / m
            if garage != 'R' or s > 0:
                wins.append((W / 2, y, z, 'x', 1))
            if garage != 'L' or s > 0:
                wins.append((-W / 2, y, z, 'x', -1))
    for (x, y, z, ax, sg) in wins:
        cube_into(cut, (x, y, z), (1.2, 0.9, 1.3) if ax == 'y' else (0.9, 1.2, 1.3))
    cutter = finish(hn + " Cutters", cut, PLASTER, X)       # the cut faces (room inside, reveals) take the cutter's plaster
    cutter.display_type = 'WIRE'; cutter.hide_render = True
    try: cutter.hide_set(True)
    except Exception: pass
    mod = walls.modifiers.new("Openings", 'BOOLEAN'); mod.operation = 'DIFFERENCE'; mod.object = cutter; mod.solver = 'EXACT'
    # The door/window cubes overlap the hollow cube inside ONE cutter mesh. Without use_self the exact
    # solver counts that overlap even-odd and leaves a SOLID block just inside every opening (2026-09-03:
    # the player walked up to the open door and stopped dead at the threshold).
    mod.use_self = True
    try: mod.material_mode = 'TRANSFER'
    except Exception: pass
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
    # The front door is INTERACTIVE: one object (panel + knob parented to it), hinged on its left
    # edge, swinging inward. The tags become glTF extras the engine reads (modules/interact).
    door = box(hn + " Door", (door_x, -D / 2 + 0.10, 0.4 + 1.03), (0.94, 0.06, 2.06), DOORWOOD, X)
    panel = box(hn + " Door Panel", (door_x, -D / 2 + 0.06, 0.4 + 1.25), (0.62, 0.02, 1.2), DOORWOOD, X)
    bm = bmesh.new(); r = bmesh.ops.create_icosphere(bm, subdivisions=2, radius=0.035)
    bmesh.ops.translate(bm, vec=(door_x + 0.36, -D / 2 + 0.05, 0.4 + 1.05), verts=r['verts'])
    knob = finish(hn + " Knob", bm, BRASS, X, smooth=True)
    parent_to(panel, door); parent_to(knob, door)
    tag(door, interact="door", hinge=gl(X @ Vector((door_x - 0.47, -D / 2 + 0.10, 0.4 + 1.03))), open_deg=95, prompt="the front door")
    box(hn + " Jamb L", (door_x - 0.53, -D / 2 - 0.03, 0.4 + 1.07), (0.07, 0.10, 2.15), TRIM, X)
    box(hn + " Jamb R", (door_x + 0.53, -D / 2 - 0.03, 0.4 + 1.07), (0.07, 0.10, 2.15), TRIM, X)
    box(hn + " Header", (door_x, -D / 2 - 0.03, 0.4 + 2.15), (1.13, 0.10, 0.08), TRIM, X)
    box(hn + " Sill", (door_x, -D / 2 + 0.12, 0.4 + 0.01), (1.0, 0.26, 0.02), TRIM, X)
    # Walk-up: a gentle ramp to floor level (the engine's walker can't climb a 40 cm step).
    front_y = -D / 2 - (2.2 if porch else 0.0)
    ramp(hn + " Ramp", (door_x, front_y - 1.05, 0.16), (1.6, 2.1, 0.08), 0.4 if not porch else 0.425, CONCRETE, X)
    # Light switch by the door (inside) + the ceiling light it controls.
    sw_x = door_x + (0.85 if door_x < 0 else -0.85)
    switch = box(hn + " Light Switch", (sw_x, -D / 2 + 0.25 + 0.015, 0.4 + 0.95), (0.08, 0.03, 0.12), TRIM, X)
    lamp = box(hn + " Ceiling Light", (0, 0, CEIL - 0.03), (0.5, 0.5, 0.06), LAMP_GLOW, X)
    tag(switch, interact="switch", target=hn + " Ceiling Light", prompt="Light switch",
        light_at=gl(X @ Vector((0, 0, CEIL - 0.3))), light_color="#ffe6c0", light_intensity=80.0)
    if porch:
        box(hn + " Porch Deck", (0, -D / 2 - 1.1, 0.35), (W * 0.7, 2.2, 0.15), DRIVE, X)
        # A house with real columns gets its own portico roof and posts (feat_columns, below) -
        # this flat porch roof would run straight through them, so skip roof + posts and keep the deck.
        if not has_columns:
            box(hn + " Porch Roof", (0, -D / 2 - 1.1, 0.4 + 2.75), (W * 0.7 + 0.6, 2.6, 0.12), ROOF, X)
            for px in (-W * 0.35 + 0.15, W * 0.35 - 0.15):
                box(hn + " Post", (px, -D / 2 - 2.05, 0.4 + 1.4), (0.18, 0.18, 2.7), TRIM, X)
    for (cx, cy) in [(-W / 2, -D / 2), (W / 2, -D / 2), (-W / 2, D / 2), (W / 2, D / 2)]:
        box(hn + " Corner", (cx, cy, 0.4 + H / 2), (0.16, 0.16, H), TRIM, X)
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
    else:
        box(hn + " Roof Slab", (0, 0, 0.4 + H + 0.06), (W - 0.1, D - 0.1, 0.12), ROOF, X)
        if stories > 1:
            zc = 0.4 + 2.9 + (H - 2.9) / 2
            for nm, c, sz in (("F", (0, -D / 2 - 0.06, zc), (W + 0.12, 0.12, H - 2.9)), ("B", (0, D / 2 + 0.06, zc), (W + 0.12, 0.12, H - 2.9)),
                              ("L", (-W / 2 - 0.06, 0, zc), (0.12, D + 0.12, H - 2.9)), ("R", (W / 2 + 0.06, 0, zc), (0.12, D + 0.12, H - 2.9))):
                box(hn + " Clad " + nm, c, sz, CLADWOOD, X)
            clad_cut = bmesh.new()
            for (x, y, z, ax, sg) in wins:
                if z > 3.0:
                    cube_into(clad_cut, (x, y, z), (1.3, 0.5, 1.4) if ax == 'y' else (0.5, 1.3, 1.4))
            cc = finish(hn + " Clad Cutters", clad_cut, TRIM, X); cc.display_type = 'WIRE'; cc.hide_render = True
            try: cc.hide_set(True)
            except Exception: pass
            for nm in ("F", "B", "L", "R"):
                m2 = bpy.data.objects[hn + " Clad " + nm].modifiers.new("Openings", 'BOOLEAN'); m2.operation = 'DIFFERENCE'; m2.object = cc; m2.solver = 'EXACT'
        if not has_columns:      # real columns bring their own portico roof (feat_columns) - this canopy would pass straight through it
            box(hn + " Canopy", (door_x, -D / 2 - 0.9, 0.4 + 2.55), (2.6, 1.8, 0.12), TRIM, X)
        for (cx, cy, sz) in [(0, -D / 2, (W + 0.2, 0.25, 0.7)), (0, D / 2, (W + 0.2, 0.25, 0.7)),
                             (-W / 2, 0, (0.25, D + 0.2, 0.7)), (W / 2, 0, (0.25, D + 0.2, 0.7))]:
            box(hn + " Parapet", (cx, cy, 0.4 + H + 0.35), sz, WALL, X)
            box(hn + " Coping", (cx, cy, 0.4 + H + 0.73), (sz[0] + 0.1, sz[1] + 0.1, 0.06), TRIM, X)
    if chimney and roof != 'flat':
        cz = 0.4 + H + (D * 0.32 if roof == 'gable' else min(W, D) * 0.28) * 0.55
        box(hn + " Chimney", (W * 0.3, D * 0.2, cz + 0.6), (0.7, 0.7, 2.2), CHIMNEYBRICK, X)
        box(hn + " Chimney Cap", (W * 0.3, D * 0.2, cz + 1.75), (0.9, 0.9, 0.1), CONCRETE, X)
    gfront = None
    if garage:
        # The garage is a WING (2026-09-04), not part of the front: it no longer moves door_x (see
        # above), and it sits back GSET from the main facade so it reads as attached rather than as
        # another slice of the front wall. Everything below that used to measure from the house's
        # front plane (-D/2) now measures from the wing's own, recessed one (gfy) instead - same
        # geometry, just moved back as a block.
        GSET = 0.6
        gx = (W / 2 + 2.9) * (1 if garage == 'R' else -1)
        GW, GD = 5.8, min(D, 6.5)
        gfy = -D / 2 + GSET                                       # the wing's own front plane
        gy = gfy + GD / 2
        gbox = box(hn + " Garage", (gx, gy, 0.4 + 1.45), (GW, GD, 2.9), WALL, X)
        box(hn + " Garage Found", (gx, gy, 0.2), (GW + 0.3, GD + 0.3, 0.4), FOUND, X)
        prism(hn + " Garage Roof", GW, GD, 0.4 + 2.9, GD * 0.28, ROOF, X, overhang=0.4, cx=gx, cy=gy)
        # Hollow garage with a through-cut for the rolling door (same recipe as the house shell).
        gcut = bmesh.new()
        cube_into(gcut, (gx, gy, 0.38 + (0.4 + 2.65 - 0.38) / 2), (GW - 0.5, GD - 0.5, 0.4 + 2.65 - 0.38))
        cube_into(gcut, (gx, gfy, 0.4 + 1.15), (4.6, 0.9, 2.3))
        gc = finish(hn + " Garage Cutters", gcut, PLASTER, X); gc.display_type = 'WIRE'; gc.hide_render = True
        try: gc.hide_set(True)
        except Exception: pass
        gm = gbox.modifiers.new("Openings", 'BOOLEAN'); gm.operation = 'DIFFERENCE'; gm.object = gc; gm.solver = 'EXACT'
        gm.use_self = True
        try: gm.material_mode = 'TRANSFER'
        except Exception: pass
        gdoor = box(hn + " Garage Door", (gx, gfy - 0.02, 0.4 + 1.15), (4.6, 0.12, 2.3), TRIM, X)
        for k in range(4):
            parent_to(box(hn + " GD line", (gx, gfy - 0.09, 0.4 + 0.45 + k * 0.56), (4.5, 0.03, 0.03), solid("GD line", (0.6, 0.6, 0.6), 0.5), X), gdoor)
        tag(gdoor, interact="slide", slide=[0.0, 2.2, 0.0], prompt="the garage door")
        ramp(hn + " Apron", (gx, gfy - 1.05, 0.16), (4.8, 2.1, 0.08), 0.4, DRIVE, X)
        box(hn + " Garage Fascia", (gx, gfy - 0.45, 0.4 + 2.95), (GW + 0.9, 0.10, 0.22), TRIM, X)
        gfront = X @ Vector((gx, gfy - 0.2, 0))
    # Feature parts (decision 23): every phrase in spec["features"] is matched by keyword and built; a phrase
    # no helper knows, or a helper's "can't" reason, goes to UNBUILT. Parts are parented to the walls object.
    c = dict(hn=hn, W=W, D=D, H=H, X=X, door_x=door_x, roof=roof, porch=porch, stories=stories, chimney=chimney, wins=wins, WALL=WALL, ROOF=ROOF, TRIM=TRIM,
             n_bays=n_bays, bay_xs=bay_xs)
    kinds, built = {}, []
    for ph in spec.get("features", []):
        ks = [k for k, rx in FEATURES if re.search(rx, ph, re.I)]
        if not ks:
            UNBUILT.append({"house": hn, "phrase": ph})
        for k in ks:
            kinds.setdefault(k, ph)
    was = {o.name for o in COL.objects}
    for k, ph in kinds.items():
        if k == "columns":
            why = feat_columns(c, ph, "pediment" in kinds)
        elif k == "pediment":
            why = None if "columns" in kinds else feat_pediment(c, ph)       # with columns it sits on the portico
        else:
            why = {"dormers": feat_dormers, "chimneys": feat_chimneys, "balcony": feat_balcony, "shutters": feat_shutters, "paint": feat_paint}[k](c, ph)
        if why:
            UNBUILT.append({"house": hn, "phrase": "%s (%s)" % (ph, why)})
        elif ph not in built:
            built.append(ph)
    for o in COL.objects:
        if o.name not in was:
            parent_to(o, walls)
    ridge = 0.4 + H + (D * 0.32 + 0.17 if roof == 'gable' else min(W, D) * 0.28 + 0.12 if roof == 'hip' else 0.12)   # top of the ridge cap / roof shell / slab
    door_w = X @ Vector((door_x, -D / 2 - 1.0, 0))
    return {"X": X, "W": W, "D": D, "door": door_w, "garage": gfront, "pos": Vector(pos), "yaw": yaw, "name": hn, "porch": porch, "spec": spec,
            "door_x": door_x, "ridge": ridge, "features_built": built}

# ---------------------------------------------------------------- the street (two layouts)
BULB = Vector((0, 10, 0)); RB = 11.0
HARD_RECTS = []              # (a, b, width) segments the grass must avoid
box("Ground", (0, 0, -0.06), (400, 400, 0.1), GRASS)
if LAYOUT == "cul-de-sac":
    PAINT = solid("Paint", (0.9, 0.85, 0.5), 0.6)
    # main street: from the bulb (y=1) south into the cross street at CROSS_Y
    box("Road", (0, (1.0 + ROAD_MIN) / 2, 0.02), (7.0, 1.0 - ROAD_MIN, 0.04), ASPHALT)
    disc("Bulb", (BULB.x, BULB.y, 0.0), RB, 0.04, ASPHALT)
    _walk_end = CROSS_Y + 4.7                                   # main-street curbs/sidewalks stop at the cross street's sidewalk
    for sx in (-1, 1):
        box("Curb", (sx * 3.65, _walk_end / 2, 0.075), (0.3, -_walk_end, 0.15), CURB)
        box("Sidewalk", (sx * 4.55, _walk_end / 2, 0.07), (1.5, -_walk_end, 0.14), CONCRETE)
    ring("Bulb Curb", BULB, RB, RB + 0.3, -70, 250, 0.15, CURB, 64)
    ring("Bulb Sidewalk", BULB, RB + 0.3, RB + 1.8, -70, 250, 0.14, CONCRETE, 64)
    disc("Island Curb", (BULB.x, BULB.y, 0.0), 3.6, 0.15, CURB, 48)
    disc("Island Lawn", (BULB.x, BULB.y, 0.15), 3.3, 0.04, GRASS, 48)
    for y in list(range(int(CROSS_Y) + 9, -45, 10)) + [-40, -30, -20, -10, -4]:
        box("Center line", (0, y, 0.045), (0.15, 3.0, 0.005), PAINT)
    # the cross street (Phase 1 plat): east-west along CROSS_Y, the T open where the main street enters
    _cx = (CROSS_X[0] + CROSS_X[1]) / 2; _cl = CROSS_X[1] - CROSS_X[0]
    box("Cross Street", (_cx, CROSS_Y, 0.02), (_cl, 7.0, 0.04), ASPHALT)
    for sy, label in ((1, "N"), (-1, "S")):
        if sy > 0:   # north side: two runs, leaving the junction open for the main street
            for x0, x1, k in ((CROSS_X[0], -4.7, "W"), (4.7, CROSS_X[1], "E")):
                box("Cross Curb %s%s" % (label, k), ((x0 + x1) / 2, CROSS_Y + sy * 3.65, 0.075), (x1 - x0, 0.3, 0.15), CURB)
                box("Cross Sidewalk %s%s" % (label, k), ((x0 + x1) / 2, CROSS_Y + sy * 4.55, 0.07), (x1 - x0, 1.5, 0.14), CONCRETE)
        else:
            box("Cross Curb %s" % label, (_cx, CROSS_Y + sy * 3.65, 0.075), (_cl, 0.3, 0.15), CURB)
            box("Cross Sidewalk %s" % label, (_cx, CROSS_Y + sy * 4.55, 0.07), (_cl, 1.5, 0.14), CONCRETE)
    for x in range(int(CROSS_X[0]) + 6, int(CROSS_X[1]) - 5, 8):
        if abs(x) > 6:
            box("Cross Center line", (x, CROSS_Y, 0.045), (3.0, 0.15, 0.005), PAINT)
    HARD_RECTS.append((Vector((CROSS_X[0], CROSS_Y, 0)), Vector((CROSS_X[1], CROSS_Y, 0)), 7.0 + 2 * 4.9))   # grass keeps off it
    ROAD_Y = (ROAD_MIN, 1.0)
else:
    box("Road", (0, 0, 0.02), (7.0, 100, 0.04), ASPHALT)
    for sx in (-1, 1):
        box("Curb", (sx * 3.65, 0, 0.075), (0.3, 100, 0.15), CURB)
        box("Sidewalk", (sx * 4.55, 0, 0.07), (1.5, 100, 0.14), CONCRETE)
    for y in range(-46, 47, 8):
        box("Center line", (0, y, 0.045), (0.15, 3.0, 0.005), solid("Paint", (0.9, 0.85, 0.5), 0.6))
    ROAD_Y = (-50.0, 50.0)

def facing(pos):
    v = BULB - Vector(pos); return math.degrees(math.atan2(v.y, v.x)) + 90.0

def spot(angle_deg, dist):
    a = math.radians(angle_deg); return (BULB.x + dist * math.cos(a), BULB.y + dist * math.sin(a), 0.0)

# ---------------------------------------------------------------- lots: where each house goes and which way it faces
slots = []
N = len(HOUSE_SPECS)
if LAYOUT == "cul-de-sac":
    nb = min(N, 4)
    angles = [90.0] if nb == 1 else [145.0 - 110.0 * i / (nb - 1) for i in range(nb)]
    for bi, a in enumerate(angles):
        rnd.seed(zlib.crc32(("bulb|%d" % bi).encode("utf-8")))          # a bulb lot's jitter is its own, not the brief's
        p = spot(a, 25.0 + rnd.uniform(-1.0, 1.0)); slots.append((p, facing(p), "bulb"))
    for lot in STREET_LOTS[:max(0, N - nb)]:                     # houses beyond the bulb fill the plat in lot order
        slots.append((lot["pos"], lot["yaw"], lot["side"]))
    plat_lots = [dict(lot, house=None) for lot in STREET_LOTS]
    for i in range(nb, N):
        plat_lots[i - nb]["house"] = "H%d" % (i + 1)
    _next = next((l for l in plat_lots if l["house"] is None), None)
else:
    def straight_lot(i):
        ys = [-34.0, -12.0, 10.0, 32.0]
        side = -1 if i % 2 == 0 else 1
        return ((side * 22.0, ys[(i // 2) % 4], 0.0), 90.0 if side < 0 else 270.0, "west" if side < 0 else "east")
    for i in range(N):
        slots.append(straight_lot(i))
    p, yaw, side = straight_lot(N)
    plat_lots = [{"id": "S%d" % (i + 1), "pos": s[0], "yaw": s[1], "side": s[2], "house": "H%d" % (i + 1)} for i, s in enumerate(slots)]
    _next = {"id": "S%d" % (N + 1), "pos": p, "yaw": yaw, "side": side, "house": None}
    plat_lots.append(_next)

HOUSES = []
for i, (spec, (p, yaw, side)) in enumerate(zip(HOUSE_SPECS, slots)):
    h = house("H%d" % (i + 1), p, yaw, spec); h["side"] = side; HOUSES.append(h)

# ---------------------------------------------------------------- signboards on every empty lot (decision 25)
# A "coming soon" sign - two posts and a board - stands 7 m in front of the lot centre, facing the street. The world
# hangs the four candidate pictures on the node named "Lot <id> Sign Board"; the judge and the ledger see it by name.
SIGN_POST = solid("Sign Post", (0.24, 0.17, 0.11), 0.7)
SIGN_BOARD = solid("Sign Board", (0.93, 0.90, 0.84), 0.55)
def signboard(lot):
    yaw = math.radians(lot["yaw"]); fx, fy = math.sin(yaw), -math.cos(yaw)         # the front direction for this yaw
    cx, cy = lot["pos"][0] + fx * 7.0, lot["pos"][1] + fy * 7.0
    ax, ay = math.cos(yaw), math.sin(yaw)                                          # along the board (perpendicular to the front)
    for s in (-1, 1):
        box("Lot %s Sign Post %s" % (lot["id"], "L" if s < 0 else "R"), (cx + ax * s * 1.1, cy + ay * s * 1.1, 1.1), (0.12, 0.12, 2.2), SIGN_POST, None, yaw)
    box("Lot %s Sign Board" % lot["id"], (cx, cy, 1.55), (2.6, 0.06, 1.5), SIGN_BOARD, None, yaw)
    HARD_RECTS.append((Vector((cx - ax * 1.3, cy - ay * 1.3, 0)), Vector((cx + ax * 1.3, cy + ay * 1.3, 0)), 1.0))   # grass/props keep off
    return (round(cx, 3), round(cy, 3))
for lot in plat_lots:
    lot["sign"] = signboard(lot) if lot["house"] is None else None

# LOTS is exported into the world manifest (run-brief.py): every lot of the plat, occupied or empty, its sign, and the
# next free one. Builder space is Z-up (x, y); the GLB the world reads is Y-up with glb.z = -builder.y.
def _lot_rec(l):
    p = l["pos"]
    return {"id": l["id"], "x": round(p[0], 3), "y": round(p[1], 3), "yaw_deg": round(l["yaw"], 2), "side": l["side"],
            "house": l["house"], "sign": ("Lot %s Sign Board" % l["id"]) if l.get("sign") else None,
            "glb": [round(p[0], 3), 0.0, round(-p[1], 3)],
            "sign_glb": [l["sign"][0], 0.0, -l["sign"][1]] if l.get("sign") else None}
LOTS = {"frame": "builder Z-up (x,y); glb Y-up, glb.z = -y", "phase": PLAT_PHASE,
        "lots": [_lot_rec(l) for l in plat_lots],
        "next": _lot_rec(_next) if _next else None,
        "empty": sum(1 for l in plat_lots if l["house"] is None),
        "road_y": [ROAD_MIN, 1.0] if LAYOUT == "cul-de-sac" else [-50.0, 50.0],
        "cross_street": {"y": CROSS_Y, "x": list(CROSS_X)} if LAYOUT == "cul-de-sac" else None}

def slab(name, a, b, width, mt, z=0.0, h=0.12):
    a, b = Vector(a), Vector(b); d = b - a; L = d.length + 0.4
    HARD_RECTS.append((a, b, width))
    return box(name, ((a + b) / 2 + Vector((0, 0, z))), (L, width, h), mt, None, math.atan2(d.y, d.x))

def to_bulb_edge(p, r):
    v = Vector(p) - BULB; v.z = 0; return BULB + v.normalized() * r

def kerb_point(h, p):
    """Where a driveway/path from house h meets the street edge."""
    if h["side"] == "bulb":
        return to_bulb_edge(p, RB + 1.9)
    if h["side"] in ("north", "south"):                       # a lot on the cross street: the kerb is a y line
        return Vector((p.x, CROSS_Y + (5.4 if h["side"] == "north" else -5.4), 0))
    sx = -5.4 if h["side"] == "west" else 5.4
    return Vector((sx, p.y, 0))

for h in HOUSES:
    if h["garage"] is not None:
        slab(h["name"] + " Driveway", h["garage"], kerb_point(h, h["garage"]), 4.0, DRIVE, 0.075, 0.15)
    else:
        gp = h["X"] @ Vector((h["W"] / 2 + 2.2, -h["D"] / 2 + 1.0, 0))
        slab(h["name"] + " Drive", gp, kerb_point(h, gp), 3.8, GRAVEL, 0.075, 0.15)
    slab(h["name"] + " Path", h["door"], kerb_point(h, h["door"]), 1.3, PATH, 0.07, 0.14)

# ---------------------------------------------------------------- street furniture (procedural)
def lamp(pos):
    cyl("Lamp Pole", pos, 0.09, 5.0, STEEL)
    box("Lamp Arm", (pos[0], pos[1] + 0.6, 5.0), (0.12, 1.4, 0.12), STEEL)
    box("Lamp Head", (pos[0], pos[1] + 1.2, 4.85), (0.5, 0.7, 0.25), STEEL)
    box("Lamp Glass", (pos[0], pos[1] + 1.2, 4.72), (0.42, 0.62, 0.03), LAMP_GLOW)
    L = bpy.data.lights.new("Lamp Light", 'POINT'); L.energy = 400; L.color = (1.0, 0.85, 0.6); L.shadow_soft_size = 0.4; L.use_shadow = False
    lo = bpy.data.objects.new("Lamp Light", L); lo.location = (pos[0], pos[1] + 1.2, 4.6); COL.objects.link(lo)

if LAYOUT == "cul-de-sac":
    for lp in [(5.6, -36, 0), (-5.6, -14, 0), (12.5, 16, 0), (-12.5, 16, 0)]:
        lamp(lp)
else:
    for lp in [(5.6, -40, 0), (-5.6, -20, 0), (5.6, 0, 0), (-5.6, 20, 0), (5.6, 40, 0)]:
        lamp(lp)

def mailbox(pos, yaw_deg):
    X = Matrix.Translation(Vector(pos)) @ Matrix.Rotation(math.radians(yaw_deg), 4, 'Z')
    box("Mailbox Post", (0, 0, 0.5), (0.08, 0.08, 1.0), solid("MB post", (0.25, 0.18, 0.1), 0.7), X)
    box("Mailbox", (0, 0, 1.12), (0.5, 0.25, 0.24), solid("MB", (rnd.uniform(0.1, 0.5), rnd.uniform(0.1, 0.3), rnd.uniform(0.1, 0.5)), 0.4, 0.6), X)

for h in HOUSES:
    rnd.seed(zlib.crc32(("mailbox|" + h["name"]).encode("utf-8")))     # a mailbox keeps its colour between versions
    if h["side"] == "bulb":
        e = to_bulb_edge(h["door"], RB + 2.4); mailbox(e, math.degrees(math.atan2((e - BULB).y, (e - BULB).x)))
    elif h["side"] in ("north", "south"):
        sy = 5.9 if h["side"] == "north" else -5.9
        mailbox((h["door"].x + 1.5, CROSS_Y + sy, 0), 0 if h["side"] == "north" else 180)
    else:
        sx = -5.9 if h["side"] == "west" else 5.9
        mailbox((sx, h["door"].y - 1.5, 0), 90 if h["side"] == "west" else 270)

# ---------------------------------------------------------------- what the grass and the trees must avoid
def hard(x, y, margin=0.0):
    if abs(x) < 4.6 + margin and ROAD_Y[0] - margin < y < ROAD_Y[1] + margin: return True
    if LAYOUT == "cul-de-sac" and (Vector((x, y, 0)) - BULB).length < RB + 2.0 + margin: return True
    for h in HOUSES:
        l = h["X"].inverted() @ Vector((x, y, 0))
        gx = 6.0 if h["garage"] is not None else 0.0
        if abs(l.x) < h["W"] / 2 + gx + 1.0 + margin and -h["D"] / 2 - (2.6 if h["porch"] else 0) - 1.0 - margin < l.y < h["D"] / 2 + 1.0 + margin: return True
    p = Vector((x, y, 0))
    for (a, b, w) in HARD_RECTS:
        ab = b - a; t = max(0.0, min(1.0, (p - a).dot(ab) / max(1e-9, ab.length_squared)))
        if (p - (a + ab * t)).length < w / 2 + 0.3 + margin: return True
    return False

# ---------------------------------------------------------------- shelf models: trees, plants, props
def add_models():
    trees = []
    tries = 0
    while len(trees) < TREE_N and tries < 400:
        tries += 1
        x, y = rnd.uniform(-46, 46), rnd.uniform(-46, 46)
        if hard(x, y, 2.5) or any((Vector((x, y, 0)) - t).length < 7.0 for t in trees):
            continue
        trees.append(Vector((x, y, 0)))
        if rnd.random() < 0.6:
            place("fir_tree_01", (x, y, 0), height=rnd.uniform(8.0, 10.5))
        else:
            place("fir_sapling_medium", (x, y, 0), height=rnd.uniform(4.5, 6.5))
    if LAYOUT == "cul-de-sac":
        if not any(str(e.get("anchor")) == "island" for e in PLACEMENTS):     # a placed part takes the island's centre instead
            place("fir_sapling_medium", (BULB.x, BULB.y, 0.18), height=4.5)
        place("painted_wooden_bench", (BULB.x + 1.6, BULB.y - 1.6, 0.19), yaw_deg=225)
    for h in HOUSES:
        for k in range(3):
            lp = h["X"] @ Vector((rnd.uniform(-h["W"] / 2, h["W"] / 2), -h["D"] / 2 - rnd.uniform(0.9, 1.6), 0))
            place("grass_bermuda_01", lp, scale=0.55)
        dp = h["door"] + (h["X"].to_3x3() @ Vector((1.8, 0.3, 0)))
        place(rnd.choice(["planter_box_01", "planter_box_02", "planter_pot_clay"]), dp, yaw_deg=math.degrees(h["yaw"]))
        fp = h["X"] @ Vector((h["W"] / 2 + 0.8, -h["D"] / 2 - 0.5, 0))
        place("celandine_01", fp, scale=0.5)
        if h["spec"]["style"] == "modern":
            for k in range(2):
                bp = h["X"] @ Vector((-h["W"] / 2 - rnd.uniform(1.5, 3.5), rnd.uniform(-2, 2), 0))
                place("boulder_01", bp, scale=rnd.uniform(0.8, 1.2))
    with_garage = [h for h in HOUSES if h["garage"] is not None]
    if with_garage:
        h = rnd.choice(with_garage)
        mid = (h["garage"] + kerb_point(h, h["garage"])) / 2 + Vector((0, 0, 0.16))
        place("covered_car", tuple(mid), yaw_deg=math.degrees(h["yaw"]) + (0 if h["side"] == "bulb" else 0))
    _road0 = -45.0 if LAYOUT == "cul-de-sac" else ROAD_Y[0]      # pinned to the original street end: props never move when the street grows
    place("fire_hydrant", (4.9, _road0 + 33, 0), yaw_deg=0, scale=1.0)
    place("metal_trash_can", (-5.0, _road0 + 12, 0), scale=0.9)

def prop_radius(root):
    r = 0.0
    for c in root.children:
        r = max(r, max(c.dimensions.x, c.dimensions.y) * root.scale.x / 2)
    return max(r, 0.25)

def house_clear(h, p, margin):
    l = h["X"].inverted() @ Vector((p.x, p.y, 0))
    xmin, xmax = -h["W"] / 2 - margin, h["W"] / 2 + margin
    if h["garage"] is not None:
        gl = h["X"].inverted() @ h["garage"]
        if gl.x > 0: xmax = max(xmax, gl.x + 2.9 + margin)
        else: xmin = min(xmin, gl.x - 2.9 - margin)
    ymin, ymax = -h["D"] / 2 - (2.6 if h.get("porch") else 0.0) - margin, h["D"] / 2 + margin
    return xmin < l.x < xmax and ymin < l.y < ymax

def qa_props():
    roots = [o for o in COL.objects if o.type == 'EMPTY' and " @" in o.name]
    fixed, dropped = [], []
    for root in roots:
        r = prop_radius(root)
        for h in HOUSES:
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
                continue
            d = Vector(a.location) - Vector(b.location); d.z = 0
            need = prop_radius(a) + prop_radius(b) + 0.15
            if 0 < d.length < need:
                push = d.normalized() * (need - d.length)
                b.location = (b.location.x - push.x, b.location.y - push.y, b.location.z)
                fixed.append("%s <-> %s separated %.1f m" % (a.name, b.name, push.length))
    print("QA props: %d moved, %d dropped" % (len(fixed), len(dropped)))
    for f in fixed + dropped: print("   ", f)

if WANT_MODELS:
    rnd.seed(zlib.crc32(("grounds|%s|%d" % (LAYOUT, PLAT_PHASE)).encode("utf-8")))   # trees and props stay where they were unless a new house needs the spot
    add_models()
    qa_props()

# ---------------------------------------------------------------- warehouse parts at anchors (a painted GLB from the shelf, on the grounds)
PLACED = []          # {"glb", "anchor" (the one actually used), "size_m", "at"} -> status.json placed

def anchor_spot(anchor, size):
    """World position, yaw and the anchor actually used: island | yard:H<n> | roof:H<n> | door:H<n> | roadside."""
    kind, _, hn = anchor.partition(":")
    h = next((x for x in HOUSES if x["name"] == hn), None)
    if kind == "island" and LAYOUT == "cul-de-sac":
        return Vector((BULB.x, BULB.y, 0.19)), 0.0, anchor                                   # the island lawn's top
    if kind in ("yard", "roof", "door") and h:
        yaw, dx, D = math.degrees(h["yaw"]), h["door_x"], h["D"]
        if kind == "roof":
            return h["X"] @ Vector((0, 0, h["ridge"])), yaw, anchor                            # the ridge centre
        if kind == "door":
            return h["X"] @ Vector((dx + 1.1 + size / 2, -D / 2 - 0.35 - size / 2, 0.425 if h["porch"] else 0.0)), yaw, anchor   # beside the walk-up
        return h["X"] @ Vector((dx + 1.5 + size / 2, -D / 2 - (2.2 if h["porch"] else 0.0) - 3.0 - size / 2, 0.0)), yaw, anchor  # 3 m out, off the path
    used = "roadside" if kind == "roadside" else "roadside (no %s)" % anchor.replace(":", " ")     # e.g. "roadside (no yard H9)"
    lamps = [Vector(o.location) for o in COL.objects if o.name.startswith("Lamp Light")]      # the poles' geometry is baked; the lights carry the spot
    for i, y in enumerate(range(int(ROAD_Y[0]) + 6, int(ROAD_Y[1]) - 4, 3)):
        x = 6.3 if i % 2 == 0 else -6.3                                                          # just past the sidewalk, sides alternating
        if not hard(x, y, size / 2 + 0.3) and all((Vector((x, y, 0)) - Vector((l.x, l.y, 0))).length > size / 2 + 1.5 for l in lamps):
            return Vector((x, y, 0.0)), (90.0 if x > 0 else 270.0), used
    return None, 0.0, used

def place_glb(e):
    """Import a painted GLB, scale its longest side to size_m, stand it on the ground at its anchor, in the export collection."""
    path, anchor = str(e.get("glb") or ""), str(e.get("anchor") or "roadside")
    try: size = max(0.2, float(e.get("size_m") or 1.0))
    except (TypeError, ValueError): size = 1.0
    tag_ = lambda why: UNBUILT.append({"house": anchor, "phrase": "placement %s (%s)" % (os.path.basename(path) or "?", why)})
    if not os.path.isfile(path):
        return tag_("file not found")
    pos, yaw, used = anchor_spot(anchor, size)
    if pos is None:
        return tag_("no free spot along the road")
    was = {o.name for o in bpy.data.objects}
    try:
        bpy.ops.import_scene.gltf(filepath=path)
    except Exception as ex:
        return tag_("import failed: %s" % str(ex)[:80])
    new = [o for o in bpy.data.objects if o.name not in was]
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(b) for o in new if o.type == 'MESH' for b in o.bound_box]
    if not pts:
        for o in new: bpy.data.objects.remove(o, do_unlink=True)
        return tag_("no mesh inside")
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    s = size / max(1e-6, max(hi - lo))
    root = bpy.data.objects.new("Placed " + os.path.splitext(os.path.basename(path))[0], None); COL.objects.link(root)
    for o in new:
        if o.parent is None:
            o.parent = root                                       # root is at the origin now: nothing moves yet
        for col in list(o.users_collection):
            if col.name != COL.name: col.objects.unlink(o)
        if o.name not in COL.objects: COL.objects.link(o)
    try: yaw = float(e["yaw"]) if e.get("yaw") is not None else yaw
    except (TypeError, ValueError): pass
    root.matrix_world = (Matrix.Translation(pos) @ Matrix.Rotation(math.radians(yaw), 4, 'Z') @ Matrix.Diagonal((s, s, s, 1))
                         @ Matrix.Translation((-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z)))   # bbox centre on the anchor, bottom on the ground
    if not used.startswith("roof"):
        HARD_RECTS.append((Vector((pos.x, pos.y, 0)), Vector((pos.x, pos.y, 0)), size))       # the grass keeps off it
    PLACED.append({"glb": os.path.basename(path), "anchor": used, "size_m": size, "at": gl(pos)})

for e in PLACEMENTS:
    place_glb(e)

# ---------------------------------------------------------------- lawn grass (hair), kept off hard surfaces
def add_grass(count, children):
    bm = bmesh.new(); bmesh.ops.create_grid(bm, x_segments=90, y_segments=90, size=48.0)
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
SKIES = {"clear": ["abandoned_pathway", "aarfontein_dirt_road", "kloofendal_48d_partly_cloudy_puresky"],
         "cloudy": ["abandoned_church", "abandoned_hopper_terminal_01", "abandoned_parking"],
         "overcast": ["abandoned_hopper_terminal_03", "abandoned_church"],
         "sunset": ["aarfontein_dirt_road", "abandoned_pathway"]}
sky_key = str(brief.get("sky", "clear")).lower()
sky_id = None
for cand in SKIES.get(sky_key, []) + SKIES["clear"]:
    if glob.glob(os.path.join(SHELF, "hdris", cand, "*.hdr")):
        sky_id = cand; break
w = sc.world or bpy.data.worlds.new("World"); sc.world = w; w.use_nodes = True
nt = w.node_tree; nt.nodes.clear()
out = nt.nodes.new('ShaderNodeOutputWorld'); bg = nt.nodes.new('ShaderNodeBackground')
if sky_id:
    env = nt.nodes.new('ShaderNodeTexEnvironment')
    env.image = bpy.data.images.load(sorted(glob.glob(os.path.join(SHELF, "hdris", sky_id, "*.hdr")))[0], check_existing=True)
    nt.links.new(env.outputs['Color'], bg.inputs['Color'])
else:
    bg.inputs['Color'].default_value = (0.55, 0.7, 0.95, 1); FALLBACKS.append("sky -> plain blue (no HDRI on the shelf yet)")
bg.inputs['Strength'].default_value = 1.0
nt.links.new(bg.outputs[0], out.inputs[0])
sun = bpy.data.lights.new("Sun", 'SUN'); sun.energy = 3.5 if sky_key != "sunset" else 2.0; sun.angle = math.radians(1.5)
if sky_key == "sunset": sun.color = (1.0, 0.75, 0.5)
so = bpy.data.objects.new("Sun", sun); so.rotation_euler = (math.radians(50 if sky_key != "sunset" else 75), 0, math.radians(-40)); COL.objects.link(so)

def camera(name, pos, aim, lens):
    c = bpy.data.cameras.new(name); c.lens = lens; c.dof.use_dof = True; c.dof.focus_distance = (Vector(aim) - Vector(pos)).length; c.dof.aperture_fstop = 8.0
    o = bpy.data.objects.new(name, c); o.location = pos
    o.rotation_euler = (Vector(aim) - Vector(pos)).to_track_quat('-Z', 'Y').to_euler(); COL.objects.link(o); return o
if LAYOUT == "cul-de-sac":
    cam_air = camera("Cam Aerial", (36, -44, 24), (0, 8, 1.5), 32)
    cam_street = camera("Cam Street", (1.8, -40, 1.7), (-2, 12, 2.5), 26)
else:
    cam_air = camera("Cam Aerial", (40, -52, 26), (0, 0, 1.5), 30)
    cam_street = camera("Cam Street", (1.8, -46, 1.7), (-1, 20, 2.5), 26)
for h in HOUSES:
    fwd = h["X"].to_3x3() @ Vector((0, -1, 0))
    k = 1.35 if h["spec"]["stories"] >= 3 else 1.0          # three storeys: further back and higher, or the roof leaves the frame
    camera("Cam " + h["name"], tuple(h["pos"] + fwd * 24 * k + Vector((4, 0, 5 * k))), tuple(h["pos"] + Vector((0, 0, 2.0 * k))), 28)
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
for f in FALLBACKS:
    print("fallback:", f)
for u in UNBUILT:
    print("unbuilt: %s - %s" % (u["house"], u["phrase"]))
for p in PLACED:
    print("placed: %s at %s" % (p["glb"], p["anchor"]))
print("BUILT %s: %s, %d houses (%s), %d objects, %d shelf materials, %d shelf models, sky %s, %.1fs" % (
    NAME, LAYOUT, len(HOUSES), ", ".join("%s x%d%s" % (h["spec"]["style"], h["spec"]["stories"], " +" + str(len(h["features_built"])) if h["features_built"] else "") for h in HOUSES),
    len(COL.objects), len(_mats), len(_groups), sky_id, time.time() - T0))
