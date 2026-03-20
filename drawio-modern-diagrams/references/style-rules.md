# Draw.io Style Rules

## Style Source Order

Pick the style source in this order:

1. User-selected preset
2. User reference image
3. Diagram-type default preset from `config.json`

For preset details and image matching rules, read `references/style-profiles.md`.

## Visual Goal

Produce diagrams that feel modern, clean, calm, and presentation-ready.
Favor structure and visual grouping over connector clutter.

## Layout Defaults

- Use a clear primary reading direction. Default to left-to-right.
- Build obvious sections with columns, phase bands, swimlanes, or stacked cards.
- Leave generous whitespace around the outer frame and between peer blocks.
- Align peers to a shared grid. Small misalignments are more visible than extra empty space.
- Use container cards for milestones, summaries, and callouts instead of loose floating labels.

## Color Rules

- Use soft fills and low-contrast strokes.
- Prefer 2-4 accent families in one diagram.
- Keep the canvas itself light.
- Reserve stronger accent contrast for milestone cards, active bands, or key outcomes.

Suggested neutral base:

- background: `#FFFDF9` or `#FFFFFF`
- border: `#E6EAF0` or `#E8E3D8`
- body text: `#475569`
- title text: `#2F4858`

Suggested accent bands:

- warm: `#FDECEF`, `#F9D8DD`, `#E7A7AE`
- green: `#EEF9F1`, `#D8F0DF`, `#8FC7A2`
- blue: `#EEF5FE`, `#DCEBFA`, `#9EBFE5`

## Typography Rules

- Keep titles visually distinct. Body text should usually stay in the 11-14px range.
- Prefer two short lines over one dense line.
- Do not solve overflow by shrinking text below legibility.
- Use bold only for titles, phase names, or dates that need immediate scanning.

## Shape Rules

- Prefer rounded rectangles and simple cards.
- Use subtle shadows only on a few emphasis blocks.
- Avoid heavy strokes, harsh black borders, and saturated fills.
- Use labels, chips, and small cards to communicate metadata instead of extra arrows.
- If the diagram mixes physical machines and virtual gateways, separate them by shape family before adding extra text.

## Arrow Policy

- Avoid arrows unless the user explicitly needs dependency, causality, or sequence.
- Replace arrows with numbered steps, column order, section headers, or containment whenever possible.
- If arrows are unavoidable, keep them short, orthogonal when possible, and routed around blocks rather than through them.

## QA Checklist

Before considering the diagram done, check all of these:

- No clipped or crowded text
- No connector passing through unrelated cards
- No important label smaller than the surrounding body text without a reason
- No accidental overlaps between peer shapes
- No element drifting beyond the intended page bounds
- No cluster that would read more clearly as grouping instead of arrows
- If a reference image was used, the output should visibly match its tone and node styling without inheriting its structural flaws

## Command Loop

1. Export:

```bash
python3 scripts/drawio_skill.py sanitize-input --input path/to/file.drawio
python3 scripts/drawio_skill.py list-profiles
python3 scripts/drawio_skill.py show-profile --preset minimal-topology
python3 scripts/drawio_skill.py render --input path/to/file.drawio --out-dir path/to/outputs --strict
```

Never prepend Markdown, YAML front matter, or explanatory prose to the `.drawio` file itself. The file must remain valid draw.io XML rooted at `<mxfile>`.

If `render` cannot use the direct draw.io CLI, it will try the macOS helper executor first, then fall back to source-only mode and skip PNG/SVG export.
In source-only mode, QA should still remain pending when the requested export artifacts or the PNG review image are missing or stale.

If you still need exports, fall back to:

```bash
python3 scripts/drawio_skill.py export-commands --input path/to/file.drawio --out-dir path/to/outputs
/opt/homebrew/bin/drawio -x -f png -o path/to/outputs path/to/file.drawio
/opt/homebrew/bin/drawio -x -f svg -o path/to/outputs path/to/file.drawio
```

On Windows, `export-commands` defaults to PowerShell formatting. Use `--shell cmd` if the user needs `cmd.exe` commands instead.

2. Lint:

```bash
python3 scripts/drawio_skill.py qa-report --input path/to/file.drawio --out-dir path/to/outputs
```

3. Inspect the exported PNG visually.
4. Fix the `.drawio` source.
5. Repeat until the lint report is empty or intentionally accepted and the PNG looks balanced.
