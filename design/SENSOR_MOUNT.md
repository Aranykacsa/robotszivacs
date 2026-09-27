# TCRT5000 mount

The four sensors are mounted to the chassis, at X = ±43 mm and Y = ±87 mm. Wheel axles are at X = ±75 mm and Y = ±62 mm. No sensor or bracket attaches to a wheel, hub or motor clamp.

Each assembly contains a removable printed cartridge, a 0.5 mm height shim, an edge clamp with a soft pad, and two M2.5 screws on 38 mm centers. The PCB sits on a supported ledge, while the optical package projects down through a cartridge aperture and a chassis window. The clamp bears on a PCB edge; it leaves the potentiometer accessible. This avoids inventing mounting holes on an unspecified breakout board.

The initial optical-face height is 2.5 mm above the board. Increasing shim thickness raises the sensor by the same amount; regenerate all associated sensor geometry when changing this parameter. The package is mounted pointing down (-Z), with its optical center displaced 10 mm toward the corresponding side of the chassis. The front/rear positions keep its sightline clear of the tires.

The Vishay datasheet specifies a 10.2 × 5.8 × 7 mm bare sensor package and a 2.5 mm peak operating distance. This is a starting point, not a guarantee that a particular frame, ink mark or whiteboard will produce a reliable threshold. Set the threshold on the actual board and frame after establishing the assembled contact height.

The generic PCB envelope remains 32 × 14 mm. Exact breakout variants differ in connector, trimmer and sensor placement. The cartridge is a replaceable prototype interface until the chosen module is measured.

References:
- [Vishay TCRT5000 datasheet](https://www.vishay.com/docs/83760/tcrt5000.pdf)
- [Ed Nisley's sensor mounting flange source](https://gist.github.com/ednisley/beb4491fc8db1e6960ebe8ec7dc56e7b) — reference for a supported optical-package aperture; dimensions concern the bare sensor, not the entire breakout board.
- [dehager's two-piece TCRT5000 mount and shims](https://cults3d.com/en/3d-model/tool/tcrt5000-sensor-mount-for-erc-timsav-diy-cnc-needle-cutter/makes) — reference for serviceable clamping and height adjustment. The robot's cartridge is newly modeled, not a downloaded mount with unverified fit.
