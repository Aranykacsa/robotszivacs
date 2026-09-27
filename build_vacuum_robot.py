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

ASSUMPTIONS = """- Revision 2: assembly-oriented, sports-car-style prototype; not production qualified.
- Four 6 V N20 drive motors per user decision; PDF's two-motor configuration is superseded.
- Full-footprint 2 mm sponge follows the chassis and its rear extensions, with a 56 mm
  vacuum opening, wheel reliefs and four sensor windows.
- The chassis has a 56 mm port feeding a gasketed adapter and QX-Motor 30 mm axial EDF.
  QF1611 14000 KV is modeled to match the 2S battery; confirm the motor's printed KV.
  Seller dimensions do not define duct ID/length; modeled fit envelope remains provisional.
  The vendor's 19.3 A 2S test point exceeds the modeled 500 mAh 30C pack's 15 A rating.
- Wheel envelope remains 22 x 21 mm from original request; PDF provides no exact wheel SKU.
- All nominal shaft/hub axes align. Motor envelope is interpreted as 26 mm body + 10 mm shaft.
- One unified chassis includes insert towers, rear forks and sensor support bosses.
- New cover, clamps, trays and coupling are separate printable parts, parented to Chassis.
- Use real screws, inserts, a 3 mm roller axle and 623 bearings; electronics and elastomers
  are purchased. Shaft profiles, fits and purchased hardware must be checked on a prototype.
- The original 100 g chassis allowance is retained as an estimate, not a calculated weight.
  Added hardware/printed parts and the enlarged full pad have unknown masses (-1).
- Godot collision helpers are static inspection geometry (-colonly for apertured structures).
  They are not dynamic rigid-body-ready; use convex decomposition before rigid-body use.
- Manufacturing exports are mm STL fit prototypes. Validate selected parts, pad drag,
  sealing, suction pressure/flow and wheel traction before operating on a vertical board.
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
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    for polygon in obj.data.polygons:
        polygon.material_index = 0
    obj['Material_Name'] = mat.name
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


# Revision 2: assembly-oriented prototype. All design arguments are millimeters.
PRINTED = []
FASTENERS = []
MATERIALS = {}
PAD_OUTLINE = [(-52,-100),(52,-100),(68,-86),(76,-45),(76,40),(70,86),(48,100),(-48,100),(-70,86),(-76,40),(-76,-45),(-68,-86)]
WHEEL_X, WHEEL_Y, AXLE_Z = 75.0, 62.0, 11.0
PORT_D = 56.0
FIT = 0.30


def active(obj):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def organize_collections(scene):
    """Put the chassis assembly into visibility-toggle groups without changing parenting."""
    root = bpy.data.collections.get('Robot Components')
    if root is None:
        root = bpy.data.collections.new('Robot Components')
    if root.name not in scene.collection.children:
        scene.collection.children.link(root)
    names = (
        'Chassis', 'Vacuum System', 'Drivetrain', 'Rear Wiper',
        'Top Electronics', 'Board Sensors', 'Charging Contacts',
        'Sports Car Body', 'Other Components', 'Collision Helpers',
    )
    groups = {}
    for name in names:
        group = bpy.data.collections.get(name)
        if group is None:
            group = bpy.data.collections.new(name)
        if group.name not in root.children:
            root.children.link(group)
        groups[name] = group

    def group_for(obj):
        name = obj.name
        if obj in COLLIDERS or name.endswith(('-colonly', '-convcolonly')):
            return 'Collision Helpers'
        if name == 'Chassis': return 'Chassis'
        if name == 'Full_Bottom_Sponge' or name.startswith((
            'Vacuum_', 'EDF_', 'QF1611_')):
            return 'Vacuum System'
        if name.startswith(('Drive_', 'Wheel_', 'Motor_')):
            return 'Drivetrain'
        if name.startswith(('Wiper_', 'Roller_', 'Microfiber_', 'Bearing_')):
            return 'Rear Wiper'
        if name.startswith((
            'Battery_', 'ESP32_', 'BLHeli_', 'TB6612', 'D4184_',
            'Electronics_', 'Power_')):
            return 'Top Electronics'
        if name.startswith(('TCRT5000_', 'IR_', 'Sensor_')):
            return 'Board Sensors'
        if name.startswith(('Charging_', 'Contact_', 'Pogo_')):
            return 'Charging Contacts'
        if name.startswith((
            'Sports_Car_', 'Exhaust_', 'Racing_Stripe_', 'Headlight_')):
            return 'Sports Car Body'
        return 'Other Components'

    for obj in list(scene.objects):
        destination = groups[group_for(obj)]
        for collection in list(obj.users_collection):
            collection.objects.unlink(obj)
        destination.objects.link(obj)
        obj['Component Group'] = destination.name
    return groups


def raw_box(size, center):
    bpy.ops.mesh.primitive_cube_add(size=1, location=tuple(v*MM for v in center))
    obj = bpy.context.object
    obj.dimensions = tuple(v*MM for v in size)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return obj


def raw_cylinder(d, length, center, axis='Z', sides=48):
    rotation = {'X':(0,math.pi/2,0),'Y':(math.pi/2,0,0),'Z':(0,0,0)}[axis]
    bpy.ops.mesh.primitive_cylinder_add(vertices=sides, radius=d*MM/2, depth=length*MM,
        location=tuple(v*MM for v in center), rotation=rotation)
    obj = bpy.context.object
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    return obj


def boolean(obj, tool, operation='DIFFERENCE'):
    active(obj)
    mod = obj.modifiers.new('Mechanical interface', 'BOOLEAN')
    mod.operation = operation
    mod.solver = 'EXACT'
    mod.object = tool
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(tool,do_unlink=True)
    return obj


def join_solid(obj, other):
    return boolean(obj,other,'UNION')


def hole(obj, diameter, length, center, axis='Z'):
    return boolean(obj,raw_cylinder(diameter,length,center,axis))


def prism(outline, z0, z1):
    n = len(outline)
    verts = [(x*MM,y*MM,z*MM) for z in (z0,z1) for x,y in outline]
    faces = [tuple(reversed(range(n))),tuple(range(n,2*n))]
    faces += [(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
    mesh=bpy.data.meshes.new('Machined profile')
    mesh.from_pydata(verts,[],faces); mesh.update()
    obj=bpy.data.objects.new('Workpiece',mesh); bpy.context.collection.objects.link(obj)
    return obj


def tube(outer, inner, length, center, axis='Z'):
    return hole(raw_cylinder(outer,length,center,axis),inner,length+2,center,axis)


def bevel(obj, width=0.5, segments=2):
    active(obj)
    mod=obj.modifiers.new('Edge relief','BEVEL'); mod.width=width*MM; mod.segments=segments
    bpy.ops.object.modifier_apply(modifier=mod.name)
    return obj


def part(obj, name, mat, kind='Printed PETG part', mass=-1, voltage=-1, printable=True, **props):
    if printable:
        props.update({'Manufacturing':'FDM prototype; fit coupon required','Fit_Clearance_mm':FIT,
                      'Print_Orientation':'See ASSEMBLY.md','Production_Validated':False})
    obj=finish(obj,name,mass,voltage,kind,mat,**props)
    if printable: PRINTED.append(obj)
    return obj


def screw(name,x,y,z,diam=2.5,length=8,axis='Z'):
    # z is the head underside for Z screws. For X, x is the head underside.
    v=Vector((x,y,z)); direction=Vector({'X':(1,0,0),'Y':(0,1,0),'Z':(0,0,1)}[axis])
    obj=raw_cylinder(diam,length,v-direction*length/2,axis,24)
    if 'SetScrew' not in name:
        join_solid(obj,raw_cylinder(diam*1.8,diam*.65,v+direction*(diam*.325-.02),axis,24))
    hole(obj,diam*.75,diam*.5,v+direction*diam*.6,axis)
    out=part(obj,name,MATERIALS['metal'],'Purchased socket screw',-1,printable=False,
             Thread=f'M{diam}',Length_mm=length,Thread_Geometry='Simplified smooth shank')
    FASTENERS.append(out)
    return out


def insert(name,x,y,z,diam=3.6,length=4):
    obj=tube(diam,2.1,length,(x,y,z))
    return part(obj,name,MATERIALS['brass'],'Purchased M2.5 heat-set insert',-1,
                printable=False,Nominal_OD_mm=diam,Fit_Status='Match purchased insert and coupon')


def recesses(obj, pad=False):
    for x in (-WHEEL_X,WHEEL_X):
        for y in (-WHEEL_Y,WHEEL_Y):
            boolean(obj,raw_box((28,29,12),(x,y,3)))
    hole(obj,PORT_D,20,(0,0,3))
    for x in (-43,43):
        for y in (-87,87):
            boolean(obj,raw_box((33,15,14),(x,y,3)))
    return obj


def loft(stations, bottom=8, inset=0):
    vertices=[]
    for y,w,h in stations:
        w-=inset; h-=inset
        profile=[(-w,bottom),(-w,h*.50),(-w*.78,h-4),(-w*.58,h),
                 (w*.58,h),(w*.78,h-4),(w,h*.50),(w,bottom)]
        vertices.extend((x*MM,y*MM,z*MM) for x,z in profile)
    faces=[tuple(reversed(range(8))),tuple(range((len(stations)-1)*8,len(stations)*8))]
    for j in range(len(stations)-1):
        for i in range(8): faces.append((j*8+i,j*8+(i+1)%8,(j+1)*8+(i+1)%8,(j+1)*8+i))
    mesh=bpy.data.meshes.new('Coachwork loft'); mesh.from_pydata(vertices,[],faces); mesh.update()
    obj=bpy.data.objects.new('Coachwork',mesh); bpy.context.collection.objects.link(obj)
    # Recalculate to ensure boolean operands have consistently outward normals.
    bm=bmesh.new(); bm.from_mesh(mesh); bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces)); bmesh.ops.triangulate(bm,faces=list(bm.faces)); bm.to_mesh(mesh); bm.free()
    return obj


def construct():
    global CHASSIS
    PRINTED.clear(); FASTENERS.clear()
    colors={'body':((0.88,.075,.018),.28,.3),'base':((.055,.07,.09),.15,.5),
      'rubber':((.018,.024,.028),0,.9),'sponge':((.10,.20,.21),0,1),
      'metal':((.52,.61,.69),.8,.28),'brass':((.62,.38,.10),.65,.35),
      'teal':((.02,.62,.53),.1,.55),'battery':((.12,.17,.23),.1,.5),
      'pcb':((.025,.33,.16),0,.5),'blue':((.035,.22,.55),.1,.4),
      'white':((.88,.94,.98),.15,.3),'red':((.58,.006,.01),.2,.3),
      'proxy':((1,.05,.6),0,.8)}
    MATERIALS.clear()
    for name,(color,metal,rough) in colors.items(): MATERIALS[name]=material(name,color,metal,rough)
    M=MATERIALS
    # One continuous chassis with all permanent bosses, roller arms and motor support.
    chassis=recesses(prism(PAD_OUTLINE,2,6))
    # Wheel motor clamps attach to blind insert towers, keeping the board face sealed.
    for s in (-1,1):
        for y in (-62,62):
            for dy in (-10,10):
                join_solid(chassis,raw_cylinder(8,10.5,(s*49,y+dy,11.15),sides=24))
                hole(chassis,3.7,4.3,(s*49,y+dy,14.35))
    # Electronics trays use captive chassis insert seats.
    for x,y in [(-31,-57),(31,-57),(-30,58),(30,58),(-60,-12),(58,-18),(58,21)]:
        join_solid(chassis,raw_cylinder(8,3.2,(x,y,7.4),sides=24))
        hole(chassis,3.7,4.2,(x,y,6.9))
    # Blower adapter M2.5 blind insert seats, around a real 56 mm through-port.
    for x in (-25,25):
        for y in (-25,25): hole(chassis,3.7,3.2,(x,y,4.5))
    # Removable cover: four low flanges, outside electronic and fan clearance.
    for x in (-66,66):
        for y in (-29,29):
            join_solid(chassis,raw_cylinder(9,2.4,(x,y,7),sides=24))
            hole(chassis,3.7,4.2,(x,y,6.1))
    # Integral rear fork; right extension carries the fifth motor.
    for x in (-65,65):
        join_solid(chassis,raw_box((12,34,3),(x,-103,3.5)))
        block=raw_box((6,22,16),(x,-111,10))
        hole(block,3.4,10,(x,-111,10),'X')
        # Outward-facing bearing pocket and an inner retention shoulder.
        hole(block,10.2,4.4,(x+math.copysign(1,x),-111,10),'X')
        for yy in (-119,-103): hole(block,1.7,9,(x,yy,10),'X')
        join_solid(chassis,block)
    join_solid(chassis,raw_box((56,26,3),(87,-109,3.5)))
    for y in (-121,-101):
        join_solid(chassis,raw_cylinder(8,10.5,(99,y,10.15),sides=24))
        hole(chassis,3.7,4.3,(99,y,13.35))
    # Sensor retainers are supported by integral ledges and blind screw bosses.
    for x in (-43,43):
        for y in (-87,87):
            for dx in (-19,19):
                join_solid(chassis,raw_cylinder(7,4,(x+dx,y,4),sides=24))
                hole(chassis,3.7,3.2,(x+dx,y,4.5))
    CHASSIS=part(chassis,'Chassis',M['base'],mass=100,
       Weight_Basis='Original 100 g chassis allowance; enlarged prototype must be weighed',
       Ground_Clearance_mm=2,Vacuum_Port_Diameter_mm=56)
    # Derive the pad directly from the complete chassis contact footprint, including forks.
    pad=bpy.data.objects.new('Pad footprint workpiece',CHASSIS.data.copy())
    bpy.context.collection.objects.link(pad)
    boolean(pad,raw_box((400,400,.7),(0,0,2.15)),'INTERSECT')
    for vertex in pad.data.vertices:
        vertex.co.z=(vertex.co.z-2*MM)*4
    pad.data.update()
    part(pad,'Full_Bottom_Sponge',M['sponge'],'Die-cut closed-cell sponge pad',-1,
         printable=False,Compressed_Thickness_mm=2,Attachment='Thin removable adhesive; include in 2 mm stack',
         Coverage='Entire chassis contact footprint including rear extensions, with functional openings')
    gasket=tube(80,56,.5,(0,0,6.25))
    for x in (-25,25):
        for y in (-25,25): hole(gasket,2.8,3,(x,y,6.25))
    part(gasket,'Vacuum_Flange_Gasket',M['rubber'],'Cut silicone gasket',-1,printable=False)
    # Hollow tapered adapter: 56 mm mouth to a provisional 26.5 mm EDF bore.
    bpy.ops.mesh.primitive_cone_add(vertices=64,radius1=30*MM,radius2=15.8*MM,
                                    depth=10*MM,location=(0,0,11.5*MM))
    adapter=bpy.context.object
    join_solid(adapter,raw_cylinder(80,3,(0,0,8)))
    bpy.ops.mesh.primitive_cone_add(vertices=64,radius1=29.3*MM,radius2=13.25*MM,
                                    depth=12*MM,location=(0,0,11.5*MM))
    boolean(adapter,bpy.context.object)
    for x in (-25,25):
        for y in (-25,25): hole(adapter,2.8,8,(x,y,8))
    # Three screws hold the EDF casing clamp; towers overlap the taper's outer wall.
    for a in (30,150,270):
        x,y=24*math.cos(math.radians(a)),24*math.sin(math.radians(a))
        join_solid(adapter,raw_cylinder(8,9,(x,y,12),sides=24))
        hole(adapter,2.1,7,(x,y,14))
    part(adapter,'Vacuum_Adapter',M['teal'],Inlet_mm=56,Outlet_mm=26.5,
         Fit_Status='Provisional throat matches estimated EDF clear bore; confirm purchased duct ID')
    for x in (-25,25):
        for y in (-25,25):
            insert(f'Vacuum_Insert_{x}_{y}',x,y,4.5,length=3)
            screw(f'Vacuum_Flange_Screw_{x}_{y}',x,y,9.5,length=6)
    part(tube(32,26.5,.5,(0,0,16.25)),'EDF_Inlet_Gasket',M['rubber'],
         'Cut silicone EDF inlet gasket',-1,printable=False,
         Fit_Status='26.5 mm opening is provisional; measure EDF bore and inlet lip')

    # QX-Motor 30 mm six-blade EDF; nominal duct OD 30, motor Ø16.3 x 25.
    # Vendor does not publish duct ID/length drawing: 25.5 mm ID x 16 mm is a fit envelope.
    edf=raw_cylinder(30,16,(0,0,24.5),'Z',72)
    boolean(edf,raw_cylinder(25.5,18,(0,0,24.5),'Z',72))
    # Three short stator spokes support the motor inside the annular airflow path.
    for angle in (90,210,330):
        phi=math.radians(angle)
        r=(7.4+13.0)/2
        outline=[]
        for rr,side in [(7.4,-.65),(13.0,-.65),(13.0,.65),(7.4,.65)]:
            outline.append((rr*math.cos(phi)-side*math.sin(phi),
                            rr*math.sin(phi)+side*math.cos(phi)))
        join_solid(edf,prism(outline,25.6,27.2))
    part(edf,'EDF_30mm_Duct_Stators',M['base'],'Purchased polycarbonate EDF casing',2.3,7.4,False,
         Manufacturer='QX-Motor 30 mm 6-blade EDF with QF1611',
         Nominal_Outer_Diameter_mm=30,Manufacturer_Duct_ID_mm=-1,
         Modeled_Bore_mm=25.5,Manufacturer_Duct_Length_mm=-1,Modeled_Length_mm=16,
         Fit_Status='OD follows 30 mm product name; ID/length measured from image only, verify part')

    # Six slim, separate vane profiles join a central hub; this is an envelope, not rotor CAD.
    impeller=raw_cylinder(11,.8,(0,0,18.15),'Z',48)
    for index in range(6):
        base_angle=math.radians(index*60)
        stations=[(5.3,-10),(8.0,-14),(11.8,-9),(12.25,-3),
                  (12.25,4),(8.0,0),(5.3,7)]
        polygon=[(r*math.cos(base_angle+math.radians(a)),
                  r*math.sin(base_angle+math.radians(a))) for r,a in stations]
        join_solid(impeller,prism(polygon,17.8,18.5))
    part(impeller,'EDF_Six_Blade_Impeller',M['metal'],'Six-blade EDF rotor envelope',-1,7.4,False,
         Blade_Count=6,Rotation_Axis='Z',Rotation_Speed_RPM=-1,
         Fit_Status='Visual vane blockout; not an aerodynamic or balanced rotor model')

    motor=raw_cylinder(16.3,25,(0,0,30.5),'Z',48)
    part(motor,'QF1611_EDF_Motor',M['metal'],'QF1611 brushless motor',19.5,7.4,False,
         Manufacturer='QX-Motor QF1611',KV=14000,KV_Selection_Basis='Vendor lists 14000 KV for 2S; assembly battery is 2S',
         Motor_Diameter_mm=16.3,Motor_Length_mm=25,Motor_Shaft_Diameter_mm=1.5,
         Vendor_Reported_Max_Current_A=20,Vendor_Reported_Max_Current_Duration_s=60,
         Vendor_Reported_2S_Test_Current_A=19.3,Vendor_Reported_2S_Test_Power_W=142.82,
         Vendor_Reported_2S_Test_Thrust_g=215,Vendor_Reported_2S_Test_Throttle_Percent=100,
         Airflow='Inlet from board chamber along +Z; exhaust upward',
         Thrust_Is_Not='Static pressure capability; no suction-pressure curve supplied')
    # Motor shaft and six-blade hub meet coaxially; shaft is a simplified 1.5 mm pin.
    part(raw_cylinder(1.5,3,(0,0,17),'Z',24),'QF1611_Output_Shaft',M['metal'],
         'QF1611 1.5 mm shaft envelope',0,7.4,False,Mass_Included_In='QF1611_EDF_Motor')

    # Split clamp grips the nominal 30 mm casing OD, and bolts to existing adapter bosses.
    clamp=tube(36,30.6,4,(0,0,19))
    join_solid(clamp,tube(64,30.6,2,(0,0,17.5)))
    boolean(clamp,raw_box((15,2,8),(18,0,19)))
    for a in (30,150,270):
        x,y=24*math.cos(math.radians(a)),24*math.sin(math.radians(a))
        join_solid(clamp,raw_cylinder(8,2,(x,y,17.5),sides=24))
        hole(clamp,2.8,8,(x,y,17.5))
    for yy in (-4,4): join_solid(clamp,raw_box((12,8,8),(22,yy,19)))
    hole(clamp,2.8,18,(22,0,19),'Y')
    boolean(clamp,raw_cylinder(6.1,3,(22,-5.3,19),'Y',6))
    part(clamp,'EDF_Duct_Clamp',M['base'],Fit_Status='Split clamp around nominal 30 mm duct OD; measure fit')
    screw('EDF_Duct_Pinch_Screw',22,7,19,length=14,axis='Y')
    nut=hole(raw_cylinder(5.8,2,(22,-5.3,19),'Y',6),2.1,4,(22,-5.3,19),'Y')
    part(nut,'EDF_Duct_Pinch_Nut',M['metal'],'Purchased M2.5 hex nut',-1,-1,False)
    for a in (30,150,270):
        x,y=24*math.cos(math.radians(a)),24*math.sin(math.radians(a))
        screw(f'EDF_Clamp_Screw_{a}',x,y,18.5,length=6)

    # Four coaxial motor/hub/shaft assemblies. 36 mm is interpreted as body + shaft.
    for side,s in [('Left',-1),('Right',1)]:
        for end,y in [('Front',62),('Rear',-62)]:
            tag=side+'_'+end
            motor=raw_box((26,12,10),(s*50.5,y,11))
            part(motor,'Drive_Motor_'+tag,M['brass'],'N20 geared motor envelope',10,6,False,
                 Envelope_Interpretation='26 mm body + 10 mm output shaft; verify selected N20',
                 Battery_Rail_V=7.4,Rated_Voltage_V=6,Axle='X')
            part(raw_cylinder(3,10,(s*68.5,y,11),'X',24),'Drive_Shaft_'+tag,M['metal'],
                 'N20 output shaft',0,6,False,Mass_Included_In='Drive_Motor_'+tag)
            wheel=tube(22,12,21,(s*75,y,11),'X')
            part(wheel,'Wheel_Tire_'+tag,M['rubber'],'Shore 20A silicone tire',5,-1,False)
            hub=tube(12,3.1,21,(s*75,y,11),'X')
            hole(hub,2.5,8,(s*70,y,16),'Z')
            part(hub,'Wheel_Hub_'+tag,M['metal'],'Aluminum wheel hub envelope',2.5,-1,False,
                 Fit_Status='Nominal 3 mm shaft; exact JSumo wheel SKU unresolved')
            screw('Hub_SetScrew_'+tag,s*70,y,17,diam=2.5,length=5)
            cap=raw_box((22,28,3),(s*49,y,17.9))
            for dy in (-10,10): hole(cap,2.8,6,(s*49,y+dy,18))
            part(cap,'Motor_Clamp_'+tag,M['base'])
            part(raw_box((20,12,.4),(s*49,y,16.2)),'Motor_Clamp_Pad_'+tag,M['rubber'],
                 'Thin compliant clamp pad',-1,printable=False)
            for dy in (-10,10):
                insert('Motor_Insert_'+tag+str(dy),s*49,y+dy,14.35)
                screw('Motor_Screw_'+tag+str(dy),s*49,y+dy,19.4,length=8)
    # Rear roller: common axis, bearing shoulders, bolted covers and a coupling.
    part(tube(15,3.2,120,(0,-111,10),'X'),'Roller_Core',M['teal'],
         Shaft_Fit='3.2 mm bore; lock with end collar set screw')
    part(tube(20,15,116,(0,-111,10),'X'),'Microfiber_Roller',M['white'],
         'Replaceable microfiber sleeve',5,-1,False,Attachment='Thin hook-and-loop sleeve; OD includes fabric')
    part(raw_cylinder(3,146,(0,-111,10),'X',24),'Roller_Steel_Axle',M['metal'],
         'Purchased 3 mm steel axle',-1,-1,False)
    for side,s in [('Left',-1),('Right',1)]:
        part(tube(10,3,4,(s*66,-111,10),'X'),'Roller_Bearing_'+side,M['metal'],
             'Purchased 623 bearing 3 x 10 x 4',-1,-1,False)
        cap=raw_box((1.8,22,16),(s*68.9,-111,10))
        hole(cap,3.5,5,(s*68.9,-111,10),'X')
        for yy in (-119,-103): hole(cap,2.2,5,(s*68.9,yy,10),'X')
        part(cap,'Bearing_Retainer_'+side,M['body'])
        # Left screws are mirrored versions of a +X-oriented fastener.
        for yy in (-119,-103):
            ob=screw('Bearing_Screw_'+side+str(yy),70.8,yy,10,diam=2,length=7,axis='X')
            if s<0:
                for v in ob.data.vertices: v.co.x=-v.co.x
                ob.location.x=-ob.location.x
                # Recalculate normals following mesh reflection.
                bm=bmesh.new(); bm.from_mesh(ob.data); bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces)); bm.to_mesh(ob.data); bm.free()
                record(ob)
    core=bpy.data.objects.get('Roller_Core')
    for x in (-57,57):
        hole(core,2.5,10,(x,-111,14),'Z')
        screw(f'Roller_Core_SetScrew_{x}',x,-111,17.5,diam=2.5,length=7)
    part(raw_box((26,12,10),(100,-111,10)),'Wiper_Motor_N20',M['brass'],
         'N20 geared wiper motor',10,6,False)
    part(raw_cylinder(3,10,(82,-111,10),'X',24),'Wiper_Output_Shaft',M['metal'],
         'N20 output shaft',0,6,False,Mass_Included_In='Wiper_Motor_N20')
    coupling=tube(11,3.2,14,(77,-111,10),'X')
    for x in (72,82): hole(coupling,2.5,8,(x,-111,14),'Z')
    part(coupling,'Roller_Shaft_Coupling',M['teal'])
    for x in (72,82): screw(f'Coupling_SetScrew_{x}',x,-111,15.5,diam=2.5,length=5)
    cap=raw_box((22,28,3),(99,-111,16.9))
    for yy in (-121,-101): hole(cap,2.8,7,(99,yy,17))
    part(cap,'Wiper_Motor_Clamp',M['base'])
    part(raw_box((20,12,.4),(99,-111,15.2)),'Wiper_Clamp_Pad',M['rubber'],
         'Thin compliant clamp pad',-1,-1,False)
    for yy in (-121,-101):
        insert(f'Wiper_Insert_{yy}',99,yy,13.35)
        screw(f'Wiper_Clamp_Screw_{yy}',99,yy,18.4,length=8)
    # Replaceable screw-down trays retain generic electronics without invented PCB hole patterns.
    electronics=[('Battery_2S_LiPo',(55,30,15),(0,-57,17.5),40,7.4,M['battery'],[(-31,-57),(31,-57)]),
       ('ESP32_S3',(53,28,12),(0,58,16),10,3.3,M['pcb'],[(-30,58),(30,58)]),
       ('BLHeli_ESC',(12,25,5),(55,-18,12.5),10,7.4,M['blue'],[(58,-18)]),
       ('TB6612FNG',(20,20,5),(53,21,12.5),5,7.4,M['pcb'],[(58,21)]),
       ('D4184_MOSFET',(17,34,12),(-52,-12,16),5,7.4,M['pcb'],[(-60,-12)])]
    for name,size,center,mass,voltage,mat,mounts in electronics:
        x,y,z=center; sx,sy,sz=size
        tray=raw_box((sx+5,sy+5,2),(x,y,10))
        # Low retaining walls; top is open, allowing module and connector access.
        for xx in (x-sx/2-1.5,x+sx/2+1.5): join_solid(tray,raw_box((2,sy+5,5),(xx,y,12)))
        for yy in (y-sy/2-1.5,y+sy/2+1.5): join_solid(tray,raw_box((sx+5,2,5),(x,yy,12)))
        # A single strap channel is recessed into the tray floor; modules sit on its flat top.
        boolean(tray,raw_box((sx+8,4,1),(x,y+sy/4,9.5)))
        for mx,my in mounts:
            join_solid(tray,raw_cylinder(8,2,(mx,my,10),sides=24))
            hole(tray,2.8,4,(mx,my,10))
        for yy in (y-sy/3,y+sy/3):
            join_solid(tray,raw_box((sx,2,2.2),(x,yy,11.9)))
        part(tray,name+'_Tray',M['base'],Retention='Thin hook-and-loop strap through tray channel')
        part(raw_box(size,(x,y,13+sz/2)),name,mat,'Electronics module envelope',mass,voltage,False,
             Mounting='Retained tray; no assumed PCB mounting holes',
             **({'Capacity_mAh':500,'Discharge_C_Min':30,
                 'Continuous_Current_at_Minimum_C_A':15.0,
                 'EDF_Full_Throttle_Current_A':19.3,
                 'Full_Throttle_Current_Margin_A':-4.3,
                 'Supply_Status':'At minimum 30C, limit EDF throttle or use a higher-current 2S pack'} if name=='Battery_2S_LiPo' else
                {'Recommended_Continuous_Rating_A':30,
                 'Vendor_EDF_Test_Current_A':19.3,
                 'Current_Margin_A':10.7} if name=='BLHeli_ESC' else {}))
        strap=raw_box((sx+7.2,3.8,sz+4.4),(x,y+sy/4,11.4+sz/2))
        boolean(strap,raw_box((sx+6,6,sz+3.2),(x,y+sy/4,11.4+sz/2)))
        part(strap,name+'_Retaining_Strap',M['rubber'],'Thin hook-and-loop retaining strap',-1,-1,False,
             Routing='Under tray in recessed channel, around sides and over component')
        for mx,my in mounts:
            insert(name+f'_Insert_{mx}',mx,my,6.9)
            # Screws underneath module footprint must be installed before the module.
            screw(name+f'_Tray_Screw_{mx}',mx,my,11,length=6)
    # Chassis-mounted sensor cartridges, ahead/behind the wheel axles, never on wheels.
    # Package geometry is from Vishay; the generic breakout PCB remains a measured-fit envelope.
    for side,x in [('Left',-43),('Right',43)]:
        for end,y in [('Front',87),('Rear',-87)]:
            tag=side+'_'+end
            optical_x=x+math.copysign(10,x)
            part(raw_box((32,14,1.6),(x,y,10.3)),'TCRT5000_PCB_'+tag,M['pcb'],
                 'TCRT5000 breakout PCB envelope',3.25,3.3,False,
                 Fit_Status='32 x 14 board envelope; confirm exact module connector layout')
            optical_body=raw_box((10.2,5.8,7),(optical_x,y,6))
            for dx in (-2.5,2.5): hole(optical_body,3.6,.7,(optical_x+dx,y,2.6))
            part(optical_body,'TCRT5000_Optical_'+tag,M['base'],
                 'Vishay TCRT5000 optical package',.5,3.3,False,
                 Optical_Axis_World=[0.,0.,-1.],Optical_Face_Gap_mm=2.5,
                 Source='https://www.vishay.com/docs/83760/tcrt5000.pdf')
            for dx in (-2.5,2.5):
                part(raw_cylinder(3.5,.3,(optical_x+dx,y,2.65),'Z',24),
                     'IR_Lens_'+tag+str(dx),M['blue'],'Optical face',0,-1,False)
            part(raw_box((5,5,5),(x-math.copysign(8,x),y-2,13.6)),
                 'IR_Trim_Pot_'+tag,M['blue'],'Module adjustment potentiometer',0,3.3,False,
                 Mass_Included_In='TCRT5000_PCB_'+tag)
            carrier=raw_box((36,18,3),(x,y,8))
            boolean(carrier,raw_box((11,7,7),(optical_x,y,8)))
            for xx in (x-19,x+19):
                join_solid(carrier,raw_cylinder(7,5,(xx,y,9),sides=24))
                hole(carrier,2.8,8,(xx,y,9))
            # Raised side guides locate the PCB; bridge clamp bears only on its edge.
            for yy in (y-8,y+8): join_solid(carrier,raw_box((32,1.6,3),(x,yy,10)))
            part(carrier,'Sensor_Cartridge_'+tag,M['teal'],
                 Adjustment='Replace 0.5 mm under-cartridge shim to set optical face gap',
                 Mounting='Two M2.5 chassis screws, 38 mm centers; no PCB hole assumptions')
            shim=raw_box((36,18,.5),(x,y,6.25))
            boolean(shim,raw_box((11,7,3),(optical_x,y,6.25)))
            for xx in (x-19,x+19):
                join_solid(shim,raw_cylinder(7,.5,(xx,y,6.25),sides=24))
                hole(shim,2.8,3,(xx,y,6.25))
            part(shim,'Sensor_Height_Shim_'+tag,M['body'],Thickness_mm=.5)
            cap=raw_box((46,3,2),(x,y+6,12.5))
            for xx in (x-19,x+19):
                join_solid(cap,raw_box((7,18,2),(xx,y,12.5)))
                hole(cap,2.8,5,(xx,y,12.5))
            part(cap,'Sensor_Edge_Clamp_'+tag,M['base'],
                 Service='Potentiometer and connector remain accessible from above')
            part(raw_box((30,2,.4),(x,y+6,11.3)),'Sensor_Clamp_Pad_'+tag,M['rubber'],
                 'Compliant PCB edge pad',-1,-1,False)
            for xx in (x-19,x+19):
                insert('Sensor_Insert_'+tag+str(xx),xx,y,4.5,length=3)
                screw('Sensor_Screw_'+tag+str(xx),xx,y,13.5,length=10)
    # Pogo pins supported by an integral-style, removable nose block.
    block=raw_box((48,8,7),(0,96,9.5))
    for x in (-16,16): hole(block,2.2,12,(x,96,9.5),'Y')
    for x in (-9,9): hole(block,2.8,12,(x,95,9))
    part(block,'Charging_Contact_Block',M['base'])
    for x in (-9,9):
        hole(CHASSIS,2.1,3,(x,95,4.7))
        screw(f'Contact_Block_Screw_{x}',x,95,13,diam=2.5,length=9)
    for side,x in [('Left',-16),('Right',16)]:
        part(raw_box((5,.6,4),(x,99.8,9.5)),'Charging_Plate_'+side,M['brass'],
             'Copper charging plate',1.25,-1,False)
        part(raw_cylinder(2,5,(x,101.6,9.5),'Y',24),'Pogo_Pin_'+side,M['brass'],
             'Purchased spring contact',1.25,-1,False)
    # Sports-car coachwork: hollow, open-bottom removable shell, not a solid block.
    stations=[(-98,52,24),(-80,66,32),(-44,72,40),(-28,72,64),
              (28,72,64),(45,70,41),(80,65,29),(98,46,22)]
    shell=loft(stations)
    inner=[(y if i not in (0,len(stations)-1) else y+math.copysign(2,-y),w,h)
           for i,(y,w,h) in enumerate(stations)]
    boolean(shell,loft(inner,bottom=0,inset=2))
    hole(shell,44,100,(0,0,40))
    for x in (-70,70):
        for y in (-62,62): boolean(shell,raw_box((70,35,50),(x,y,0)))
    # Clear the complete sensor clamps, leaving noses and central deck intact.
    for x in (-43,43):
        for y in (-87,87): boolean(shell,raw_box((49,19,46),(x,y,0)))
    boolean(shell,raw_box((50,16,28),(0,99,0)))
    for x in (-66,66):
        for y in (-29,29):
            join_solid(shell,raw_box((25,12,3),(math.copysign(62,x),y,9.7)))
            hole(shell,2.8,8,(x,y,9.7))
    shell=part(shell,'Sports_Car_Service_Cover',M['body'],Shell_Thickness_mm=2,
               Removal='Four flange screws; lift vertically after disconnecting no wires')
    for x in (-66,66):
        for y in (-29,29):
            insert(f'Cover_Insert_{x}_{y}',x,y,6.1)
            screw(f'Cover_Screw_{x}_{y}',x,y,11.2,length=7)
    # Printed exhaust bezel and open grille; no closed decorative cap over the outlet.
    grille=tube(51,44,2,(0,0,65))
    for x in (-15,-5,5,15):
        half=math.sqrt(22**2-x*x)
        join_solid(grille,raw_box((1.5,2*half+2,2),(x,0,65)))
    part(grille,'Exhaust_Grille',M['base'],Retention='Bond bezel to cover after fit test')
    # Surface-following paint strips and headlight graphics are separate thin mesh decals.
    def graphic(name,verts,faces,mat):
        mesh=bpy.data.meshes.new(name); mesh.from_pydata([(x*MM,y*MM,z*MM) for x,y,z in verts],[],faces); mesh.update()
        obj=bpy.data.objects.new(name,mesh); bpy.context.collection.objects.link(obj)
        return part(obj,name,mat,'Paint / vinyl graphic',0,-1,False)
    def roof(y):
        for (ya,wa,ha),(yb,wb,hb) in zip(stations,stations[1:]):
            if ya<=y<=yb: return ha+(hb-ha)*(y-ya)/(yb-ya)
        return 24
    for s in (-1,1):
        for start,end in [(28,95),(-95,-28)]:
            ys=sorted({start,end,*[v[0] for v in stations if start<v[0]<end]})
            verts=[(s*x,y,roof(y)+.16) for y in ys for x in (4,9)]
            graphic(f'Racing_Stripe_{s}_{start}',verts,[(2*i,2*i+1,2*i+3,2*i+2) for i in range(len(ys)-1)],M['white'])
        graphic(f'Headlight_Graphic_{s}',[(s*14,85,roof(85)+.2),(s*29,84,roof(84)+.2),
                (s*30,88,roof(88)+.2),(s*15,89,roof(89)+.2)],[(0,1,2,3)],M['white'])
    for obj in PRINTED:
        bm=bmesh.new(); bm.from_mesh(obj.data)
        bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=1e-7)
        bmesh.ops.dissolve_degenerate(bm,edges=list(bm.edges),dist=1e-8)
        bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
        bm.to_mesh(obj.data); bm.free()
    for obj in VISUALS:
        mat=bpy.data.materials[obj['Material_Name']]
        obj.data.materials.clear(); obj.data.materials.append(mat)
        for polygon in obj.data.polygons: polygon.material_index=0
    # Refresh finalized geometry logs for parts receiving late machining operations.
    log('\nFinal machining updates:')
    record(CHASSIS); record(core)
    # Static concave helpers preserve every port and bolt opening. Godot static inspection only.
    # One helper per principal structure; convex boxes for purchased components.
    for obj in list(VISUALS):
        if obj['Part Type'] in ('Paint / vinyl graphic','Purchased socket screw','Purchased M2.5 heat-set insert'):
            continue
        if obj in PRINTED or obj.name in ('Full_Bottom_Sponge','Vacuum_Flange_Gasket','EDF_30mm_Duct_Stators','EDF_Six_Blade_Impeller','QF1611_EDF_Motor'):
            helper=bpy.data.objects.new(obj.name+'-colonly',obj.data.copy())
            bpy.context.collection.objects.link(helper); helper.matrix_world=obj.matrix_world.copy()
            finish(helper,obj.name+'-colonly',0,-1,'Static collision helper',M['proxy'],True)
        else:
            lo,hi=bounds(obj)
            box(obj.name+'-convcolonly',(hi-lo)/MM,(lo+hi)/(2*MM),0,-1,'Collision',M['proxy'],True)


def validate():
    import json
    from mathutils.bvhtree import BVHTree
    assert CHASSIS.location.length < 1e-8
    report={'printed_parts':[],'cut_parts':[],'checks':[],'status':'PROTOTYPE — purchased-part fit unverified'}
    for obj in PRINTED+[bpy.data.objects['Full_Bottom_Sponge']]:
        bm=bmesh.new(); bm.from_mesh(obj.data)
        bad=sum(not e.is_manifold for e in bm.edges)
        bm.verts.ensure_lookup_table()
        seen=set(); components=0
        for root in bm.verts:
            if root in seen: continue
            components+=1; pending=[root]
            while pending:
                v=pending.pop()
                if v in seen: continue
                seen.add(v); pending.extend(e.other_vert(v) for e in v.link_edges)
        volume=abs(bm.calc_volume())*1e9
        bm.free()
        report['printed_parts' if obj in PRINTED else 'cut_parts'].append({'name':obj.name,'nonmanifold_edges':bad,
            'connected_solids':components,'solid_volume_mm3':round(volume,2)})
        assert bad==0, f'{obj.name}: {bad} non-manifold edges'
        assert components==1, f'{obj.name}: {components} disconnected pieces'
    assert len([o for o in VISUALS if o.name.startswith('Drive_Motor_')])==4
    assert all(o.parent==CHASSIS for o in VISUALS+COLLIDERS if o!=CHASSIS)
    assert all((o.scale-Vector((1,1,1))).length <1e-6 for o in VISUALS+COLLIDERS)
    assert all(len(o.users_collection)==1 and o.get('Component Group')
               for o in VISUALS+COLLIDERS), 'Every assembly object must belong to one visibility group'
    # A real vacuum passage through all stationary layers; inspect off-axis to avoid grille bars.
    for name in ('Full_Bottom_Sponge','Chassis','Vacuum_Adapter','EDF_Inlet_Gasket'):
        ob=bpy.data.objects[name]; inv=ob.matrix_world.inverted()
        sample=Vector((0,0,-.001))
        start=inv @ sample; direction=(inv.to_3x3() @ Vector((0,0,1))).normalized()
        hit=ob.ray_cast(start,direction,distance=.08)[0]
        assert not hit,f'Vacuum path blocked by {name}'
    # Off-axis ray passes through blade gaps, between stators and outside motor casing.
    sample=Vector((.009526,.0055,-.001))
    for name in ('EDF_30mm_Duct_Stators','EDF_Six_Blade_Impeller','QF1611_EDF_Motor'):
        ob=bpy.data.objects[name]; inv=ob.matrix_world.inverted()
        start=inv @ sample; direction=(inv.to_3x3() @ Vector((0,0,1))).normalized()
        hit=ob.ray_cast(start,direction,distance=.08)[0]
        assert not hit,f'Vacuum path blocked by {name}'
    # Tires and cleaning sleeve touch the common board plane.
    for obj in VISUALS:
        if obj.name.startswith('Wheel_Tire_') or obj.name=='Microfiber_Roller':
            assert abs(bounds(obj)[0].z)<1e-7,obj.name
    # Nominal shaft/hub alignment checks use the actual world mesh bounds.
    for side,s in [('Left',-1),('Right',1)]:
        for end,y in [('Front',62),('Rear',-62)]:
            for prefix in ('Drive_Shaft_','Wheel_Hub_','Wheel_Tire_'):
                low,high=bounds(bpy.data.objects[prefix+side+'_'+end]); center=(low+high)/2/MM
                assert abs(center.y-y)<1e-4 and abs(center.z-11)<1e-4
    # Verify the sensor's optical ray reaches the board without a chassis, pad or tire obstruction.
    for obj in VISUALS:
        if obj.name.startswith('TCRT5000_Optical_'):
            lo,hi=bounds(obj); p=(lo+hi)/2; p.z=lo.z-1e-6
            assert abs(lo.z-.0025)<1e-7, obj.name
            for obstacle in VISUALS:
                if obstacle.name.startswith(('IR_Lens_','TCRT5000_Optical_')): continue
                inv=obstacle.matrix_world.inverted()
                hit=obstacle.ray_cast(inv@p,(inv.to_3x3()@Vector((0,0,-1))).normalized(),distance=.003)[0]
                assert not hit,f'{obj.name} sightline blocked by {obstacle.name}'
    # The shell must not cut into purchased modules, wheels or optical packages.
    def tree(obj):
        verts=[obj.matrix_world@v.co for v in obj.data.vertices]
        return BVHTree.FromPolygons(verts,[list(p.vertices) for p in obj.data.polygons])
    cover=tree(bpy.data.objects['Sports_Car_Service_Cover'])
    clashes=[]
    for obj in VISUALS:
        if obj.name.startswith(('Drive_Motor_','Wheel_Tire_','TCRT5000_','IR_Trim_')) or obj.name in ('Battery_2S_LiPo','ESP32_S3','BLHeli_ESC','TB6612FNG','D4184_MOSFET','QF1611_EDF_Motor','EDF_30mm_Duct_Stators'):
            if cover.overlap(tree(obj)): clashes.append(obj.name)
    assert not clashes, 'Cover intersects '+', '.join(clashes)
    report['checks']=['Connected manifold printable solids','Four 6 V drive motors',
        'Direct chassis parenting','Applied scale','Open vacuum path through pad/chassis/adapter/EDF' ,
        'Shared wheel/motor axes','Wheel and roller board contact','Four unobstructed downward optical rays at 2.5 mm',
        'Cover/purchased-component surface interference check']
    known_mass=sum(o['Weight'] for o in VISUALS if o['Weight']>=0)
    CHASSIS['Assembly_Specified_Mass_g']=known_mass
    CHASSIS['Mass_Status']='Excludes unweighed new mounts, cover, pad, fasteners, shafts and bearings'
    report['specified_mass_g']=known_mass
    report['limits']=['Not pressure/flow or adhesion validated','EDF duct bore/length and N20 shaft geometry require measurement',
       'Fit coupon and actual part measurements required','No claim of full assembly interference certification']
    bpy.context.scene['Validation_Report']=json.dumps(report)
    log(f'\nValidation passed: {len(PRINTED)} manifold printable solids; '
        f'{len(VISUALS)} visual meshes; open vacuum passage; four aligned drive axes.')
    return report


def export_manufacturing(output,report):
    import json,struct
    directory=output/'manufacturing'; directory.mkdir(exist_ok=True)
    # Binary STL coordinates are explicitly mm, independent of Blender's unit settings.
    # Keep native assembly orientation and translate each part to its own build-plane datum.
    for obj in PRINTED:
        mesh=obj.data; mesh.calc_loop_triangles()
        points=[obj.matrix_world @ v.co / MM for v in mesh.vertices]
        min_z=min(p.z for p in points)
        center=Vector(((min(p.x for p in points)+max(p.x for p in points))/2,
                       (min(p.y for p in points)+max(p.y for p in points))/2,min_z))
        with (directory/(obj.name+'.stl')).open('wb') as f:
            f.write(b'Prototype mm; choose print orientation per assembly guide'.ljust(80,b' '))
            f.write(struct.pack('<I',len(mesh.loop_triangles)))
            for triangle in mesh.loop_triangles:
                a,b,c=(points[i]-center for i in triangle.vertices)
                normal=(b-a).cross(c-a).normalized()
                f.write(struct.pack('<12fH',*normal,*a,*b,*c,0))
    (directory/'validation_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    # Derive cutting contours from the actual pad's bottom faces, not an approximate outline.
    pad=bpy.data.objects['Full_Bottom_Sponge']; pad.data.update()
    points=[pad.matrix_world @ v.co / MM for v in pad.data.vertices]
    edge_counts={}
    for face in pad.data.polygons:
        if all(abs(points[i].z)<.0001 for i in face.vertices):
            ids=list(face.vertices)
            for i,a in enumerate(ids):
                edge=tuple(sorted((a,ids[(i+1)%len(ids)])))
                edge_counts[edge]=edge_counts.get(edge,0)+1
    edges={e for e,n in edge_counts.items() if n==1}; loops=[]
    while edges:
        a,b=edges.pop(); loop=[a,b]
        while loop[-1]!=loop[0]:
            candidates=[e for e in edges if loop[-1] in e]
            assert len(candidates)==1, 'Ambiguous pad cutting contour'
            edge=candidates[0]; edges.remove(edge)
            loop.append(edge[1] if edge[0]==loop[-1] else edge[0])
        loops.append(loop[:-1])
    xmin=min(p.x for p in points)-5; ymax=max(p.y for p in points)+5
    width=max(p.x for p in points)-xmin+5; height=ymax-min(p.y for p in points)+15
    path=' '.join('M '+' L '.join(f'{points[i].x-xmin:.4f},{ymax-points[i].y:.4f}' for i in loop)+' Z' for loop in loops)
    svg=f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width:.4f}mm" height="{height:.4f}mm" viewBox="0 0 {width:.4f} {height:.4f}">
<path d="{path}" fill="#9bb" fill-rule="evenodd" stroke="black" stroke-width="0.15"/>
<path d="M 5 {height-4} h 50" stroke="black" stroke-width="0.3"/><text x="5" y="{height-7}" font-size="3">50 mm — print at 100%</text></svg>'''
    (directory/'sponge_cutting_template.svg').write_text(svg,encoding='utf-8')
    for name in ('ASSEMBLY.md','SENSOR_MOUNT.md','MOUNTING_DATUMS.md'):
        source=Path(__file__).resolve().parent/'design'/name
        if source.exists(): shutil.copy2(source,directory/name)
    shutil.make_archive(str(output/'robot_print_prototypes'),'zip',directory)
    log(f'Exported {len(PRINTED)} individual mm STL prototypes, pad template and validation report.')


def presentation(output):
    from mathutils import Quaternion
    scene=bpy.context.scene
    scene.render.engine='CYCLES'; scene.cycles.samples=32
    scene.cycles.use_denoising=True
    scene.render.resolution_x=1400; scene.render.resolution_y=1100; scene.render.resolution_percentage=100
    scene.world.color=(.12,.12,.12)
    scene.view_settings.exposure=-1
    scene.render.image_settings.file_format='PNG'
    # Studio-only objects are deliberately excluded from export and component mass.
    studio=bpy.data.collections.new('Presentation — not exported'); scene.collection.children.link(studio)
    def move_to_studio(obj):
        for col in list(obj.users_collection): col.objects.unlink(obj)
        studio.objects.link(obj)
    floor=raw_box((2000,2000,4),(0,0,-3))
    floor.name='Studio_Floor'; floor.data.materials.append(material('Studio slate',(.038,.05,.068),.0,.75)); move_to_studio(floor)
    bpy.ops.object.camera_add(location=(.30,.38,.30)); camera=bpy.context.object; camera.name='Presentation_Camera'; move_to_studio(camera)
    camera.data.type='ORTHO'; camera.data.ortho_scale=.36; camera.data.clip_start=.001
    camera.rotation_euler=(Vector((.01,-.01,.018))-camera.location).to_track_quat('-Z','Y').to_euler(); scene.camera=camera
    for name,location,power,size in [('Key',(.1,.15,.4),6,.3),('Rim',(-.25,-.2,.25),8,.2),('Fill',(.3,-.1,.15),3,.25)]:
        bpy.ops.object.light_add(type='AREA',location=location); light=bpy.context.object; light.name='Studio_'+name; move_to_studio(light)
        light.data.energy=power; light.data.shape='DISK'; light.data.size=size
        light.rotation_euler=(-light.location).to_track_quat('-Z','Y').to_euler()
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=='VIEW_3D':
                area.spaces.active.clip_start=.0001
                area.spaces.active.region_3d.view_distance=.4
                area.spaces.active.region_3d.view_location=Vector((0,0,.02))
                area.spaces.active.region_3d.view_rotation=camera.rotation_euler.to_quaternion()
                area.spaces.active.shading.color_type='MATERIAL'
    bpy.ops.wm.save_as_mainfile(filepath=str(output/'Vacuum_Robot_Blockout.blend'))
    scene.render.filepath=str(output/'robot_assembled.png'); bpy.ops.render.render(write_still=True)
    # Underbody view reveals full pad coverage and the actual vacuum aperture.
    floor.hide_render=True
    camera.location=(.26,.32,-.28)
    camera.rotation_euler=(Vector((0,-.01,.015))-camera.location).to_track_quat('-Z','Y').to_euler()
    for obj in studio.objects:
        if obj.type=='LIGHT': obj.location.z=-abs(obj.location.z); obj.rotation_euler=(-obj.location).to_track_quat('-Z','Y').to_euler()
    scene.render.filepath=str(output/'robot_underbody.png'); bpy.ops.render.render(write_still=True)
    # Restore studio and produce the service view without changing component placements.
    floor.hide_render=False; camera.location=(.30,.38,.30)
    camera.rotation_euler=(Vector((.01,-.01,.018))-camera.location).to_track_quat('-Z','Y').to_euler()
    for obj in studio.objects:
        if obj.type=='LIGHT': obj.location.z=abs(obj.location.z); obj.rotation_euler=(-obj.location).to_track_quat('-Z','Y').to_euler()
    hidden=[]
    for obj in VISUALS:
        if obj.name in ('Sports_Car_Service_Cover','Exhaust_Grille') or obj['Part Type']=='Paint / vinyl graphic':
            obj.hide_render=True; hidden.append(obj)
    scene.render.filepath=str(output/'robot_service.png'); bpy.ops.render.render(write_still=True)
    for obj in hidden: obj.hide_render=False
    log('Rendered assembled, underside and service views.')


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
    parser.add_argument('--skip-render', action='store_true')
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
            organize_collections(scene)
            report = validate()
            export_manufacturing(output, report)
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
            if not args.skip_render:
                presentation(output)
            log('\nBUILD COMPLETE')
        except Exception:
            log('\nBUILD FAILED\n```\n' + traceback.format_exc() + '```')
            raise
        finally:
            LOG = None


if __name__ == '__main__':
    main()
