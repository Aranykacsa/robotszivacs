"""Blender 4.x/5.x blockout. Run: blender --background --python build_vacuum_robot.py
Optional script arguments after --: --output-dir DIR --godot-bin PATH --skip-godot
Destructively replaces the current scene, but never overwrites robotszivacs.blend.
Coordinates: X right, Y front, Z up. All design inputs below are millimeters.
"""
from __future__ import annotations

import argparse
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback

import bpy
import bmesh
from mathutils import Vector

MM = 0.001
VISUALS = []
COLLIDERS = []
CHASSIS = None
LOG = None
STEP = 0

ASSUMPTIONS = """- Origin is the board-plane datum (0,0,0); chassis bottom is Z=2 mm.
- +Y is front. Chassis envelope is 120 X × 140 Y × 4 Z mm.
- Wheels have X axles at X=±60, Y=±48, Z=11 mm; side slots have 1 mm clearance.
- Roller diameter is 18 mm; its center is Y=-79.5, Z=9 mm, just behind the rear edge.
- Sensor bodies extend outboard (X=±78.5 mm) so their -Z optical axes clear wheels.
  They are blockout modules; mounting brackets, shafts, wiring and vacuum ducting are omitted.
- Battery and ESP32 bases are Z=18 mm to clear drivetrain; battery sits behind the central fan.
- Skirt is a 2 mm thick rectangular sponge ring, centered at Z=1 mm, touching the board.
- Unspecified masses and voltages use -1 (unknown), never fabricated rated values.
  Electronics supply assignments are distinguished from datasheet ratings in custom properties.
- Pogo/contact total mass is split equally across four visual pieces; wheel, drive motor,
  and sensor totals are split equally across their respective four instances.
- Collision proxies are zero-mass helpers. Godot -convcolonly removes their visible surfaces;
  Blender displays them as wireframes and excludes them from rendering.
- The Godot demo is a static inspection scene. Imported static collision bodies must be
  replaced/reparented with convex shapes under one RigidBody3D before dynamic simulation.
- This is a packaging blockout, not a validated vacuum seal, adhesion or drivetrain design.
"""


def log(message):
    LOG.write(message + "\n")
    LOG.flush()
    print(message, flush=True)


def bounds(obj):
    bpy.context.view_layer.update()
    points = [obj.matrix_world @ Vector(p) for p in obj.bound_box]
    low = Vector(tuple(min(p[i] for p in points) for i in range(3)))
    high = Vector(tuple(max(p[i] for p in points) for i in range(3)))
    return low, high


def triple(value):
    return "(" + ", ".join(f"{v:.4f}" for v in value) + ")"


def record(obj):
    global STEP
    STEP += 1
    low, high = bounds(obj)
    log(f"{STEP:03d}. `{obj.name}` | mesh `{obj.data.name}` | "
        f"world dimensions mm {triple((high-low)/MM)} | "
        f"world origin mm {triple(obj.matrix_world.translation/MM)} | "
        f"bounds mm {triple(low/MM)} → {triple(high/MM)} | "
        f"scale {triple(obj.scale)} | mass g {obj['Weight']} | "
        f"voltage V {obj['Voltage']} | type {obj['Part Type']}")


def material(name, color, metallic=0.0, roughness=0.6):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value = (*color, 1)
    shader.inputs['Metallic'].default_value = metallic
    shader.inputs['Roughness'].default_value = roughness
    return mat


def finish(obj, name, mass, voltage, kind, mat, collision=False, **properties):
    obj.name = name
    obj.data.name = name + '_Mesh'
    if CHASSIS is not None:
        world = obj.matrix_world.copy()
        obj.parent = CHASSIS
        obj.matrix_world = world
    obj['Weight'] = float(mass)
    obj['Voltage'] = float(voltage)
    obj['Part Type'] = kind
    obj['Weight Unit'] = 'grams; -1 = unspecified'
    obj['Voltage Unit'] = 'volts; -1 = unspecified/not applicable'
    obj['Mass Known'] = mass >= 0
    for key, value in properties.items():
        obj[key] = value
    obj.data.materials.append(mat)
    if collision:
        obj.display_type = 'WIRE'
        obj.hide_render = True
        obj['Physics Helper'] = True
        COLLIDERS.append(obj)
    else:
        VISUALS.append(obj)
    record(obj)
    return obj


def box(name, size, center, mass=-1, voltage=-1, kind='Component', mat=None,
        collision=False, **properties):
    bpy.ops.mesh.primitive_cube_add(size=1, location=tuple(v*MM for v in center))
    obj = bpy.context.object
    obj.dimensions = tuple(v*MM for v in size)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return finish(obj, name, mass, voltage, kind, mat, collision, **properties)


def cylinder(name, diameter, length, center, axis='Z', mass=-1, voltage=-1,
             kind='Component', mat=None, collision=False, **properties):
    rotation = {'Z': (0, 0, 0), 'X': (0, math.pi/2, 0),
                'Y': (math.pi/2, 0, 0)}[axis]
    bpy.ops.mesh.primitive_cylinder_add(vertices=12 if collision else 32,
        radius=diameter*MM/2, depth=length*MM,
        location=tuple(v*MM for v in center), rotation=rotation)
    obj = bpy.context.object
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    return finish(obj, name, mass, voltage, kind, mat, collision, **properties)


def plate_mesh(name, xs, ys, cells, bottom, top):
    """One manifold, connected grid solid, with no internal faces or boolean debris."""
    vertices, faces, indices = [], [], {}
    def vid(i, j, k):
        key = (i, j, k)
        if key not in indices:
            indices[key] = len(vertices)
            vertices.append((xs[i]*MM, ys[j]*MM, (bottom if k == 0 else top)*MM))
        return indices[key]
    for i, j in sorted(cells):
        faces.append([vid(i,j,0), vid(i,j+1,0), vid(i+1,j+1,0), vid(i+1,j,0)])
        faces.append([vid(i,j,1), vid(i+1,j,1), vid(i+1,j+1,1), vid(i,j+1,1)])
        for neighbor, edge in [((i,j-1), ((i,j),(i+1,j))),
                                ((i+1,j), ((i+1,j),(i+1,j+1))),
                                ((i,j+1), ((i+1,j+1),(i,j+1))),
                                ((i-1,j), ((i,j+1),(i,j)))]:
            if neighbor not in cells:
                a,b = edge
                faces.append([vid(*a,0), vid(*b,0), vid(*b,1), vid(*a,1)])
    mesh = bpy.data.meshes.new(name + '_Mesh')
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def construct():
    global CHASSIS
    gray = material('Chassis graphite', (0.16,0.20,0.25))
    black = material('Silicone rubber', (0.025,0.03,0.04), roughness=0.9)
    sponge = material('Neoprene skirt', (0.08,0.11,0.13), roughness=1)
    silver = material('Motor aluminum', (0.55,0.62,0.68), 0.7)
    gold = material('Gearbox brass', (0.60,0.39,0.09), 0.65)
    cloth = material('Microfiber teal', (0.04,0.65,0.65), roughness=1)
    red = material('LiPo red', (0.75,0.06,0.08))
    green = material('ESP32 green', (0.03,0.40,0.13))
    purple = material('ESC purple', (0.39,0.09,0.64))
    blue = material('H bridge blue', (0.04,0.25,0.85))
    orange = material('MOSFET orange', (0.95,0.30,0.04))
    sensor = material('IR module navy', (0.035,0.08,0.24))
    copper = material('Copper contacts', (0.8,0.35,0.13), 0.8)
    proxy = material('Collision helper', (0.95,0.1,0.6))

    cells = {(i,j) for i in range(3) for j in range(5)
             if not (i in (0,2) and j in (1,3))}
    chassis = plate_mesh('Chassis', [-60,-48.5,48.5,60],
                         [-70,-60.5,-35.5,35.5,60.5,70], cells, 2, 6)
    finish(chassis, 'Chassis', 100, -1, 'Unified chassis', gray,
           Ground_Clearance_mm=2, Datum='Board plane; bottom face +2 mm')
    CHASSIS = chassis
    ring = plate_mesh('Vacuum_Skirt', [-44,-40,40,44], [-33,-29,29,33],
                      {(i,j) for i in range(3) for j in range(3) if (i,j)!=(1,1)}, 0, 2)
    finish(ring, 'Vacuum_Skirt', -1, -1, 'Neoprene sealing sponge ring', sponge,
           Thickness_mm=2)
    cylinder('Vacuum_Motor_BLDC',40,40,(0,0,26),mass=60,voltage=7.4,
             kind='BLDC vacuum motor',mat=silver, Airflow='+Z',
             Voltage_Basis='Assigned 2S supply; motor rating unspecified')
    for side, x in [('Left',-60),('Right',60)]:
        for end,y in [('Front',48),('Rear',-48)]:
            cylinder(f'Wheel_{side}_{end}',22,21,(x,y,11),'X',7.5,-1,
                     'JSumo Mini Sumo silicone wheel',black, Axle='X')
            box(f'Drive_Motor_{side}_{end}',(36,12,10),
                (math.copysign(31.25,x),y,11),10,7.4,'N20 metal gear motor',gold,
                Voltage_Basis='Assigned 2S supply; rated voltage unspecified', Axle='X')
    cylinder('Microfiber_Roller',18,120,(0,-79.5,9),'X',5,-1,'Microfiber roller',cloth)
    box('Wiper_Motor_N20',(36,12,10),(78.25,-79.5,9),10,7.4,'N20 wiper motor',gold,
        Voltage_Basis='Assigned 2S supply; rated voltage unspecified', Axle='X')
    box('Battery_2S_LiPo',(55,30,15),(0,-36,25.5),40,7.4,'2S LiPo battery',red,
        Capacity_mAh=500, Discharge_C_Min=30)
    box('ESP32_S3',(53,28,12),(0,36,24),10,3.3,'Microcontroller',green,
        Voltage_Basis='Logic voltage; board power input unspecified')
    box('BLHeli_ESC',(12,25,5),(39,-7,9.5),10,7.4,'BLDC ESC',purple,
        Current_A_Min=20,Current_A_Max=30,Voltage_Basis='2S power rail')
    box('TB6612FNG',(20,20,5),(37,22,9.5),5,7.4,'Dual H bridge',blue,
        Logic_Voltage=3.3,Voltage_Basis='2S motor rail; 3.3 V logic',
        Wiring='Two motors per channel; verify aggregate stall current separately')
    box('D4184_MOSFET',(17,34,12),(-39,0,13),5,7.4,'Wiper MOSFET switch',orange,
        Voltage_Basis='Switched 2S rail; module logic requirements unspecified')
    for side,x in [('Left',-78.5),('Right',78.5)]:
        for end,y in [('Front',54),('Rear',-54)]:
            box(f'TCRT5000_{side}_{end}',(14,32,15),(x,y,9.5),3.75,-1,
                'IR reflective module',sensor,Detection_Direction='World -Z',
                Optical_Axis_World=[0.0,0.0,-1.0],Board_Gap_mm=2)
    for side,x in [('Left',-18),('Right',18)]:
        box(f'Charging_Plate_{side}',(7,0.8,3),(x,70.4,4),1.25,-1,
            'Copper charging plate',copper)
        cylinder(f'Pogo_Pin_{side}',2,4,(x,72.8,4),'Y',1.25,-1,
                 'Spring charging contact',gold,Contact_Direction='+Y')

    # Collision helpers: disjoint boxes preserve wheel slots and skirt opening.
    box('Chassis_Core-convcolonly',(97,140,4),(0,0,4),0,-1,'Collision',proxy,True)
    for x in (-54.25,54.25):
        for y,depth in [(-65.25,9.5),(0,71),(65.25,9.5)]:
            box(f'Chassis_Rail_{x}_{y}-convcolonly',(11.5,depth,4),(x,y,4),
                0,-1,'Collision',proxy,True)
    for name,size,center in [
        ('Left',(4,66,2),(-42,0,1)),('Right',(4,66,2),(42,0,1)),
        ('Front',(80,4,2),(0,31,1)),('Rear',(80,4,2),(0,-31,1))]:
        box(f'Skirt_{name}-convcolonly',size,center,0,-1,'Collision',proxy,True)
    for obj in list(VISUALS):
        if obj in (CHASSIS,ring):
            continue
        low,high = bounds(obj)
        center = (low+high)/(2*MM)
        size = (high-low)/MM
        name = obj.name + '-convcolonly'
        if obj.name.startswith(('Wheel_', 'Microfiber_', 'Pogo_', 'Vacuum_Motor')):
            axis = 'X' if obj.name.startswith(('Wheel_', 'Microfiber_')) else ('Y' if obj.name.startswith('Pogo_') else 'Z')
            index = {'X':0,'Y':1,'Z':2}[axis]
            diameter = size[(index+1)%3]
            cylinder(name,diameter,size[index],center,axis,0,-1,'Collision',proxy,True)
        else:
            box(name,size,center,0,-1,'Collision',proxy,True)


def validate():
    assert CHASSIS.location.length < 1e-9
    lo,hi = bounds(CHASSIS)
    assert (lo-Vector((-0.06,-0.07,0.002))).length < 1e-7
    assert (hi-Vector((0.06,0.07,0.006))).length < 1e-7
    bm = bmesh.new()
    bm.from_mesh(CHASSIS.data)
    assert all(e.is_manifold for e in bm.edges), 'Chassis is not manifold'
    bm.verts.ensure_lookup_table()
    seen, pending = set(), [bm.verts[0]]
    while pending:
        v = pending.pop()
        if v in seen:
            continue
        seen.add(v)
        pending.extend(e.other_vert(v) for e in v.link_edges)
    assert len(seen) == len(bm.verts), 'Disconnected chassis mesh'
    bm.free()
    assert all(o.parent == CHASSIS for o in VISUALS+COLLIDERS if o != CHASSIS)
    assert all((o.scale-Vector((1,1,1))).length < 1e-6 for o in VISUALS+COLLIDERS)
    known_mass = sum(o['Weight'] for o in VISUALS if o['Mass Known'])
    assert abs(known_mass-335) < 1e-5, known_mass
    CHASSIS['Assembly_Known_Mass_g'] = known_mass
    CHASSIS['Assembly_Mass_Excludes'] = 'Unspecified skirt mass; omitted hardware and wiring'
    centroid = sum(((o.matrix_world @ (sum((Vector(v) for v in o.bound_box), Vector())/8))*o['Weight']
                    for o in VISUALS if o['Mass Known']), Vector()) / known_mass
    CHASSIS['Estimated_COM_mm'] = list(centroid/MM)
    log(f'\nValidation passed: connected manifold chassis; {len(VISUALS)} visuals; '
        f'{len(COLLIDERS)} collision proxies; known mass {known_mass:.2f} g plus skirt. '
        f'Uniform-density blockout COM mm {triple(centroid/MM)}.')


PLAYER_SCRIPT = '''extends CharacterBody3D
const SPEED = 1.5
const SENSITIVITY = 0.002
@onready var camera: Camera3D = $Camera3D
func _ready() -> void:
    Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
func _unhandled_input(event: InputEvent) -> void:
    if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
        rotate_y(-event.relative.x * SENSITIVITY)
        camera.rotation.x = clampf(camera.rotation.x - event.relative.y * SENSITIVITY, -1.5, 1.5)
    if event is InputEventKey and event.pressed and event.keycode == KEY_ESCAPE:
        Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
    if event is InputEventMouseButton and event.pressed:
        Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
func _physics_process(delta: float) -> void:
    var direction := Vector3.ZERO
    if Input.is_physical_key_pressed(KEY_W): direction.z -= 1
    if Input.is_physical_key_pressed(KEY_S): direction.z += 1
    if Input.is_physical_key_pressed(KEY_A): direction.x -= 1
    if Input.is_physical_key_pressed(KEY_D): direction.x += 1
    direction = (transform.basis * direction).normalized()
    velocity.x = direction.x * SPEED
    velocity.z = direction.z * SPEED
    if not is_on_floor(): velocity.y -= 9.8 * delta
    elif Input.is_physical_key_pressed(KEY_SPACE): velocity.y = 3.5
    move_and_slide()
'''

MAIN_SCRIPT = '''extends Node3D
func _ready() -> void:
    var robot := preload("res://Vacuum_Robot_Blockout.glb").instantiate()
    robot.position = Vector3(0, 0.85, 0)
    add_child(robot)
    var table := StaticBody3D.new()
    table.position = Vector3(0, 0.825, 0)
    add_child(table)
    var mesh := MeshInstance3D.new()
    var box := BoxMesh.new()
    box.size = Vector3(0.6, 0.05, 0.6)
    mesh.mesh = box
    table.add_child(mesh)
    var collision := CollisionShape3D.new()
    var shape := BoxShape3D.new()
    shape.size = box.size
    collision.shape = shape
    table.add_child(collision)
    var label := Label.new()
    label.text = "WASD: move | Mouse: look | Space: jump | Esc: release mouse\\nRobot shown at true scale on an inspection table."
    label.position = Vector2(16, 16)
    var ui := CanvasLayer.new()
    add_child(ui)
    ui.add_child(label)
'''

MAIN_SCENE = '''[gd_scene load_steps=8 format=3]
[ext_resource type="Script" path="res://main.gd" id="1"]
[ext_resource type="Script" path="res://player.gd" id="2"]
[sub_resource type="BoxShape3D" id="FloorShape"]
size = Vector3(10, 0.1, 10)
[sub_resource type="BoxMesh" id="FloorMesh"]
size = Vector3(10, 0.1, 10)
[sub_resource type="CapsuleShape3D" id="PlayerShape"]
radius = 0.15
height = 1.6
[sub_resource type="Environment" id="Environment"]
background_mode = 1
background_color = Color(0.12, 0.16, 0.22, 1)
ambient_light_source = 3
ambient_light_color = Color(0.8, 0.85, 1, 1)
ambient_light_energy = 0.7
[sub_resource type="StandardMaterial3D" id="FloorMat"]
albedo_color = Color(0.25, 0.28, 0.33, 1)
[node name="Inspection" type="Node3D"]
script = ExtResource("1")
[node name="WorldEnvironment" type="WorldEnvironment" parent="."]
environment = SubResource("Environment")
[node name="Sun" type="DirectionalLight3D" parent="."]
rotation_degrees = Vector3(-55, -30, 0)
shadow_enabled = true
[node name="Floor" type="StaticBody3D" parent="."]
position = Vector3(0, -0.05, 0)
[node name="CollisionShape3D" type="CollisionShape3D" parent="Floor"]
shape = SubResource("FloorShape")
[node name="MeshInstance3D" type="MeshInstance3D" parent="Floor"]
mesh = SubResource("FloorMesh")
material_override = SubResource("FloorMat")
[node name="Player" type="CharacterBody3D" parent="."]
position = Vector3(0, 0.81, 0.85)
script = ExtResource("2")
[node name="CollisionShape3D" type="CollisionShape3D" parent="Player"]
shape = SubResource("PlayerShape")
[node name="Camera3D" type="Camera3D" parent="Player"]
position = Vector3(0, 0.65, 0)
rotation_degrees = Vector3(-35, 0, 0)
near = 0.005
current = true
'''


def create_godot_project(directory, executable=None, skip=False):
    """Write a Godot 4 project, then import and smoke-run it with OS subprocesses."""
    directory.mkdir(parents=True, exist_ok=True)
    files = {'project.godot': '''config_version=5
[application]
config/name="Vacuum Robot Inspection"
run/main_scene="res://main.tscn"
[rendering]
renderer/rendering_method="gl_compatibility"
renderer/rendering_method.mobile="gl_compatibility"
''', 'player.gd': PLAYER_SCRIPT, 'main.gd': MAIN_SCRIPT, 'main.tscn': MAIN_SCENE}
    for name, contents in files.items():
        (directory/name).write_text(contents, encoding='utf-8')
    binary = executable or os.environ.get('GODOT_BIN') or shutil.which('godot4') or shutil.which('godot')
    if skip or not binary:
        status = 'SKIPPED explicitly' if skip else 'UNAVAILABLE: install Godot 4 or set GODOT_BIN'
        log(f'Godot headless execution {status}. Project files generated at {directory}.')
        return
    version = subprocess.run([binary, '--version'], capture_output=True, text=True, timeout=30, check=True)
    if not version.stdout.strip().startswith('4.'):
        raise RuntimeError('Godot 4.x required: ' + version.stdout)
    for tag, args in [('import', ['--editor','--import']), ('smoke', ['--quit-after','120'])]:
        result = subprocess.run([binary,'--headless','--path',str(directory),*args],
                                capture_output=True, text=True, timeout=180)
        output = result.stdout + result.stderr
        (directory/f'headless_{tag}.log').write_text(output,encoding='utf-8')
        if result.returncode or 'SCRIPT ERROR:' in output or 'ERROR:' in output:
            raise RuntimeError(f'Godot {tag} failed; see {directory}/headless_{tag}.log')
        log(f'Godot headless {tag} passed ({version.stdout.strip()}).')


def main():
    global LOG, STEP, CHASSIS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--godot-bin')
    parser.add_argument('--skip-godot', action='store_true')
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    default_dir = Path(bpy.data.filepath).parent if bpy.data.filepath else Path(__file__).resolve().parent
    output = (args.output_dir or default_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    blend = output/'Vacuum_Robot_Blockout.blend'
    VISUALS.clear()
    COLLIDERS.clear()
    CHASSIS, STEP = None, 0
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1.0
    scene.unit_settings.length_unit = 'MILLIMETERS'
    with (output/'robot_build_state.md').open('w',encoding='utf-8') as handle:
        LOG = handle
        try:
            log('# Vacuum Robot Build State\n\n' + ASSUMPTIONS + '\n## Components\n')
            construct()
            validate()
            notes = bpy.data.texts.get('Robot_Design_Notes.md') or bpy.data.texts.new('Robot_Design_Notes.md')
            notes.clear()
            notes.write(ASSUMPTIONS)
            bpy.ops.object.select_all(action='DESELECT')
            CHASSIS.select_set(True)
            bpy.context.view_layer.objects.active = CHASSIS
            for screen in bpy.data.screens:
                for area in screen.areas:
                    if area.type == 'VIEW_3D':
                        area.spaces.active.clip_start = 0.0001
                        area.spaces.active.region_3d.view_distance = 0.4
                        area.spaces.active.shading.color_type = 'MATERIAL'
            bpy.ops.wm.save_as_mainfile(filepath=str(blend))
            log(f'Saved Blender file: {blend}')
            project = output/'godot_vacuum_robot'
            project.mkdir(exist_ok=True)
            bpy.ops.object.select_all(action='DESELECT')
            for obj in VISUALS+COLLIDERS:
                obj.select_set(True)
            # Explicit selection includes hidden-render helpers; importer removes their meshes.
            bpy.ops.export_scene.gltf(filepath=str(project/'Vacuum_Robot_Blockout.glb'),
                export_format='GLB',use_selection=True,export_extras=True,
                export_yup=True,export_animations=False)
            log('Exported glTF with custom-property extras and collision helper names.')
            create_godot_project(project,args.godot_bin,args.skip_godot)
            log('\nBUILD COMPLETE')
        except Exception:
            log('\nBUILD FAILED\n```\n' + traceback.format_exc() + '```')
            raise
        finally:
            LOG = None


if __name__ == '__main__':
    main()
