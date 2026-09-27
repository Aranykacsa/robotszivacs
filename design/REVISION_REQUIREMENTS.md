# Revised requirements

User decisions:
- Full-bottom sponge pad with a vacuum opening.
- Vacuum provides whiteboard adhesion, not dust collection.
- Prefer printed construction; use conventional hardware when it makes a better assembly.
- No fixed 140 × 120 mm envelope. Sports-car styling is desired.
- Hardware reference: `Automata Vákuumos Táblatörlő Robot – Hardverspecifikáció.pdf`.

PDF findings:
- Four Shore 20A silicone wheels with aluminum hubs, approximate combined mass 30 g.
- Two N20 drive motors, 100:1 or 300:1, rated 6 V, approximate combined mass 20 g.
- One additional N20 wiper motor, approximate mass 10 g.
- Selected QX-Motor 30 mm six-blade EDF with QF1611; duct bore/length, flange, pressure/flow curve and mounting drawing still not supplied.
- 2S 7.4 V 500 mAh 30C battery; BLHeli ESC with BEC; ESP32-S3; TB6612FNG; D4184; four TCRT5000 modules; pogo contacts.
- Original 1–2 mm sealing skirt is estimated at 10 g. Full-pad replacement mass cannot be assumed equal.
- The electronics table does not supply board outlines or mounting-hole patterns.
- PDF's estimated 225 g excludes printed chassis. Its individual listed masses total 225 g with two drive motors and a 10 g skirt.

Unresolved interface choices:
- RESOLVED: four drive motors, one per wheel, explicitly confirmed by user.
- Proceed with replaceable prototype interfaces; exact purchased-part fits remain unresolved.

Engineering interpretation:
- Keep motors rated at 6 V in properties; do not describe 7.4 V battery voltage as motor rating.
- The PDF's direct 2S motor rail requires electrical review for 6 V motors and driver current; not validated by the mechanical model.
- A full pad and an adhesion chamber must share a defined airflow path and seal. The central port should connect to the blower inlet through a gasketed adapter.
- Do not equate blower outside diameter with inlet diameter.
- Small conventional screws, steel shafts and bearings are preferable to inventing printable equivalents for rotating/load-bearing interfaces. Nonstructural panels may use printed locating features.
- Product-specific fit, pressure/flow performance, pad compression/drag and wheel traction still require physical measurements and prototype testing.
