# Vacuum whiteboard robot — assembly prototype

The revised model uses **four drive motors**, a full-bottom sponge with an actual vacuum aperture, a gasketed adapter for a **QX-Motor 30 mm six-blade EDF / QF1611**, supported mechanical assemblies and a removable sports-car-style cover. Four TCRT5000 cartridges attach to the chassis ahead of/behind the wheels; they do not mount on the wheels.

The Blender Outliner groups parts under **Robot Components** into Chassis, Vacuum System, Drivetrain, Rear Wiper, Top Electronics, Board Sensors, Charging Contacts, Sports Car Body, Other Components and Collision Helpers. Toggle a collection's eye icon to hide/show that logical group; the individual meshes remain separate and parented to Chassis.

The hardware PDF supplies the component families. The user subsequently confirmed four motors, adhesion-only vacuum, no fixed footprint limit and a preference for printed construction. The selected EDF's duct ID/length and its mounting drawing are not supplied by the vendor, so the model's 25.5 mm bore and clamp fit are explicitly provisional. The model selects 14,000 KV for the 2S setup; check the marking on the actual motor. The vendor's 19.3 A 2S full-throttle point exceeds a 500 mAh 30C pack's nominal 15 A continuous rating.

## Open the result

- `Vacuum_Robot_Blockout.blend` — revised assembled model, component properties and studio setup.
- `robot_assembled.png`, `robot_underbody.png`, `robot_service.png` — assembled, underside and cover-off views.
- `robot_build_state.md` — flushed step-by-step component log, absolute dimensions/positions, build checks and completion status.
- `manufacturing/` — individual prototype STLs in mm, full-pad cutting template and validation report.
- `godot_vacuum_robot/project.godot` — playable whiteboard-cleaning demo built around the unchanged true-scale robot GLB.
- [Assembly and manufacturing notes](design/ASSEMBLY.md).
- [TCRT5000 mounting details and references](design/SENSOR_MOUNT.md).

The original blockout is preserved in `archive/blockout_v1/`. The original `robotszivacs.blend` is untouched.

## Generate everything

```bash
blender --background --python-exit-code 1 --python build_vacuum_robot.py -- --godot-bin /absolute/path/to/godot
```

For this machine's Flatpak Blender installation and downloaded validation binary:

```bash
flatpak run org.blender.Blender --background --python-exit-code 1 \
  --python "$PWD/build_vacuum_robot.py" -- \
  --godot-bin /home/aranykacsa/.cache/vacuum_robot_tools/godot
```

Optional arguments: `--output-dir DIR`, `--skip-render`, `--skip-godot`. Without an explicit Godot path, the script checks `GODOT_BIN`, then `godot4` and `godot` on PATH. Missing Godot is logged; an execution failure raises an exception. Rendering uses Cycles on the available device.

The script clears the current scene and replaces generated output. In Blender's Text Editor it writes beside the current `.blend`; in a fresh background session it writes beside the script. One Blender unit is one meter. STL export explicitly converts back to mm. X is right, Y is front, Z is away from the board; the board is Z=0 and the chassis base starts at Z=2 mm.

## What is checked

The script checks that every printed part is a connected manifold solid, that all robot meshes are directly parented to the one chassis object, and that object scale is applied. It checks four common shaft/hub axes, wheel and roller board contact, an open central passage and off-axis ray through EDF blade gaps, the sensors' unobstructed downward sightlines and nominal 2.5 mm optical-face height, and cover surface interference with the principal purchased-part envelopes. It exports Godot and runs headless import/runtime checks when Godot is available.

These checks do not establish actual component fit, pressure/flow performance, adhesion or production readiness. The print files are **fit prototypes**. Follow the assembly notes before fabricating final parts.

## Godot and physics metadata

The Godot project opens directly into a maximized, classroom-scale demo with Lorem Ipsum wrapped across fifteen whiteboard rows, leaving a marked lower-right docking bay. **W/S** throttle, **A/D** steer, **Home** performs a corner-parking approach and aligns the front pogo pins with two copper dock pads, and **R** resets the scene. The pad centers match the model's 32 mm pogo spacing and 104.1 mm pin reach; charging begins only when both simulated pin tips contact their pads. The robot erases text under its sponge footprint, shows cleaning progress and a one-minute battery countdown, charges while docked, and falls to the classroom floor when empty. **F11** toggles fullscreen. The robot model itself is unchanged.

Each robot mesh has `Weight` in grams, `Voltage` in volts and `Part Type`. Unknown masses/ratings are `-1`; properties distinguish generic envelopes, rated motor voltage and estimated mass. Drive motors are rated **6 V**, while the battery is **7.4 V nominal**. Do not infer electrical compatibility from the visual layout.

Helpers use `-colonly` for apertured structures and `-convcolonly` for simple envelopes. Godot removes helper visuals during import. The demo is static. Replace concave static geometry with suitable convex shapes under one `RigidBody3D` before attempting dynamic simulation; establish the finished assembly mass separately.

## References

- Local `Automata Vákuumos Táblatörlő Robot – Hardverspecifikáció.pdf`.
- [Research and downloaded complete CAD models](references/RESEARCH_AND_REDESIGN.md).
- [Vishay TCRT5000 datasheet](https://www.vishay.com/docs/83760/tcrt5000.pdf).
- [Blender glTF export API](https://docs.blender.org/api/current/bpy.ops.export_scene.html).
- [Godot import naming conventions](https://docs.godotengine.org/en/stable/tutorials/assets_pipeline/importing_3d_scenes/node_type_customization.html).
