# make-walkable-v2.py - first-person walk for Maple Court in UPBGE 0.50, with a flight recorder.
# Replaces v1's logic bricks with one Python controller: time-based walking, run, smoothed mouse
# look with a pitch clamp, jump - and a log (walk-log.txt) written every second while you play so
# the walk can be checked after Esc instead of guessed at. Adds only CUL_* things; re-runnable.
# Controls: W A S D walk, SHIFT run, mouse look, SPACE jump, ESC stops. Start: hover the 3D view, press P.
import bpy, bmesh, math, os, time
from mathutils import Vector

T0 = time.time()
sc = bpy.context.scene
OUT = r"E:\Software Development\Video Game Development\03 Projects\Cul-de-sac"
COL = bpy.data.collections.get("Maple Court")
PFX = "CUL_"
LOG = os.path.join(OUT, "walk-log.txt")

def mark(stage):
    print("  %-40s %5.1fs" % (stage, time.time() - T0))

for o in [o for o in bpy.data.objects if o.name.startswith(PFX)]:
    bpy.data.objects.remove(o, do_unlink=True)
for t in [t for t in bpy.data.texts if t.name.startswith(PFX)]:
    bpy.data.texts.remove(t)

# ---------------------------------------------------------------- 1. physics on the neighbourhood
PROPS_HULL = ("boulder_01", "covered_car", "fire_hydrant", "metal_trash_can", "painted_wooden_bench",
              "planter_box", "planter_pot", "wine_barrel", "old_tyre", "wooden_ladder")
TREES = ("fir_tree_01", "fir_sapling_medium")
n_static = n_none = n_hull = n_trunk = 0
for o in COL.objects:
    if o.type != 'MESH':
        continue
    g = o.game
    if o.name.endswith(" Cutters") or o.hide_render:
        g.physics_type = 'NO_COLLISION'; n_none += 1; continue
    root = o.parent.name.split(" @")[0] if o.parent and " @" in o.parent.name else None
    if root is None:
        g.physics_type = 'STATIC'; g.use_collision_bounds = False; n_static += 1
    elif root.startswith(PROPS_HULL):
        g.physics_type = 'STATIC'; g.use_collision_bounds = True; g.collision_bounds_type = 'CONVEX_HULL'; n_hull += 1
    else:
        g.physics_type = 'NO_COLLISION'; n_none += 1
for root in [o for o in COL.objects if o.type == 'EMPTY' and o.name.split(" @")[0] in TREES]:
    r = 0.22 * root.scale.x * (1.6 if root.name.startswith("fir_tree") else 1.0)
    bm = bmesh.new(); bmesh.ops.create_cone(bm, cap_ends=True, segments=10, radius1=r, radius2=r, depth=8.0)
    bmesh.ops.translate(bm, vec=(0, 0, 4.0), verts=bm.verts)
    me = bpy.data.meshes.new(PFX + "Trunk"); bm.to_mesh(me); bm.free()
    t = bpy.data.objects.new(PFX + "Trunk", me); COL.objects.link(t)
    t.location = root.location; t.hide_render = True; t.display_type = 'WIRE'
    t.game.physics_type = 'STATIC'; t.game.use_collision_bounds = True; t.game.collision_bounds_type = 'CYLINDER'
    n_trunk += 1
mark("physics: %d static, %d hulls, %d trunks, %d no-collision" % (n_static, n_hull, n_trunk, n_none))

# ---------------------------------------------------------------- 2. player capsule + eye camera (camera sits above the capsule top)
bm = bmesh.new(); bmesh.ops.create_cone(bm, cap_ends=True, segments=12, radius1=0.3, radius2=0.3, depth=1.6)
me = bpy.data.meshes.new(PFX + "Player"); bm.to_mesh(me); bm.free()
player = bpy.data.objects.new(PFX + "Player", me); COL.objects.link(player)
player.location = (0.0, -42.0, 0.9)           # middle of the road, bottom of the street, facing north (local +Y)
player.hide_render = True; player.display_type = 'WIRE'
g = player.game
g.physics_type = 'CHARACTER'; g.use_actor = True
g.use_collision_bounds = True; g.collision_bounds_type = 'CAPSULE'; g.radius = 0.3
g.step_height = 0.35; g.jump_speed = 5.0; g.fall_speed = 40.0; g.max_slope = math.radians(50); g.jump_max = 1

cam = bpy.data.cameras.new(PFX + "Eye"); cam.lens = 24; cam.clip_start = 0.05; cam.clip_end = 700
eye = bpy.data.objects.new(PFX + "Eye", cam); COL.objects.link(eye)
eye.parent = player; eye.location = (0, 0, 0.86); eye.rotation_euler = (math.radians(90), 0, 0)   # just above the capsule top (0.8): eye 1.76 m
sc.camera = eye
mark("player + eye camera")

# ---------------------------------------------------------------- 3. the controller (runs every tick inside the game)
CONTROLLER = r'''
import bge, math, time, traceback
from mathutils import Vector, Euler
LOG_PATH = %r
SENS = 0.0012          # radians per pixel of mouse travel (0.0025 was a 70-degree whip on the first playtest)
WALK, RUN = 3.6, 6.5   # metres per second
cont = bge.logic.getCurrentController(); own = cont.owner
G = bge.logic.globalDict
try:
    if "t0" not in G:
        G["t0"] = time.time(); G["last_log"] = 0.0; G["pitch"] = 0.0; G["ticks"] = 0; G["warm"] = 0
        G["log"] = open(LOG_PATH, "a")
        G["log"].write("=== walk start %%s\n" %% time.ctime()); G["log"].flush()
        bge.render.showMouse(False)
    w, h = bge.render.getWindowWidth(), bge.render.getWindowHeight()
    G["ticks"] += 1
    ch = bge.constraints.getCharacter(own)
    kb = bge.logic.keyboard.inputs
    def down(k): return kb[k].active
    fwd = (1 if down(bge.events.WKEY) else 0) - (1 if down(bge.events.SKEY) else 0)
    side = (1 if down(bge.events.DKEY) else 0) - (1 if down(bge.events.AKEY) else 0)
    speed = RUN if down(bge.events.LEFTSHIFTKEY) else WALK
    if fwd or side:
        d = Vector((side, fwd, 0.0)); d.normalize()
        ch.walkDirection = own.worldOrientation @ (d * speed / 60.0)
    else:
        ch.walkDirection = Vector((0.0, 0.0, 0.0))
    if kb[bge.events.SPACEKEY].activated and ch.onGround:
        ch.jump()
    mx, my = bge.logic.mouse.position
    # Look = movement since the LAST tick, not distance from centre: a re-centre that lands a tick late
    # would otherwise be applied twice (v2 first playtest: one 50 px nudge turned the view 70 degrees).
    if G["warm"] < 3 or G.get("skip", 0) > 0:      # first ticks, and the 2 ticks after a re-centre: read, don't steer
        G["warm"] += 1; G["skip"] = max(0, G.get("skip", 0) - 1); G["pmx"], G["pmy"] = mx, my
    else:
        dx = (mx - G["pmx"]) * w; dy = (my - G["pmy"]) * h
        G["pmx"], G["pmy"] = mx, my
        if abs(dx) < w * 0.2 and abs(dy) < h * 0.2 and (dx or dy):
            own.applyRotation((0.0, 0.0, -dx * SENS), True)
            G["pitch"] = max(-1.25, min(1.25, G["pitch"] - dy * SENS))
            own.children["CUL_Eye"].localOrientation = Euler((math.pi / 2 + G["pitch"], 0.0, 0.0), "XYZ")
    if abs(mx - 0.5) > 0.25 or abs(my - 0.5) > 0.25:      # keep the cursor inside the window; re-centre rarely
        bge.render.setMousePosition(w // 2, h // 2); G["skip"] = 2
    now = time.time()
    if now - G["last_log"] >= 1.0:
        G["last_log"] = now
        p = own.worldPosition; f = own.worldOrientation.col[1]
        G["log"].write("t=%%5.1f pos=(%%6.1f, %%6.1f, %%5.2f) heading=(%%5.2f, %%5.2f) pitch=%%5.2f fps=%%4.0f ground=%%s keys=%%s\n" %% (
            now - G["t0"], p.x, p.y, p.z, f.x, f.y, G["pitch"], bge.logic.getAverageFrameRate(), ch.onGround,
            "".join(k for k, e in (("W", bge.events.WKEY), ("A", bge.events.AKEY), ("S", bge.events.SKEY), ("D", bge.events.DKEY)) if down(e)) or "-"))
        G["log"].flush()
except Exception:
    try:
        G["log"].write("ERROR tick %%s:\n%%s" %% (G.get("ticks"), traceback.format_exc())); G["log"].flush()
    except Exception:
        pass
''' % (LOG,)
txt = bpy.data.texts.new(PFX + "controller.py"); txt.write(CONTROLLER)
with bpy.context.temp_override(active_object=player, object=player, selected_objects=[player]):
    bpy.ops.logic.sensor_add(type="ALWAYS", name="Tick", object=player.name)
    bpy.ops.logic.controller_add(type="PYTHON", name="FPS", object=player.name)
s = player.game.sensors["Tick"]; s.use_pulse_true_level = True; s.tick_skip = 0
c = player.game.controllers["FPS"]; c.mode = 'SCRIPT'; c.text = txt
s.link(c)
mark("python controller + flight recorder")

# ---------------------------------------------------------------- 4. game settings + the viewport the game will use
lawn = bpy.data.objects.get("Lawn")          # 240k grass strands cost ~25 fps in-game (recorder: 13-43 fps); walk file goes without
if lawn:
    for m in [m for m in lawn.modifiers if m.type == 'PARTICLE_SYSTEM']:
        lawn.modifiers.remove(m)
for k, val in (("taa_samples", 4), ("shadow_ray_count", 1), ("shadow_step_count", 2), ("use_raytracing", False)):
    try: setattr(sc.eevee, k, val)
    except Exception as e: print("  eevee", k, e)
gs = sc.game_settings
gs.physics_engine = 'BULLET'; gs.physics_gravity = 9.8; gs.fps = 60; gs.use_frame_rate = True
gs.show_mouse = False; gs.show_framerate_profile = False
try: gs.samples = 'SAMPLES_8'
except Exception as e: print("  samples:", e)
for win in bpy.data.window_managers[0].windows:
    for area in win.screen.areas:
        if area.type == 'VIEW_3D':
            sp = area.spaces.active
            sp.shading.type = 'RENDERED'          # the embedded game renders with the viewport's shading: RENDERED = real sky + sun
            sp.shading.use_scene_world = True; sp.shading.use_scene_lights = True
            sp.region_3d.view_perspective = 'CAMERA'; sp.overlay.show_overlays = False
mark("game settings + RENDERED viewport on the eye")

path = os.path.join(OUT, "maple-court-v2-walk.blend")
win = bpy.data.window_managers[0].windows[0]
with bpy.context.temp_override(window=win):
    res = bpy.ops.wm.save_as_mainfile(filepath=path)
mark("saved %s %s" % (os.path.basename(path), res))
f = player.matrix_world.to_3x3() @ Vector((0, 1, 0))
print("spawn %s facing (%.1f, %.1f) -> the street runs north: %s" % (tuple(round(v, 1) for v in player.location), f.x, f.y, "OK" if f.y > 0.9 else "WRONG"))
print("WALKABLE v2 ready. total %.1fs" % (time.time() - T0))
