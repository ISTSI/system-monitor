# Theme implementation contract

Light maps to Cool Slate; dark maps to Graphite Dusk. The JSON file is the token source of truth and the CSS file is its checked reference translation. These are not an implemented React theme provider. Do not choose a third palette from the older SPDN image.

Use `data-theme="light|dark"` on the root and pass the same resolved mode to React Flow's `colorMode`. Preference modes `default` and `system` resolve to one of those two themes; they are not extra visual themes. Implement all UI states using semantic tokens rather than duplicating component trees or hard-coding colours in nodes.

Normal text tokens on the designated opaque surfaces and match-highlight text have package-level contrast checks. Actual typography, overlays, transparency, disabled states, icons, focus indicators and browser rendering still require the application accessibility and visual tests. Decorative dividers are not substitutes for the stronger control/focus borders.

Preserve both attached images without edits. A reference image is not a webpage background, status-data fixture or license to hard-code the pictured logo. Build hierarchy, icon sizes, blue orthogonal arrows, selected-node outlines, process-details fields and log text as real components. Use self-contained, permitted icon assets; never ship workstation font files.
