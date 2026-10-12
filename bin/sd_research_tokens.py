"""The one visual identity every research repo renders with.

Inlined rather than shipped beside the renderer as `tokens.css`, because
`bin/` holds Python and nothing else -- `tests/test_no_shipped_shell.py` and the
Makefile's git-enumerated lint target both read that directory expecting it.
A stylesheet living here as data is the form that survives both.

The identity is the shared foundation in ui-design (`foundation/`), adopted
whole (sd:3584): its OKLCH tokens, its Dark · Light · System control and its
IBM Plex faces (`sd_research_fonts`). Two strings here are verbatim copies of
foundation files, and `tests/test_sd_research_kit.py` pins each by SHA-256:

    FOUNDATION_TOKENS_CSS   foundation/tokens.css -- never edit a value here
    THEME_JS                foundation/theme.js

When the foundation changes, paste the new file over its string and re-pin.
`PAGE_CSS` is the research page shell and the only part to edit; it names
tokens and never a colour value, which the same test enforces. `TOKENS_CSS`
stays the one name callers read: the renderer, and the system repo's design
documents, which reuse this stylesheet.
"""

FOUNDATION_TOKENS_CSS = """/* Hallmark · route: custom (bespoke) · structure: rail + annunciator + ranked ledger + evidence drawer · idea: "dark cockpit"
 * paper: dark oklch(17% 0.014 250) / light oklch(96% 0.006 250) · accent: cyan oklch(78% 0.11 210) / oklch(52% 0.115 215)
 * display: IBM Plex Sans · body: IBM Plex Sans · data: IBM Plex Mono · icons: Lucide
 * axes: dark / grotesk-sans / cool · gates: pass (see products/system/README.md § Slop test) · studied: no
 *
 * Instrument-panel foundation tokens. The default for personal dashboards,
 * development and tracking UIs (see principles.md). Copy this file; do not
 * restate its values inline.
 *
 * Theme: dark by default. Every colour token is light-dark(LIGHT, DARK), so
 * one list names both palettes. `color-scheme` picks the side:
 *   <html>                     dark (default)
 *   <html data-theme="dark">   dark
 *   <html data-theme="light">  light
 *   <html data-theme="system"> follows the OS
 * theme.js sets the attribute from the viewer's stored choice.
 */

:root {
  color-scheme: dark;

  /* Surfaces: blue-grey paper, raised panel, recessed well. */
  --color-paper:     light-dark(oklch(96%   0.006 250), oklch(17%   0.014 250));
  --color-panel:     light-dark(oklch(98.6% 0.004 250), oklch(20.5% 0.016 250));
  --color-well:      light-dark(oklch(93%   0.008 250), oklch(14.5% 0.013 250));
  --color-rule:      light-dark(oklch(84%   0.010 250), oklch(33%   0.018 250));
  --color-rule-2:    light-dark(oklch(90%   0.008 250), oklch(26%   0.016 250));

  /* Text. */
  --color-ink:       light-dark(oklch(21%   0.014 255), oklch(93%   0.010 250));
  --color-ink-2:     light-dark(oklch(38%   0.014 255), oklch(80%   0.014 250));
  --color-muted:     light-dark(oklch(49%   0.014 250), oklch(68%   0.018 250));

  /* Accent: cyan, the avionics colour for "selected". Selection, focus, live only. */
  --color-accent:     light-dark(oklch(52%  0.115 215), oklch(78%  0.11  210));
  --color-accent-bg:  light-dark(oklch(92%  0.035 210), oklch(29%  0.05  220));
  --color-accent-ink: light-dark(oklch(97%  0.005 210), oklch(17%  0.014 250));
  --color-focus:      light-dark(oklch(55%  0.19  215), oklch(80%  0.15  210));
  --color-scrim:      light-dark(oklch(21%  0.014 255 / 0.28), oklch(8% 0.012 250 / 0.6));

  /* State: the only other hues on the screen. Lamp = fill, text = on paper. */
  --color-ok:               light-dark(oklch(52% 0.12 150), oklch(76% 0.13 150));
  --color-ok-lamp:          light-dark(oklch(90% 0.06 150), oklch(32% 0.06 150));
  --color-caution:          light-dark(oklch(50% 0.11 70),  oklch(82% 0.13 85));
  --color-caution-lamp:     light-dark(oklch(89% 0.10 85),  oklch(31% 0.06 75));
  --color-caution-lamp-ink: light-dark(oklch(24% 0.02 70),  oklch(86% 0.12 85));
  --color-warning:          light-dark(oklch(50% 0.19 25),  oklch(70% 0.17 25));
  --color-warning-lamp:     light-dark(oklch(50% 0.19 25),  oklch(50% 0.17 25));
  --color-warning-ink:      light-dark(oklch(97% 0.01 25),  oklch(97% 0.01 25));
  --color-unknown:          light-dark(oklch(49% 0.014 250), oklch(68% 0.018 250));
  --color-hatch:            light-dark(oklch(80% 0.010 250), oklch(38% 0.016 250));

  /* Charts: neutral series; state and accent keep their meaning (patterns.md § Charts). */
  --color-series-1:  light-dark(oklch(38%   0.014 255), oklch(84%   0.014 250));
  --color-series-2:  light-dark(oklch(58%   0.014 250), oklch(62%   0.018 250));
  --color-series-3:  light-dark(oklch(76%   0.010 250), oklch(42%   0.016 250));
  --color-grid:      var(--color-rule-2);

  /* Type: two registers. */
  --font-ui:    "IBM Plex Sans", ui-sans-serif, sans-serif;
  --font-label: "IBM Plex Sans Condensed", "IBM Plex Sans", ui-sans-serif, sans-serif;
  --font-data:  "IBM Plex Mono", ui-monospace, monospace;

  /* Scale: minor third (1.2) from 16px; data rows sit at --text-sm. */
  --text-2xs: 0.694rem;
  --text-xs:  0.75rem;
  --text-sm:  0.875rem;
  --text-base:1rem;
  --text-md:  1.2rem;
  --text-lg:  1.44rem;
  --text-xl:  1.728rem;
  --text-2xl: 2.074rem;

  /* Space: 4pt. */
  --space-3xs: 0.125rem;
  --space-2xs: 0.25rem;
  --space-xs:  0.5rem;
  --space-sm:  0.75rem;
  --space-md:  1rem;
  --space-lg:  1.5rem;
  --space-xl:  2rem;
  --space-2xl: 3rem;
  --space-3xl: 4rem;

  --row:        2.25rem;   /* desktop data row */
  --row-touch:  2.75rem;   /* 44px: any row that is a control on touch */
  --rail:       13.5rem;
  --drawer:     26rem;
  --bulk-bar:   3.5rem;    /* sticky bulk-action bar */

  /* Icons: Lucide, stroked in currentColor. */
  --icon-sm:     1rem;     /* inline with --text-sm, help icons */
  --icon-md:     1.25rem;  /* buttons, row actions */
  --icon-stroke: 1.75;

  --rule-hair:  1px;
  --rule-lamp:  3px;
  --radius-sm:  3px;
  --radius-md:  5px;

  /* Shadows: only a floating layer casts one (popover, menu, toast, bulk bar, dialog; the bottom sheet casts upward). */
  --shadow-overlay: 0 8px 24px oklch(0% 0 0 / 0.3);
  --shadow-sheet:   0 -8px 32px oklch(0% 0 0 / 0.35);

  --ease-out:    cubic-bezier(0.22, 1, 0.36, 1);
  --ease-in:     cubic-bezier(0.64, 0, 0.78, 0);
  --ease-in-out: cubic-bezier(0.65, 0, 0.35, 1);
  --dur-fast:  120ms;
  --dur-base:  180ms;
  --dur-lamp:  420ms;
  --delay-help: 600ms;     /* hover preview of a help popover; focus and tap show at once */
}

:root[data-theme="light"]  { color-scheme: light; }
:root[data-theme="system"] { color-scheme: light dark; }
"""

THEME_JS = """// Theme control for foundation UIs: dark (default), light or system.
// Load it in <head> without defer, so the stored choice applies before first paint.
// Any element with data-theme-choice="dark|light|system" becomes a control;
// the selected one gets aria-pressed="true".
(() => {
  const KEY = 'theme';
  const CHOICES = ['dark', 'light', 'system'];
  const root = document.documentElement;

  const read = () => {
    try { const v = localStorage.getItem(KEY); return CHOICES.includes(v) ? v : 'dark'; }
    catch { return 'dark'; }
  };
  const mark = (choice) => {
    document.querySelectorAll('[data-theme-choice]').forEach((el) =>
      el.setAttribute('aria-pressed', String(el.dataset.themeChoice === choice)));
  };
  const apply = (choice) => {
    root.dataset.theme = choice;
    try { localStorage.setItem(KEY, choice); } catch { /* storage blocked: choice lasts this page */ }
    mark(choice);
  };

  root.dataset.theme = read();
  document.addEventListener('DOMContentLoaded', () => mark(root.dataset.theme));
  document.addEventListener('click', (e) => {
    const el = e.target.closest('[data-theme-choice]');
    if (el && CHOICES.includes(el.dataset.themeChoice)) apply(el.dataset.themeChoice);
  });
})();
"""

PAGE_CSS = """/* Hallmark · redesign · macrostructure: Long Document (rail + reading column) · tone: instrument panel, calm
 * theme: ui-design foundation, tokens above unchanged · display + body: IBM Plex Sans
 * labels: IBM Plex Sans Condensed · data: IBM Plex Mono · axes: dark / grotesk-sans / cool
 * pre-emit critique: P4 H4 E4 S4 R5 V3 · studied: no
 *
 * The research page shell, on the foundation's tokens only: no colour value
 * below this line, only a token name. */
:root{
  --measure:31rem;  /* long text: about 70 characters of Plex Sans a line */
  /* Older names a page shell outside this pack still reads (the system repo's
     design-document diagram figure). Drop them once that shell reads the
     foundation names. */
  --surface:var(--color-panel); --line:var(--color-rule); --line-soft:var(--color-rule-2);
  --sans:var(--font-ui); --ink-faint:var(--color-muted);
}
/* theme.js always sets data-theme. Without it the script did not run (a page
   served under a policy that blocks it), so there is no control to offer:
   follow the reader's OS instead of holding them to dark. */
:root:not([data-theme]){color-scheme:light dark}
:root:not([data-theme]) .theme{display:none}

*{box-sizing:border-box}
html,body{overflow-x:clip}
body{margin:0;background:var(--color-paper);color:var(--color-ink);font-family:var(--font-ui);
  font-size:var(--text-base);line-height:1.6;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
::selection{background:var(--color-accent-bg);color:var(--color-ink)}
:focus-visible{outline:2px solid var(--color-focus);outline-offset:2px}
.wrap{display:grid;grid-template-columns:var(--rail) minmax(0,1fr);gap:var(--space-2xl);
  max-width:84rem;margin:0 auto;padding:0 var(--space-xl) var(--space-3xl)}

/* rail */
.rail{position:sticky;top:0;align-self:start;max-height:100vh;overflow-y:auto;
  padding:var(--space-xl) 0 var(--space-lg)}
.rail .badge{display:flex;align-items:baseline;gap:var(--space-xs);padding-bottom:var(--space-sm);
  margin:0 var(--space-xs) var(--space-sm);border-bottom:var(--rule-hair) solid var(--color-rule)}
.rail .badge b{font-family:var(--font-label);font-size:var(--text-md);font-weight:600;color:var(--color-ink);
  overflow-wrap:anywhere;min-width:0}
.rail .badge span{font-family:var(--font-data);font-size:var(--text-2xs);color:var(--color-muted)}
.rail nav{display:grid;gap:1px;margin-bottom:var(--space-sm)}
.rail nav a{display:flex;align-items:center;gap:var(--space-xs);min-height:2rem;padding:0 var(--space-xs);
  border-radius:var(--radius-sm);text-decoration:none;font-size:var(--text-sm);line-height:1.3;color:var(--color-ink-2)}
.rail nav a:hover{background:var(--color-well);color:var(--color-ink)}
.rail nav a:focus-visible{outline-offset:-2px}
.rail nav a em{flex:none;min-width:1.5rem;font-family:var(--font-data);font-style:normal;font-size:var(--text-xs);
  color:var(--color-muted);font-variant-numeric:tabular-nums}
.rail nav a span{min-width:0;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.railnote{font-family:var(--font-data);font-size:var(--text-2xs);line-height:1.7;color:var(--color-muted);
  margin:0 var(--space-xs);padding-top:var(--space-sm);margin-top:var(--space-sm);
  border-top:var(--rule-hair) solid var(--color-rule-2);overflow-wrap:anywhere}
.railnote strong{display:block;font-family:var(--font-label);font-size:var(--text-xs);font-weight:600;
  color:var(--color-ink-2);margin-bottom:var(--space-3xs)}
.railnote a{color:var(--color-ink-2);text-underline-offset:2px}
.railnote code{font-family:var(--font-data)}

/* theme control: Dark · Light · System (foundation patterns.md) */
.theme{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:2px;padding:2px;
  margin:var(--space-lg) var(--space-xs) 0;border:var(--rule-hair) solid var(--color-rule);border-radius:var(--radius-md)}
.theme button{display:inline-flex;align-items:center;justify-content:center;min-height:2rem;
  padding:0 var(--space-2xs);border:0;border-radius:var(--radius-sm);background:transparent;color:var(--color-muted);
  font:500 var(--text-2xs)/1 var(--font-ui);white-space:nowrap;cursor:pointer}
.theme button:hover{color:var(--color-ink);background:var(--color-well)}
.theme button[aria-pressed="true"]{color:var(--color-ink);background:var(--color-panel);
  box-shadow:inset 0 0 0 1px var(--color-rule)}

/* masthead */
main{padding-top:var(--space-xl);min-width:0}
.eyebrow{font-family:var(--font-label);font-size:var(--text-sm);font-weight:500;color:var(--color-muted);
  margin:0 0 var(--space-xs)}
h1{font-family:var(--font-ui);font-style:normal;font-weight:600;
  font-size:clamp(var(--text-xl),1rem + 2.4vw,var(--text-2xl));line-height:1.15;letter-spacing:-.01em;
  text-wrap:balance;overflow-wrap:anywhere;min-width:0;max-width:var(--measure);margin:0 0 var(--space-sm)}
.subtitle{font-family:var(--font-data);font-size:var(--text-xs);color:var(--color-muted);
  font-variant-numeric:tabular-nums;margin:0 0 var(--space-lg)}
.subtitle b{font-weight:500;color:var(--color-ink-2)}
.standfirst{font-size:var(--text-md);line-height:1.5;color:var(--color-ink-2);max-width:var(--measure);
  margin:0 0 var(--space-lg)}
.meta{font-family:var(--font-data);font-size:var(--text-xs);line-height:1.75;color:var(--color-ink-2);
  background:var(--color-well);border:var(--rule-hair) solid var(--color-rule-2);border-radius:var(--radius-md);
  padding:var(--space-sm) var(--space-md);margin-bottom:var(--space-xl);overflow-wrap:anywhere}
.meta a{color:var(--color-ink)}
.meta code{background:none;border:0;padding:0}

/* verdict strip: the state grammar, a glyph beside every state colour */
.verdict{background:var(--color-panel);border:var(--rule-hair) solid var(--color-rule);border-radius:var(--radius-md);
  padding:var(--space-md) var(--space-lg);margin-bottom:var(--space-xl)}
.verdict h2{font-family:var(--font-label);font-size:var(--text-sm);font-weight:600;color:var(--color-ink-2);
  margin:0 0 var(--space-sm);border:0;padding:0}
.figs{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,10rem),1fr));gap:var(--space-md) var(--space-lg)}
.fig{display:flex;flex-direction:column;gap:var(--space-3xs);min-width:0}
.fig .n{display:flex;align-items:baseline;gap:var(--space-2xs);font-family:var(--font-data);font-size:var(--text-xl);
  font-weight:500;line-height:1.1;font-variant-numeric:tabular-nums;color:var(--color-ink)}
.fig .n .g{font-size:var(--text-sm);line-height:1}
.fig .n.is-pass{color:var(--color-ok)}
.fig .n.is-warn,.fig .n.is-caution{color:var(--color-caution)}
.fig .n.is-fail{color:var(--color-warning)}
.fig .n.is-flat,.fig .n.is-inert{color:var(--color-ink)}
.fig .l{font-size:var(--text-sm);line-height:1.35;color:var(--color-ink-2)}
.fig .s{font-family:var(--font-data);font-size:var(--text-2xs);line-height:1.5;color:var(--color-muted)}
.legend{font-family:var(--font-data);font-size:var(--text-2xs);line-height:1.7;color:var(--color-muted);
  margin-top:var(--space-md);padding-top:var(--space-sm);border-top:var(--rule-hair) solid var(--color-rule-2)}
/* :where keeps the base at one class, so each state rule below wins */
:where(.legend) .chip{display:inline-flex;align-items:baseline;gap:var(--space-2xs);font-family:var(--font-data);
  font-size:var(--text-2xs);font-weight:500;padding:var(--space-3xs) var(--space-xs);margin:var(--space-3xs) var(--space-xs) var(--space-3xs) 0;
  border:var(--rule-hair) solid var(--color-rule);border-radius:var(--radius-sm);color:var(--color-ink-2)}
.chip--pass{color:var(--color-ok)}
.chip--pass::before{content:"●" / ""}
.chip--hyp,.chip--caution{background:var(--color-caution-lamp);color:var(--color-caution-lamp-ink);border-color:transparent}
.chip--hyp::before,.chip--caution::before{content:"▲" / ""}
.chip--fail{background:var(--color-warning-lamp);color:var(--color-warning-ink);border-color:transparent}
.chip--fail::before{content:"■" / ""}
.chip--acc{color:var(--color-unknown);border-style:dashed;border-color:var(--color-hatch)}
.chip--acc::before{content:"▨" / ""}

/* document body: tables and code take the column, long text keeps the measure */
.doc :is(p,ul,ol,dl,blockquote,h2,h3,h4){max-width:var(--measure)}
.doc h2,.doc h3,.doc h4{font-style:normal;text-wrap:balance;scroll-margin-top:var(--space-lg)}
.doc h2{font-size:var(--text-lg);font-weight:600;line-height:1.25;margin:var(--space-2xl) 0 var(--space-sm);
  padding-bottom:var(--space-xs);border-bottom:var(--rule-hair) solid var(--color-rule)}
.doc h3{font-size:var(--text-md);font-weight:600;line-height:1.3;margin:var(--space-xl) 0 var(--space-xs)}
.doc h4{font-family:var(--font-label);font-size:var(--text-base);font-weight:600;color:var(--color-ink-2);
  margin:var(--space-lg) 0 var(--space-2xs)}
.doc p{margin:0 0 var(--space-md)}
.doc strong{font-weight:600;color:var(--color-ink)}
.doc a{color:var(--color-ink);text-decoration:underline;text-decoration-color:var(--color-muted);
  text-underline-offset:.2em;overflow-wrap:anywhere}
.doc a:hover{text-decoration-color:var(--color-ink)}
.doc ul,.doc ol{margin:0 0 var(--space-md);padding-left:var(--space-lg)}
.doc li{margin-bottom:var(--space-2xs)}
.doc li::marker{color:var(--color-muted)}
.doc code{font-family:var(--font-data);font-size:.875em;background:var(--color-well);
  border:var(--rule-hair) solid var(--color-rule-2);border-radius:var(--radius-sm);padding:0 .3em;overflow-wrap:anywhere}
.doc blockquote{margin:var(--space-lg) 0;padding:var(--space-2xs) 0 var(--space-2xs) var(--space-md);
  border-left:var(--rule-lamp) solid var(--color-rule);color:var(--color-ink-2)}
.doc hr{border:0;border-top:var(--rule-hair) solid var(--color-rule);margin:var(--space-2xl) 0}

.table-wrap{overflow-x:auto;border:var(--rule-hair) solid var(--color-rule);border-radius:var(--radius-md);
  background:var(--color-panel);margin:var(--space-lg) 0}
.doc table{border-collapse:collapse;width:100%;font-size:var(--text-sm);line-height:1.45}
.doc th{font-family:var(--font-label);font-size:var(--text-xs);font-weight:600;color:var(--color-ink-2);
  text-align:left;padding:var(--space-xs) var(--space-sm);background:var(--color-well);
  border-bottom:var(--rule-hair) solid var(--color-rule);white-space:nowrap}
.doc td{padding:var(--space-xs) var(--space-sm);border-bottom:var(--rule-hair) solid var(--color-rule-2);
  vertical-align:top;color:var(--color-ink-2);font-variant-numeric:tabular-nums}
.doc tr:last-child td{border-bottom:none}
.doc td:first-child{color:var(--color-ink)}
.doc td code{background:none;border:0;padding:0}

.doc pre{overflow-x:auto;background:var(--color-well);border:var(--rule-hair) solid var(--color-rule-2);
  border-radius:var(--radius-md);padding:var(--space-sm) var(--space-md);margin:var(--space-lg) 0}
.doc pre code{background:none;border:0;padding:0;font-size:var(--text-xs);line-height:1.55;
  color:var(--color-ink-2);white-space:pre;overflow-wrap:normal}

footer{max-width:var(--measure);margin-top:var(--space-3xl);padding-top:var(--space-sm);
  border-top:var(--rule-hair) solid var(--color-rule);font-family:var(--font-data);font-size:var(--text-xs);
  line-height:1.75;color:var(--color-muted)}
footer a{color:var(--color-ink-2)}

@media (max-width:899px){
  .wrap{grid-template-columns:minmax(0,1fr);gap:0;padding:0 var(--space-md) var(--space-2xl)}
  .rail{position:static;max-height:none;padding:var(--space-lg) 0 0}
  .rail nav{display:none}
  .rail .badge{border-bottom:0;margin-bottom:0}
  .theme{max-width:16rem}
  main{padding-top:var(--space-lg)}
}
@media (pointer:coarse){.rail nav a,.theme button{min-height:var(--row-touch)}}
@media (forced-colors:active){
  .verdict,.table-wrap,.chip,.theme{border-color:CanvasText}
  .theme button[aria-pressed="true"]{outline:2px solid Highlight}
}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""

TOKENS_CSS = FOUNDATION_TOKENS_CSS + "\n" + PAGE_CSS
