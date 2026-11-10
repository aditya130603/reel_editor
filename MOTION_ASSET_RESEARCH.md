# Verified free motion-asset sources — November 2026

This catalog is a sourcing plan, not a claim that thousands of third-party templates are already installed in Reel Studio. The current local render engine uses original FFmpeg + Pillow components, avoiding heavy runtimes on the same VPS as OpenClaw.

| Repository | Verified contents | License / usage | Action for Reel Studio |
|---|---|---|---|
| https://github.com/ANVEAI/motion-pack | 287 motion/type entries, generated audio and transitions, camera treatments | Code MIT; generated media CC0; third-party fonts and examples separately licensed | **Best candidate:** selectively adopt CC0 SFX/music and original transition recipes after reviewing file-level license and resource requirements |
| https://github.com/reactvideoeditor/remotion-templates | 81 self-contained frame-driven Remotion components | README MIT | Use as examples or selectively port after a compatible Remotion worker exists; don't import all 81 into FFmpeg |
| https://github.com/ali-abassi/remotion-templates | 1,000 registry entries across 100 families | Repository warns to verify individual third-party provenance | Inspect catalog, choose a small original/verified subset, not a wholesale commercial license assumption |
| https://github.com/nexu-io/motion-anything | 403 recipes and video layer compositor | Apache-2.0 | Study motion grammar, safe motion budgets and export model; no need to install its AI agent |
| https://github.com/woernerm/retro_newspaper | Vox-inspired Fusion comps | Check exact source license before copying | Visual inspiration only; .drfx templates aren't native to server-side FFmpeg |
| https://github.com/Creative-Crafter/davinci-shortform-overlays | Vertical platform safe-zone guides | Check LICENSE | Adopt safe-zone concept in our custom layout tests |
| https://github.com/rse/vmix-assets | vMix XAML titles and virtual sets | MIT | Reimplement similar clean lower-third presentation without a vMix dependency |
| https://github.com/reactvideoeditor/free-react-video-editor | Browser timeline reference | Conflicting public README licensing statements; some commercial use requires RVE/Remotion licenses | Not bundled; verify terms before code reuse |
| https://github.com/kamalivaturi/kerf | Editing toolkit + MOGRT packs | Native editor integrations, larger application | Don't install into the VPS editor just to obtain MOGRTs |

Names mentioned but **not sufficiently verified as usable free asset sources**: open-design/motion-future, open-design/motion-showreel, SailorClippers/Adobe-After-Effects-Motion-Graphics-Templates. Don't clone or assign commercial licensing to these based on generated recommendation text alone.

## Benchmark from supplied clips

1. 16.3-second reference: constrained white kinetic lower-left text, occasional bold emphasis, clean circular metric interruption, icon callout, restrained visual density.
2. 25.9-second reference: cyan/green-lit talking head, energetic italic centered emphasis text, glowing bar/rating overlays, pricing comparison cards, ring HUD and small label. Distinct stages, not an effect on every word.

This maps to two reusable directions:

- **Editorial Clean:** fewer than four events per 30 s, clean typography, metric/timer diagrams, gentle motion, high subject visibility.
- **Neon Business:** lime/cyan floating cards, comparison metrics, rating and progress components, timing aligned to spoken keywords, subject matte if enabled.

Each component should only show quantities grounded in the speech or explicitly supplied data. Never invent ratings, prices, percentages or testimonials.

## Operating boundaries

- Free/local-only rendering, no recurring provider queues, remote model inference or API key.
- No copying logos/watermarks/identifiable branding from reference clips.
- Keep the 720x1280 core renderer; motion components can be generated at 360x640 and scaled.
- Cap generated assets to four short events per reel, and delete generated PNG frames immediately.
- Never install an entire optional Blender/Three.js/Node agent stack just to render a text card.
- Every third-party media import requires a documented source and license before production use.
