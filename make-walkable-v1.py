# make-walkable-v1.py - turns the open Maple Court scene into a first-person walk for UPBGE 0.50.
# Sent through the Claude Bridge AFTER build-culdesac-v1.py. Adds only CUL_* objects; re-runnable.
# Controls in game: W A S D walk, mouse look, SPACE jump, ESC stops.  Start: mouse over the 3D view, press P.
import bpy, bmesh, math, os, time
from mathutils import Vector

T0 = time.time()
sc = bpy.context.scene
OUT = r"E:\Software Development\Video Game Development\03 Projects\Cul-de-sac"
COL = bpy.data.collections.get("Maple Court")
PFX = "CUL_"

def mark(stage):
    print("  %-28s %5.1fs" % (stage, time.time() - T0))

# ---------------------------------------------------------------- 0. clear only our own objects
for o in [o for o in bpy.data.objects if o.name.startswith(PFX)]:
    bpy.data.objects.remove(o, do_unlink=True)

# ---------------------------------------------------------------- 1. physics for what is already there
# Everything built by the script is a static collider by default (STATIC + triangle mesh).
# Exceptions: hidden cutters, and the shelf models - plants get no collision, props get a hull,
# trees get an invisible trunk cylinder so you bump the trunk, not the canopy.
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

# ---------------------------------------------------------------- 2. the player (character capsule) + eye camera
bm = bmesh.new(); bmesh.ops.create_cone(bm, cap_ends=True, segments=12, radius1=0.35, radius2=0.35, depth=1.8)
me = bpy.data.meshes.new(PFX + "Player"); bm.to_mesh(me); bm.free()
player = bpy.data.objects.new(PFX + "Player", me); COL.objects.link(player)
player.location = (1.8, -40.0, 0.95)          # on the road, facing north up the street (local +Y = forward)
player.hide_render = True                      # invisible in game, still collides
player.display_type = 'WIRE'
g = player.game
g.physics_type = 'CHARACTER'; g.use_actor = True
g.use_collision_bounds = True; g.collision_bounds_type = 'CAPSULE'; g.radius = 0.35
g.step_height = 0.35; g.jump_speed = 5.0; g.fall_speed = 40.0; g.max_slope = math.radians(50); g.jump_max = 1
g.lock_rotation_x = True; g.lock_rotation_y = True

cam = bpy.data.cameras.new(PFX + "Eye"); cam.lens = 24; cam.clip_end = 600
eye = bpy.data.objects.new(PFX + "Eye", cam); COL.objects.link(eye)
eye.parent = player; eye.location = (0, 0, 0.65); eye.rotation_euler = (math.radians(90), 0, 0)
sc.camera = eye
mark("player + eye camera")

# ---------------------------------------------------------------- 3. logic bricks: keys -> character motion, mouse -> look
def brick(ob, sensor_type, name, actuator_type, setup_sensor, setup_actuator):
    with bpy.context.temp_override(active_object=ob, object=ob, selected_objects=[ob]):   # the logic ops poll for an active object
        bpy.ops.logic.sensor_add(type=sensor_type, name=name, object=ob.name)
        bpy.ops.logic.controller_add(type="LOGIC_AND", name=name, object=ob.name)
        bpy.ops.logic.actuator_add(type=actuator_type, name=name, object=ob.name)
    s, c, a = ob.game.sensors[name], ob.game.controllers[name], ob.game.actuators[name]
    setup_sensor(s); setup_actuator(a)
    s.link(c); a.link(c)

STEP = 0.07     # metres per logic tick (60/s) = 4.2 m/s, a brisk walk
def key(k):
    return lambda s: setattr(s, "key", k)
def move(dx, dy):
    def f(a):
        a.mode = "OBJECT_CHARACTER"; a.offset_location = (dx, dy, 0.0)
    return f
def jump(a):
    a.mode = "OBJECT_CHARACTER"; a.use_character_jump = True

brick(player, "KEYBOARD", "Forward", "MOTION", key("W"), move(0, STEP))
brick(player, "KEYBOARD", "Back", "MOTION", key("S"), move(0, -STEP))
brick(player, "KEYBOARD", "Right", "MOTION", key("D"), move(STEP, 0))
brick(player, "KEYBOARD", "Left", "MOTION", key("A"), move(-STEP, 0))
brick(player, "KEYBOARD", "Jump", "MOTION", key("SPACE"), jump)

def mouse_move(s):
    s.mouse_event = 'MOVEMENT'; s.use_pulse_true_level = True
def look_yaw(a):
    a.mode = 'LOOK'; a.use_axis_y = False; a.sensitivity_x = 1.5
def look_pitch(a):
    a.mode = 'LOOK'; a.use_axis_x = False; a.sensitivity_y = 1.5; a.min_y = math.radians(-80); a.max_y = math.radians(80)
brick(player, "MOUSE", "Turn", "MOUSE", mouse_move, look_yaw)
brick(eye, "MOUSE", "Pitch", "MOUSE", mouse_move, look_pitch)
mark("logic bricks (WASD, jump, mouse look)")

# ---------------------------------------------------------------- 4. game settings + view
gs = sc.game_settings
gs.physics_engine = 'BULLET'; gs.physics_gravity = 9.8; gs.fps = 60; gs.use_frame_rate = True
gs.show_mouse = False; gs.show_framerate_profile = False; gs.use_viewport_render = False
for win in bpy.data.window_managers[0].windows:
    for area in win.screen.areas:
        if area.type == 'VIEW_3D':
            sp = area.spaces.active; sp.shading.type = 'MATERIAL'; sp.region_3d.view_perspective = 'CAMERA'
            sp.overlay.show_overlays = False
mark("game settings + viewport on the eye camera")

# ---------------------------------------------------------------- 5. save as a NEW file
path = os.path.join(OUT, "maple-court-v1-walk.blend")
win = bpy.data.window_managers[0].windows[0]
with bpy.context.temp_override(window=win):
    res = bpy.ops.wm.save_as_mainfile(filepath=path)
mark("saved %s %s" % (os.path.basename(path), res))
print("WALKABLE: hover the 3D view and press P. W A S D walk, mouse looks, SPACE jumps, ESC stops. total %.1fs" % (time.time() - T0))
