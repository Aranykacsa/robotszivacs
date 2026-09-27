# Assembly-oriented prototype — revision 2

This revision implements four drive motors per the user's latest decision. The hardware PDF remains the component-family reference. The 140 × 120 mm limit is removed. The source files and complete model from the first blockout are preserved in `archive/blockout_v1/`.

## Interfaces implemented

- One continuous chassis: base, wheel wells, blind insert pockets, sensor seats, rear roller forks and wiper-motor extension.
- Full-footprint 2 mm sponge, with central 56 mm vacuum aperture and wheel/sensor reliefs. It is no longer a perimeter-only ring.
- Chassis through-port, flange gasket, removable tapered adapter, EDF inlet gasket, split casing clamp and QX-Motor 30 mm six-blade EDF with QF1611.
- Four matching motor clamps, 3 mm nominal output shafts, aluminum wheel hubs and silicone tires on common axes.
- Rear microfiber sleeve on a printed core, 3 mm steel axle, two 623 bearings, bearing shoulders, bolted retainers and a separate motor coupling.
- Printed electronics trays with support rails and retention-strap provision; battery/boards no longer float over the chassis.
- Four chassis-mounted sensor cartridges, shims and PCB edge clamps. See `SENSOR_MOUNT.md`.
- Bolted front charging-contact block.
- Removable 2 mm sports-style shell, racing graphics, wheel arches and an open exhaust grille.

## Printed and purchased parts

Print the chassis, adapter, EDF clamp, motor clamps, roller core, bearing retainers, coupling, electronics trays, sensor cartridges/shims/clamps, contact block, service cover and grille.

Use purchased motors/electronics, silicone tires/aluminum hubs, screws and inserts, 3 mm steel roller axle, two 623 bearings (3 × 10 × 4 mm), sponge, gaskets, microfiber and thin retaining straps. Small plastic screws, a printed high-speed fan and printed roller bearings are not assumed substitutes for these parts.

M2.5 inserts are represented with 3.6 mm nominal OD. The chassis uses 3 mm long inserts where its deck is only 4 mm thick, and 4 mm inserts in raised bosses. Match the actual insert's manufacturer's hole specification before printing; nominal CAD clearance is not a universal press-fit rule. Bearing retainers use M2 screws into printed pilot holes. Thread profiles are simplified in the visual model.

## Assembly sequence

1. Print fit coupons for the chosen insert, shaft, bearing and motor-clamp interfaces. Measure actual motor bodies, shaft profile/length, hub bore and EDF casing/bore before final fit.
2. Print the chassis flat, board face on the build plate. Inspect the uninterrupted vacuum sealing face and clear the blind insert bores. Use supports for horizontal bearing pockets where needed, or drill/ream to final fit.
3. Install heat-set inserts. Assemble the four drive motors, compliant clamp pads and clamps. Engage the output shafts in the wheel hubs and secure their set screws; check free rotation and board contact.
4. Assemble the rear shaft, bearings, roller core and bearing retainers. Fit the wiper motor and coupling. Secure the core, then install the microfiber sleeve. Confirm the sleeve's compressed outside diameter and actual board contact.
5. Install the electronics trays before the modules. Use thin hook-and-loop retention straps and keep connectors clear; printed supports do not replace battery restraint.
6. Install the sensor shims, cartridges, modules and edge clamps. Set optical height and calibrate on the actual board/frame.
7. Install the flange gasket, adapter, EDF inlet gasket and purchased EDF. Verify casing OD and clamp zone against the actual duct; keep the upward exhaust unobstructed. Air enters from the board chamber through the central opening and exits upward through the axial fan.
8. Cut the sponge using the 1:1 SVG template. Confirm the 50 mm scale bar. Attach with a thin removable adhesive, accounting for its thickness in the 2 mm compressed stack. Keep the vacuum aperture and sensor windows open. The pad also follows the rear chassis extensions; its pattern is extracted directly from the model.
9. Route wiring, install the pogo contacts, and close the service cover with its four flange screws. Bond the grille bezel to the cover after its fit test. The cover has no electrical connections.

Print small clamps/trays with their broad faces on the bed. Orient the roller core vertically for its bore, and the coupling so its bore can be finished accurately. The shell may require supports at the roof and arches; orient it after checking supports in the slicer. Exported STLs preserve assembly orientation but have their lowest Z translated to zero. They are in millimeters.

## Remaining physical validation

The PDF does not identify the EDF, N20 variant, wheel SKU, PCB layouts or insert supplier. The selected EDF is the [QX-Motor 30 mm six-blade unit with QF1611](https://www.qx-motor.net/products/qx-motor-30mm-6-blades-edf-unit-with-qf1611-7000kv-14000kv-6000kv-5000kv-brushless-motor). Its product listing identifies a nominal 30 mm fan and a QF1611 motor (16.3 mm diameter × 25 mm long, 1.5 mm shaft); it does not provide a dimensioned duct ID, length or mounting drawing. The model assumes a 25.5 mm bore and 16 mm duct length from the pictured envelope, so measure the delivered unit and adjust the adapter/clamp before printing final-fit parts. The seller lists motor-only weight 19.5 g and assembled EDF weight 21.8 g; the modeled 2.3 g casing/rotor share is their difference, an estimate. This is a buildable assembly approach with provisional purchased-part interfaces, not a production-qualified design.

The nominal wheel diameter remains 22 mm from the original brief. JSumo JS2622 is a different size; do not purchase it assuming it matches. Each N20 envelope is interpreted as a 26 mm body plus 10 mm shaft. Replace those parameters with actual measured dimensions before fabricating mounts. The model selects 14,000 KV to suit 2S; the listing's 2S test point is 19.3 A, 142.82 W and 215 g thrust at full throttle, and is not a suction-pressure curve. A 500 mAh 30C pack is nominally 15 A continuous, so that setup exceeds its stated rating by 4.3 A. Limit throttle or select a battery with adequate continuous-current rating, and use suitable ESC, wiring and thermal margins.

A 56 mm circular vacuum mouth has an area of approximately 0.00246 m². At an assumed 3 kPa pressure difference, its ideal normal force would be approximately 7.39 N. This is an illustrative calculation, not a blower performance claim. The broad sponge area is not automatically effective suction area. Adhesion depends on measured pressure under leakage, wheel friction, pad drag, actual mass, compression and peeling moments.

The full pad must not lift the wheels off the board when compressed. New supports/cover/hardware add unknown mass beyond the original estimate. The model's known-mass sum is not its finished weight.

The PDF rates the N20 motors at 6 V but supplies the motor driver from 2S. Electrical power conditioning/current capability, two motors per TB6612 channel, blower compatibility and charging circuitry remain separate engineering checks.
