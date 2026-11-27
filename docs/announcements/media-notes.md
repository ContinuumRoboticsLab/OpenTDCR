# Announcement media

Prepared 26 November 2026 for the lab blog and LinkedIn drafts.

## OpenTDCR animation

- [GIF](https://continuumroboticslab.github.io/OpenTDCR/assets/blog/opentdcr-motion.gif): `website/dist/assets/blog/opentdcr-motion.gif`, 600 × 600, 14.21 seconds, 2,013,802 bytes.
- [MP4](https://continuumroboticslab.github.io/OpenTDCR/assets/blog/opentdcr-motion.mp4): `website/dist/assets/blog/opentdcr-motion.mp4`, 600 × 600, 14.214 seconds, 259,499 bytes. H.264, `yuv420p`, fast-start playback, no audio.

The animation uses the supplied actuation assembly CAD and an illustrative continuum backbone from the local OpenTDCR viewer (`motion.js`, `studio.js`, and `cad.js`). It is a render, not a measurement or recording of hardware motion. Credit: OpenTDCR, Continuum Robotics Laboratory, University of Toronto.

Production: 100 browser screenshots at 600 × 600, captured over 7.344 seconds, encoded at 14 frames per second. Reversed frames were appended without repeated endpoint frames to form the loop. The GIF uses a 128-color palette; the MP4 contains the same animation.

Suggested caption: **Actuation CAD from the supplied assembly, with illustrative backbone motion.** Use the GIF in the Markdown blog draft. The smaller MP4 is available for native social-video upload or a lab CMS video player.

## Physical hardware and companion experiment

- [Poster image](https://continuumroboticslab.github.io/OpenTDCR/assets/blog/tdcr-hardware.jpg): `website/dist/assets/blog/tdcr-hardware.jpg`, 1280 × 720. Copied unchanged from the [official OpenCR-MuJoCo poster](https://continuumroboticslab.github.io/opencr-mujoco/assets/compressed/all_rollouts_cylinder_task_blurred_poster.jpg), preserving its existing blur.
- [Experiment video](https://continuumroboticslab.github.io/opencr-mujoco/media/policies/all_rollouts_cylinder_task_blurred.mp4): existing public companion-project video, approximately 22.7 MB; HTTP 200 verified during preparation. The video is linked remotely and is not duplicated in this repository.

Credit: [OpenCR-MuJoCo](https://continuumroboticslab.github.io/opencr-mujoco/), Continuum Robotics Laboratory, University of Toronto. This media shows a physical TDCR in the companion learned-policy cylinder-manipulation experiment. It is not a demonstration of the released teleoperation code, and the pictured hardware is not asserted to match every detail of the supplied CAD.

Suggested caption: **Physical TDCR in the companion OpenCR-MuJoCo learned-policy experiment.** Retain the companion-project credit when reusing the poster or embedding its video.

The blog draft includes a video element for the lab CMS and a linked poster for Markdown viewers such as GitHub. Keep one presentation in the published lab post: the video player where supported, otherwise the linked poster. The remote clip requires an internet connection.
