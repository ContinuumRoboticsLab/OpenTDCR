# OpenTDCR

[Project webpage](https://continuumroboticslab.github.io/OpenTDCR/) · [Repository](https://github.com/ContinuumRoboticsLab/OpenTDCR)

Hardware designs and small, sensor-independent teleoperation tools for tendon-driven continuum robots.

OpenTDCR brings the mechanical files, tendon-space control, and setup instructions into one readable starting point. The hardware reference for this release is the supplied [STEP assembly](hardware/cad/assembly.step). The supplied assembly covers the actuation module and mounts; a complete flexible backbone design and build specification remain to be documented. The Python tools support configurable multi-segment robots; the example configuration is a teaching example, not a verified calibration of that assembly.

**Release candidate.** Software can be installed and exercised without hardware. Before publishing the hardware as an open-source design, finish the [hardware licensing, BOM, and assembly verification items](docs/release-checklist.md). Physical testing of the new motor and controller paths is still required.

## Start without a robot

From this directory, with Python 3.10 or newer:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
tdcr inspect --config configs/three_segment.example.json
tdcr teleop --config configs/three_segment.example.json --commands '1 w w 2 a q'
```

On Windows, activate with `.venv\Scripts\activate`. The commands above use the dry-run backend and do not connect to motors. No optical tracker, depth camera, ROS installation, or game controller is needed.

For interactive keyboard control:

```sh
tdcr teleop --config configs/three_segment.example.json
```

Type `w`, `a`, `s`, or `d`, then press Enter to move the selected segment by one configured step. Select a segment with `1`, `2`, or `3`; `home` requests the recorded reference posture; `q` exits. For a standard wired DualSense controller:

```sh
python -m pip install -e '.[gamepad]'
tdcr teleop --config configs/three_segment.example.json --input dualsense
```

Release L1 before startup. Hold L1 and use the left stick to bend the selected segment; D-pad up/down changes segments and Circle ends the session. The USB controller path uses bounded steps and freshness checks. Bluetooth and DualSense Edge are unsupported. See [getting started](docs/getting-started.md) for exact behavior and the physical-hardware workflow.

## Calibrate with your measurement sensor

Try the retained loosen, threshold-search, countback, and reference-capture sequence with synthetic measurements first:

```sh
tdcr calibrate --config configs/three_segment.example.json \
  --calibration-config configs/calibration.example.json
```

For physical calibration, use your own sensor adapter or the optional Lyra adapter and supply reviewed hardware settings. Movement thresholds, tendon countbacks, and search limits are configurable. `--teleop` continues in the same calibrated motor session; saved offsets are never automatically restored across a power cycle. See the [calibration guide](docs/calibration.md) for the complete sequence, parameters, and commands.

## Explore the project

| I want to… | Start here |
| --- | --- |
| Understand and assemble the hardware | [Hardware guide](docs/hardware.md) and [CAD inventory](hardware/README.md) |
| Inspect the supplied assembly | [STEP source](hardware/cad/assembly.step) |
| Run or adapt teleoperation | [Getting started](docs/getting-started.md), [configuration examples](configs/) |
| Calibrate tendon references | [Sensor-independent calibration](docs/calibration.md) |
| Plug in a measurement sensor | [Sensor contract and calibration boundary](docs/measurements.md), [adapter example](examples/sensor_adapter.py) |
| Run or edit the interactive webpage | [Website source](website/), [preview instructions](#website-and-release-tools) |
| Understand the code | [Architecture](docs/architecture.md), [agent instructions](AGENTS.md) |
| Reproduce the paper's simulation | [OpenCR-MuJoCo](https://github.com/ContinuumRoboticsLab/opencr-mujoco) |
| Prepare the release | [Release checklist](docs/release-checklist.md), [provenance](docs/release-audit.md) |

## A small control stack

The core maps a bend command for each segment to relative tendon length changes, including the contribution of proximal segments to tendons routed distally. A backend receives those targets. Dry-run is the default; hardware requires an explicit flag and a reviewed local configuration.

A sensor adapter reports a timestamped position in the robot base frame through a small Python interface. Teleoperation optionally checks measurement health. The separate calibration command uses measured displacement to find per-tendon reference positions, apply configured countbacks, and establish a new session zero. The workflow accepts your own sensor adapter or the optional Lyra adapter; it does not estimate tendon force or add closed-loop shape control to teleoperation.

The release preserves the lab's tendon calibration sequence in a reusable module. Lab-specific experiment scripts, recordings, hard-coded transforms, and one-off robot configurations remain outside the public tree. [The provenance notes](docs/release-audit.md) describe what was retained and what must be verified.

## Research context

This project accompanies the hardware work behind **Do Rigid-Body Simulators Dream of Soft Robots? Learning Contact-Rich Manipulation for Tendon-Driven Continuum Robots** (CoRL 2026), by Chengnan Shentu, Nicholas Baldassini, Tongjia Zheng, Priyanka Rao, and Jessica Burgner-Kahrs. The paper and its simulator are separate research artifacts. [Paper](https://arxiv.org/abs/2606.22397) · [project and interactive simulation](https://continuumroboticslab.github.io/opencr-mujoco/) · [BibTeX](docs/citation.bib).

The supplied assembly represents this hardware release. Its precise correspondence to the paper's experimental robot must be recorded before claiming an exact reproduction. The webpage's geometric explorer is an illustration; the linked OpenCR-MuJoCo demo provides the physics simulation.

The calibration workflow builds on **Automating Tension Calibration for Tendon-Driven Continuum Robots: A Low-Cost Approach Towards Consistent Teleoperation**, by Kyum Lee, Chengnan Shentu, Chloe Pogue, and Jessica Burgner-Kahrs (ICRA 2025). OpenTDCR adapts the lab's later position-threshold/countback procedure behind a sensor-independent interface; it does not claim to reproduce the paper's Hall-effect apparatus or measured tension accuracy. [Paper](https://doi.org/10.1109/ICRA55743.2025.11128689) · [Calibration guide](docs/calibration.md) · [BibTeX](docs/citation.bib).

## Development

```sh
python -m unittest discover -s tests -v
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for changes and the [architecture guide](docs/architecture.md) for extension points. Tests and dry-run examples require no physical devices.

## Website and release tools

The interactive project webpage is included as static source and assets in `website/`. Serve it locally from this directory:

```sh
python3 -m http.server 4173 --directory website/dist
```

Open [the local preview](http://localhost:4173). The CAD viewer uses the supplied actuation assembly; the shape explorer is an illustrative constant-curvature model. The physics demo links to the separate OpenCR-MuJoCo project.

To regenerate the CAD viewer assets from the release's STEP file, install the locked converter dependencies and provide both paths explicitly:

```sh
npm ci --prefix tools/cad
node tools/cad/convert-step.cjs hardware/cad/assembly.step website/dist/assets/cad
node tools/cad/optimize-glb.mjs website/dist/assets/cad
```

The converter preserves source appearance colors and records provenance; its materials and lighting are visualization choices. See [the converter notes](tools/cad/README.md) for details.

Create a clean distributable archive with:

```sh
python tools/package_release.py --output /tmp/OpenTDCR-source.zip
```

Choose an appropriate output path for your system. Review the [release checklist](docs/release-checklist.md) before publishing an archive.

## License and attribution

The software is released under the [MIT license](LICENSE) by the Continuum Robotics Laboratory, University of Toronto. The notice names the lab for this release and retains the original 2024 Chengnan Shentu notice for inherited code. Hardware and embedded supplier CAD require a separate, explicit licensing review; see [hardware/LICENSING.md](hardware/LICENSING.md). A software MIT notice alone is not a confirmed license grant for every object in the assembly.

## Local webpage

The webpage also builds to one HTML file that opens directly in a browser, including its CAD, fonts, and animations. Code and documentation are linked on GitHub. See `website/README.md` for the reproducible build commands. GitHub and the MuJoCo demo need internet access. The main theme uses the 2023 guide’s U of T Blue (`#1E3765`).
