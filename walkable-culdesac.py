# walkable-culdesac.py - turns the open Maple Court scene into a first-person walk (UPBGE 0.50).
# Sent through the Claude Bridge. Adds CUL_Player (character physics, capsule) + CUL_Cam,
# a logic brick pair (Always -> Python module) and the culwalk.py text block that reads
# WASD / mouse / Space / Shift. Everything else becomes static collision. Saves a NEW file.
# Property names below were read off the live 0.50 API on 2026-09-02 (drive-upbge facts file).
import bpy, bmesh, math, os, time
from mathutils import Vector

T0 = time.time()
def mark(s): print("  [%5.1fs] %s" % (time.time() - T0, s))
sc = bpy.context.scene
OUT = r"E:\Software Development\Video Game Development\03 Projects\Cul-de-sac"

# ---- clear only our own prefix (re-runnable) ----
for o in [o for o in bpy.data.objects if o.name.startswith("CUL_")]:
    bpy.data.objects.remove(o, do_unlink=True)
if "culwalk.py" in bpy.data.texts:
    bpy.data.texts.remove(bpy.data.texts["culwalk.py"])
COL = bpy.data.collections.get("Maple Court") or sc.collection

# ---- static collision for the world, cheap shapes where a triangle mesh is waste ----
n_static = n_none = n_cyl = 0
for o in sc.objects:
    if o.type != 'MESH' or o.name.startswith("CUL_"):
        continue
    g = o.game
    root = o.parent.name if o.parent else ""
    if any(k in (o.name + root) for k in ("grass_bermuda", "celandine", "Lawn", " WG", " WM", "Cutters", "Center line", "GD line", "Lamp Glass")):
        g.physics_type = 'NO_COLLISION'; n_none += 1
    elif any(k in root for k in ("fir_tree", "fir_sapling")):
        g.physics_type = 'STATIC'; g.use_collision_bounds = True; g.collision_bounds_type = 'CYLINDER'; n_cyl += 1
    else:
        g.physics_type = 'STATIC'; g.use_collision_bounds = False; n_static += 1   # no bounds = triangle mesh
mark("collision: %d static mesh, %d tree cylinders, %d no-collision" % (n_static, n_cyl, n_none))

# ---- the player: an invisible capsule with character physics, camera at eye height ----
bm = bmesh.new()
bmesh.ops.create_cone(bm, cap_ends=True, segments=12, radius1=0.35, radius2=0.35, depth=1.8)
me = bpy.data.meshes.new("CUL_Player"); bm.to_mesh(me); bm.free()
player = bpy.data.objects.new("CUL_Player", me); COL.objects.link(player)
player.location = (1.8, -40.0, 0.95)
g = player.game
g.physics_type = 'CHARACTER'; g.use_collision_bounds = True; g.collision_bounds_type = 'CAPSULE'
g.step_height = 0.35; g.jump_speed = 6.0; g.fall_speed = 55.0; g.max_slope = math.radians(50); g.jump_max = 1
g.use_actor = True
cam_data = bpy.data.cameras.new("CUL_Cam"); cam_data.lens = 24; cam_data.clip_end = 600
cam = bpy.data.objects.new("CUL_Cam", cam_data); COL.objects.link(cam)
cam.parent = player; cam.location = (0, 0, 0.65); cam.rotation_euler = (math.radians(90), 0, 0)   # look down +Y
sc.camera = cam
mark("player + camera")

# ---- the walk script, stored inside the .blend so the file is self-contained ----
WALK = '''import bge, math
from bge import logic, render, events
from mathutils import Matrix, Vector

SPEED, RUN, SENS = 0.09, 1.9, 0.0028     # per-tick metres, shift multiplier, radians per pixel

def main(cont):
    own = cont.owner
    cam = [c for c in own.children if c.name == "CUL_Cam"][0]
    if "st" not in own:
        own["st"] = {"pitch": 0.0}
        own.visible = False
        render.showMouse(False)
        logic.mouse.position = (0.5, 0.5)
        return
    st = own["st"]
    mx, my = logic.mouse.position
    logic.mouse.position = (0.5, 0.5)
    w, h = render.getWindowWidth(), render.getWindowHeight()
    own.applyRotation((0.0, 0.0, -(mx - 0.5) * w * SENS), False)
    st["pitch"] = max(-1.45, min(1.45, st["pitch"] - (my - 0.5) * h * SENS))
    cam.localOrientation = Matrix.Rotation(math.pi / 2 + st["pitch"], 3, 'X')

    kb = logic.keyboard.inputs
    on = lambda k: kb[k].active
    fwd = (1 if on(events.WKEY) or on(events.UPARROWKEY) else 0) - (1 if on(events.SKEY) or on(events.DOWNARROWKEY) else 0)
    side = (1 if on(events.DKEY) or on(events.RIGHTARROWKEY) else 0) - (1 if on(events.AKEY) or on(events.LEFTARROWKEY) else 0)
    v = own.getAxisVect((0, 1, 0)) * fwd + own.getAxisVect((1, 0, 0)) * side
    v.z = 0.0
    if v.length > 0:
        v.normalize()
    speed = SPEED * (RUN if on(events.LEFTSHIFTKEY) else 1.0)
    char = bge.constraints.getCharacter(own)
    char.walkDirection = v * speed
    if on(events.SPACEKEY) and char.onGround:
        char.jump()
'''
txt = bpy.data.texts.new("culwalk.py"); txt.write(WALK)

# ---- logic bricks: Always (every frame) -> Python module culwalk.main ----
win0 = bpy.data.window_managers[0].windows[0]
bpy.context.view_layer.objects.active = player
with bpy.context.temp_override(window=win0, active_object=player, object=player, selected_objects=[player]):
    bpy.ops.logic.sensor_add(type='ALWAYS', name="tick", object=player.name)
    bpy.ops.logic.controller_add(type='PYTHON', name="walk", object=player.name)
sens = player.game.sensors["tick"]; sens.use_pulse_true_level = True
ctrl = player.game.controllers["walk"]; ctrl.mode = 'MODULE'; ctrl.module = "culwalk.main"
sens.link(ctrl)
mark("logic bricks")

# ---- game settings ----
gs = sc.game_settings
gs.show_mouse = False; gs.fps = 60; gs.use_frame_rate = True
gs.physics_gravity = 9.8; gs.show_framerate_profile = True
try: gs.use_viewport_render = True
except Exception: pass

for win in bpy.data.window_managers[0].windows:
    for area in win.screen.areas:
        if area.type == 'VIEW_3D':
            sp = area.spaces.active; sp.shading.type = 'MATERIAL'; sp.region_3d.view_perspective = 'CAMERA'

path = os.path.join(OUT, "maple-court-v1-walk.blend")
win = bpy.data.window_managers[0].windows[0]
with bpy.context.temp_override(window=win):
    bpy.ops.wm.save_as_mainfile(filepath=path)
mark("saved " + os.path.basename(path) + " (%d KB)" % (os.path.getsize(path) // 1024))
print("WALKABLE: player at", tuple(player.location), "| camera", sc.camera.name, "| controls: WASD / mouse / Space / Shift, Esc quits")
