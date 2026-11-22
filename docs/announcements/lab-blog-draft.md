# OpenTDCR: sharing our hardware and teleoperation tools

> Launch draft — assumes the repository and project page are public when posted. The webpage link uses the default GitHub Pages address; update it if a different URL is chosen.

We’ve released **OpenTDCR**, the hardware designs and simple teleoperation code we developed for tendon-driven continuum robot experiments in the Continuum Robotics Laboratory at the University of Toronto. These tools have been useful in our own work, and we hope they can help others build and explore continuum robots.

The release includes CAD for a modular actuation unit, 3D-printed components, and a small Python toolkit for keyboard or wired DualSense teleoperation. You can try the control software in dry-run mode before connecting motors, adapt the robot configuration, and connect your own measurement sensor through a simple adapter interface.

We have also retained our tendon calibration sequence and separated it from the measurement hardware. It can use the Lyra adapter or another sensor, with movement thresholds and tendon countbacks supplied in configuration. This workflow builds on [our ICRA 2025 calibration paper](https://doi.org/10.1109/ICRA55743.2025.11128689) by Kyum Lee, Chengnan Shentu, Chloe Pogue, and Jessica Burgner-Kahrs.

OpenTDCR grows out of the hardware work behind our CoRL 2026 research and complements [OpenCR-MuJoCo](https://continuumroboticslab.github.io/opencr-mujoco/), our companion simulation project.

Explore the design on the [project webpage](https://continuumroboticslab.github.io/OpenTDCR/), or find the files and instructions on [GitHub](https://github.com/ContinuumRoboticsLab/OpenTDCR). Feedback and contributions are welcome.

---

Acknowledgements: Chengnan Shentu, Kyum Lee, Puspita Triana Dewi, and Jessica Burgner-Kahrs. Suggested visual: one assembly rendering or a short teleoperation clip.
