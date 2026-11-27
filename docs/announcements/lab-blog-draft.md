# OpenTDCR: sharing our hardware and teleoperation tools

> Launch draft for the lab website — not posted. The media below link to the project’s GitHub Pages assets and the companion experiment video.

We’ve released **OpenTDCR**, the hardware designs and simple teleoperation tools developed for our tendon-driven continuum robot experiments at the University of Toronto’s Continuum Robotics Laboratory. We hope they help others build and explore continuum robots.

![OpenTDCR actuation assembly with an animated, illustrative continuum backbone](https://continuumroboticslab.github.io/OpenTDCR/assets/blog/opentdcr-motion.gif)

*Actuation CAD from the supplied assembly, with illustrative backbone motion.*

The release includes CAD, 3D-printed components, and Python tools for keyboard or wired DualSense teleoperation. You can try the software without motors, adapt the robot configuration, and connect your own measurement sensor.

We’ve also retained our tendon calibration sequence, with configurable movement thresholds and tendon countbacks. It can use Lyra or another sensor and builds on [our ICRA 2025 calibration paper](https://doi.org/10.1109/ICRA55743.2025.11128689) by Kyum Lee, Chengnan Shentu, Chloe Pogue, and Jessica Burgner-Kahrs.

OpenTDCR grows out of the hardware work behind our CoRL 2026 research and complements [OpenCR-MuJoCo](https://continuumroboticslab.github.io/opencr-mujoco/), our simulation project.

<!-- Lab CMS: use this video player. The linked poster below is the portable GitHub fallback; retain one presentation when publishing the lab post. -->
<video controls playsinline preload="none" poster="https://continuumroboticslab.github.io/OpenTDCR/assets/blog/tdcr-hardware.jpg" aria-label="Physical tendon-driven continuum robot performing a learned-policy cylinder manipulation experiment" style="width: 100%; height: auto;">
  <source src="https://continuumroboticslab.github.io/opencr-mujoco/media/policies/all_rollouts_cylinder_task_blurred.mp4" type="video/mp4">
  <a href="https://continuumroboticslab.github.io/opencr-mujoco/media/policies/all_rollouts_cylinder_task_blurred.mp4">Watch the physical TDCR experiment video.</a>
</video>

[![Physical TDCR in the companion learned-policy experiment; select to watch the video](https://continuumroboticslab.github.io/OpenTDCR/assets/blog/tdcr-hardware.jpg)](https://continuumroboticslab.github.io/opencr-mujoco/media/policies/all_rollouts_cylinder_task_blurred.mp4)

*Physical TDCR in the companion OpenCR-MuJoCo learned-policy experiment.*

Explore the [project webpage](https://continuumroboticslab.github.io/OpenTDCR/) or find the files and instructions on [GitHub](https://github.com/ContinuumRoboticsLab/OpenTDCR). Feedback and contributions are welcome.

---

Acknowledgements: Chengnan Shentu, Kyum Lee, Puspita Triana Dewi, and Jessica Burgner-Kahrs.
