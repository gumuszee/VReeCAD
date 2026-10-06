# Licensing review (not legal advice)

## Our position
BlocksCAD (this repo) is a fork of **freecad-xr-workbench** by Adrian Przekwas. We stay **LGPL-3.0-or-later**.
Diverging from upstream without merging back is allowed.

| Component | Licence | Relationship | What we must do |
|---|---|---|---|
| freecad-xr-workbench (base of this repo) | LGPL-3.0-or-later (`LICENSE`, `package.xml`, file headers say "version 3 or any later") | Forked and modified | Keep `LICENSE` and the existing copyright headers; modified files stay LGPL-3.0+; add our own copyright line to files we substantially change; changes are documented by git history; new files get the same LGPL header. Original author stays credited (`package.xml` `<author>`, `docs/upstream/README-freecad-xr-workbench.md`). |
| Upstream controller models `Resources/controllers/*.iv`, icons | **no separate licence stated** (inherit the repo's) | Shipped in this repo | Provenance unverified. Controller models are replaced by own models in M0; icons are redrawn when touched. |
| FreeCAD | LGPL-2.1-or-later | We call its Python API; not bundled | none beyond normal use |
| pyopenxr | Apache-2.0 | runtime dependency, installed via pip, not bundled | none |
| PyOpenGL | BSD-style | runtime dependency | none |
| Open Blocks / Blocks by Google | Apache-2.0 (copyright "The Blocks Authors", Google LLC) | **inspiration only**; no code or assets from it are included | If we ever copy code/assets: keep Apache headers + NOTICE, mark changes; Apache-2.0 is compatible with LGPL-3.0 combined works. Ideas/UX concepts themselves are not covered by copyright. Never copy Google's logos/brand assets. |
| freecad-mcp (dev tooling only) | MIT | third-party RPC addon used as a dev remote-control channel in `refs/`; not part of BlocksCAD | not distributed with the addon; no dependency from the addon |
| Open Blocks docs/brand | trademark guidelines | - | see below |

## Naming (flag for the owner)
- **"Blocks" is a Google trademark** (`refs/open-blocks/BRAND_GUIDELINES.md`): clones/derivatives must choose a distinct name; using "Blocks" inside a different product name is a grey area but we do not imply affiliation. We do not use Google's logo/trade dress.
- **"BlocksCAD" is already an existing, unrelated product** (a web-based block-coding front-end for OpenSCAD, blockscad3d.com; unverified). A public project/addon with the same name risks confusion, search collisions and a name clash in the FreeCAD Addon Manager. The repository is named `BlocksCAD_VR` and the workbench `BlocksCAD` at the owner's request; a more distinctive name is advisable before publishing to the Addon Manager.

## Repository hygiene
- Commits are authored with the owner's git identity only; no AI attribution lines.
- Do not commit secrets, tokens, or the dev-only `.mcp.json` (git-ignored).
