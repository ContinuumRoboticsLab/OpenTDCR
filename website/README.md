# OpenTDCR website

## Open directly

Double-click `standalone/OpenTDCR.html` in Finder, or open it in Safari, Chrome, or Firefox. This single generated file embeds its scripts, fonts, and CAD model. No web server or sign-in is needed. WebGL is required for the 3D views. GitHub, research links, and the external MuJoCo demo require internet access.

The generated file can be moved independently of this folder. It is a generated build artifact and is excluded from source archives.

## Edit and rebuild

The editable website is in `dist/`. Preview it over HTTP when developing:

```sh
python3 -m http.server 4173 --directory dist
```

To regenerate the single file from the public repository root:

```sh
cd website
npm ci
npm run build:local
```

`build-local.mjs` bundles JavaScript into a classic inline script, inlines fonts and images, and decodes the embedded GLB directly. This avoids ES module and fetch restrictions on `file://` pages. Code and documentation are accessed through the GitHub link; no source archive is embedded in the page. Embedded JavaScript is syntax-checked during the build.

## Theme and assets

The primary color is **U of T Blue, #1E3765**, from the [2023 Colour Quick Guide](https://www.scribd.com/document/971068328/UofT-Colour-Guide-2023). The page uses a white background, navy text, and light gray controls. Official CRL and Open CR logos retain their original artwork and colors; provenance is recorded in `dist/assets/identity/sources.json`. Formerly white CAD components use neutral gray for contrast. Rendering materials are presentation choices.

Three.js and its Meshopt decoder are pinned to 0.181.0. DM Sans and Manrope fonts are local; their SIL OFL notices and source hashes are in `dist/assets/fonts/`. The standalone export retains the library/font notices in its source.

`dist/motion.js` animates a representative three-segment constant-curvature backbone above the STEP-derived actuation unit. Hovering over one of the three Clarke-coordinate pads holds that segment; dragging or arrow keys steers it; leaving resumes its smooth wandering motion. Dragging down sets positive coordinate y and bends the robot toward the viewer. The backbone begins at the top-face center of the supplied upper mount. A pause button and reduced-motion preference are supported. The backbone is illustrative, not measured CAD or a physics model, and never sends hardware commands.

`dist/assembly.js` separates the supplied CAD into 26 component groups as the reader scrolls: the ten original groups and sixteen spools extracted from disconnected solids in the merged servo mesh. The extracted spools match the supplied spool STL within tessellation tolerance; all original triangles are preserved. Blue plates and spools sit toward the front, with the off-the-shelf motor bank to the side. This is an inspection layout, not a slicer file or verified print orientation. Scrolling back exactly reassembles the model.

`dist/teleoperation.js` illustrates four stages: input devices, Clarke coordinates, coordinated tendons, and a tracing tip. Keyboard and wired DualSense are the released input paths; the haptic-device drawing represents a possible custom input adapter. The tendon stage cycles through 3, 4, 6, and 8 equally spaced tendons using the generalized Clarke transform, with a spatial bending segment and coordinated tendon pulls. Input illustrations use rigid joystick and haptic links. The diagram is explanatory and sends no hardware commands. `dist/studio.js` and `dist/cad.js` share rendering and model-loading helpers.

CAD conversion is documented in `../tools/cad/`. Refresh the rendered asset by copying `assembly-optimized.glb` and `manifest.json` to `dist/assets/cad/`. No hardware redistribution license is asserted by this website. Public source exports omit Site identity and local runtime state.

## Clarke coordinate reference

Reinhard M. Grassmann and Jessica Burgner-Kahrs. [Clarke Coordinates Are Generalized Improved State Parametrization for Continuum Robots](https://arxiv.org/abs/2503.12265), 2025. The page uses a representative constant-curvature mapping for the visual; Clarke coordinates are not themselves limited to constant-curvature models.

The code row links to [OpenTDCR on GitHub](https://github.com/ContinuumRoboticsLab/OpenTDCR). The project webpage is published at [GitHub Pages](https://continuumroboticslab.github.io/OpenTDCR/).

## GitHub Pages

The repository’s `.github/workflows/pages.yml` publishes `website/dist/` on pushes to `main` that change the website or deployment workflow. It can also be run manually. GitHub Pages must use **GitHub Actions** as its source. The self-contained `standalone/OpenTDCR.html` remains a separate local export; Pages serves the prepared static source and assets.
