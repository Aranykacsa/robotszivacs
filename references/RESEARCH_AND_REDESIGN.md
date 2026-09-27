# Manufacturing review and CAD references

Status: initial research snapshot. Revision 2 now implements the clarified architecture; see `../design/ASSEMBLY.md` and `../design/SENSOR_MOUNT.md`. The defects below describe the archived first blockout. Its manifold checks and headless smoke test validate geometry/software execution, not mechanical fit or manufacturability.

## Verified reference models

1. [Automatic Suction Powered Wall Climbing Robot](https://github.com/albindavidc/Automatic-Suction-Powered-Wall-Climbing-Robot)
   - Repository contains SolidWorks assembly `.SLDASM` and part `.SLDPRT` files, STL/3MF print parts, fan models, reports and test videos.
   - Downloaded `wall_climber_3D_Print.zip`. Closest reference for the suction adhesion architecture.
   - Assembly dependency resolution and dimensional compatibility with this robot have not been verified. GitHub reports no declared repository license; use as a reference, with reuse rights unresolved.
2. [iblowy](https://github.com/iROSLink/iblowy)
   - Confirmed `cad/iblowy.step` and `cad/iblowy.f3d` plus printable parts for a BLDC mount, fan housing halves, fan spacer, filter holder/frame, dust box, and brush motor mounts.
   - Downloaded the complete STEP file, BOM and MIT license. This is a floor vacuum, not a demonstrated wall-adhesion solution.
3. [D.A.W.E. whiteboard eraser](https://vip.bradley.edu/dawe/)
   - University project links a [public Onshape document](https://cad.onshape.com/documents/b87db0510eba9ebc45f2fa4b/w/fb9e55935966bfcd511138c9/e/75c1aa72cf430dedbd217dcf).
   - The page describes its printed frame and selected components. The Onshape link resolves, but its assembly contents/export were not inspectable through the text browser. Do not describe it as a verified downloadable complete vacuum robot.
4. [Pololu micro gearmotor and bracket CAD](https://www.pololu.com/product/1086/resources)
   - Manufacturer offers STEP models of a motor with its matching bracket.
   - Useful for actual clamping and fastener interfaces; not a silent substitution for the user's unspecified N20 motor.
5. [JSumo JS2622 wheel](https://www.jsumo.com/js2622-aluminum-silicone-wheel-pair)
   - Manufacturer specifies 26.5 mm diameter, 22 mm overall width, 3 mm bore and M4 setscrew.
   - This differs from the original 22 × 21 mm requirement. Exact wheel identity must be settled before machining/printing hub fits or fixing axle height.

Downloaded source paths and commit hashes are in `download_manifest.json`.

## Defects in the current blockout

- The chassis is solid beneath the vacuum motor. No through-port or sealed inlet-to-exhaust path exists.
- The sponge is only an 88 × 66 mm rectangular perimeter ring, not full-bottom coverage.
- The motor is a solid cylinder representing only an envelope; it contains no fan, inlet, exhaust or flange.
- Drive motors and wheels share a nominal axis but have no modeled output shafts, hub engagement, retainers or mounts.
- The roller has no shaft, bearings, coupling, supported ends or compression adjustment.
- Sensor modules float outboard; the battery and ESP32 have no supporting tray or standoffs.
- No assembly fasteners, inserts, tool access, cable passages or service access are provided.
- Collision helpers also fill the central chassis, so a new vacuum port must be reflected in collision geometry.
- The original 335 g is a specified mass total, not a weighed assembly. New mounts and hardware change the mass and center of gravity.

## Proposed revision, subject to requested construction choices

Keep a single continuous chassis solid with integral mounting bosses and wheel recesses. Add a genuine vacuum through-port matched to the selected blower inlet; do not assume inlet diameter equals its 40 mm outside diameter. Provide a sealed flange and gasket seat, an accessible exhaust and, if dust is collected, a serviceable filter path.

Replace the small skirt with a replaceable full-footprint sponge pad following the chassis perimeter and wheel reliefs. Whether the vacuum opening passes through the pad or draws through porous material is a user decision. The board-side air distribution, sponge permeability, compressed thickness and attachment layer must be considered together. A broad cleaning pad should not be assumed to behave like a perimeter vacuum seal.

Locate wheel hubs from actual output-shaft geometry and insertion length. Define motor saddles or clamp brackets with accessible fasteners, rather than a visual gap between motor and wheel. Add supported roller bearings, a motor coupling and a way to set contact pressure. Provide supported, adjustable downward sensor mounts and mechanically retained electronics/battery holders.

Before labeling the result fabrication-ready, check the chosen parts against their drawings, fastener engagement and access, printer-specific fits, minimum wall thickness, assembly order and removal of wear parts. Confirm pad drag, adhesion, wheel traction and motor loading experimentally; CAD alone cannot establish these.

## Questions recorded before revision 2

- Full pad with a vacuum opening, or continuous porous sponge?
- FDM with inserts, FDM with nuts/bolts, or another manufacturing process?
- Exact purchased parts, or documented candidate parts to review?
- Vacuum for adhesion, dust collection, or both?
- 140 × 120 mm chassis envelope, or maximum overall assembled footprint?

User subsequently specified a full pad with opening, adhesion-only vacuum, four drive motors, no fixed footprint limit and printed construction where practical. Product-specific fits remain provisional.
