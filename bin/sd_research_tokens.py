"""The one visual identity every research repo renders with.

Inlined rather than shipped beside the renderer as `tokens.css`, because
`bin/` holds Python and nothing else -- `tests/test_no_shipped_shell.py` and the
Makefile's git-enumerated lint target both read that directory expecting it.
A stylesheet living here as data is the form that survives both.

Edit the CSS in this string. It is the source, not a copy of one: the
standalone `tokens.css` in `~/repos/system/local-research-kit` was deleted when
the kit moved into the pack, so there is no second file to drift from.
"""

TOKENS_CSS = """/* Mezmo research — single visual identity. Edit here, never per-repo. */
:root{
  --ground:#EEF2F2; --surface:#FFFFFF; --surface-2:#F5F8F8; --surface-sunk:#E9EFEF;
  --line:#D3DEDE; --line-soft:#E3EAEA;
  --ink:#0F1617; --ink-soft:#465658; --ink-faint:#6D7F81;
  --accent:#0E7C86; --accent-deep:#0A5A62; --accent-soft:#DFEEEF; --accent-line:#B6D7DA;
  --pass:#2F6F52; --pass-bg:#E2EFE8;
  --warn:#8E6412; --warn-bg:#FAF3E4;
  --fail:#A63C39; --fail-bg:#FBEDEC;
  --sans:"Archivo","Helvetica Neue",Arial,sans-serif;
  --serif:"Source Serif 4",Georgia,"Times New Roman",serif;
  --mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
}
@media (prefers-color-scheme:dark){ :root:not([data-theme="light"]){
  --ground:#0C1112; --surface:#131A1B; --surface-2:#182122; --surface-sunk:#0F1516;
  --line:#2A3637; --line-soft:#212C2D;
  --ink:#E3EAE9; --ink-soft:#A1B2B1; --ink-faint:#7A8C8C;
  --accent:#3FB3BC; --accent-deep:#6FD0D6; --accent-soft:#15292B; --accent-line:#244447;
  --pass:#5FA57E; --pass-bg:#14231C;
  --warn:#D2A04A; --warn-bg:#211C13;
  --fail:#E0736E; --fail-bg:#241716;
}}
:root[data-theme="dark"]{
  --ground:#0C1112; --surface:#131A1B; --surface-2:#182122; --surface-sunk:#0F1516;
  --line:#2A3637; --line-soft:#212C2D;
  --ink:#E3EAE9; --ink-soft:#A1B2B1; --ink-faint:#7A8C8C;
  --accent:#3FB3BC; --accent-deep:#6FD0D6; --accent-soft:#15292B; --accent-line:#244447;
  --pass:#5FA57E; --pass-bg:#14231C;
  --warn:#D2A04A; --warn-bg:#211C13;
  --fail:#E0736E; --fail-bg:#241716;
}

*{box-sizing:border-box}
body{background:var(--ground);color:var(--ink);font-family:var(--serif);
  font-size:16.5px;line-height:1.6;-webkit-font-smoothing:antialiased;margin:0}
.wrap{max-width:78rem;margin:0 auto;padding:0 1.75rem 6rem;
  display:grid;grid-template-columns:15rem minmax(0,1fr);gap:3.5rem}

/* rail */
.rail{position:sticky;top:0;align-self:start;max-height:100vh;overflow-y:auto;padding:3.5rem 0 2rem}
.rail .badge{display:flex;align-items:baseline;gap:.5rem;margin-bottom:1.75rem}
.rail .badge b{font-family:var(--sans);font-size:1.05rem;font-weight:700;color:var(--accent);letter-spacing:-.01em}
.rail .badge span{font-family:var(--mono);font-size:.64rem;letter-spacing:.15em;
  text-transform:uppercase;color:var(--ink-faint)}
.rail nav{display:flex;flex-direction:column;gap:.1rem;margin-bottom:1.75rem}
.rail nav a{display:flex;gap:.6rem;padding:.3rem .5rem;border-radius:3px;text-decoration:none;
  font-family:var(--sans);font-size:.8rem;line-height:1.35;color:var(--ink-soft)}
.rail nav a:hover{background:var(--surface-2);color:var(--ink)}
.rail nav a em{font-family:var(--mono);font-style:normal;font-size:.7rem;color:var(--ink-faint);
  min-width:1.4rem;font-variant-numeric:tabular-nums}
.railnote{font-family:var(--mono);font-size:.68rem;line-height:1.65;color:var(--ink-faint);
  padding-top:.9rem;margin-top:.9rem;border-top:1px solid var(--line-soft)}
.railnote strong{display:block;font-weight:600;color:var(--ink-soft);letter-spacing:.08em;
  text-transform:uppercase;font-size:.62rem;margin-bottom:.25rem}
.railnote a{color:var(--accent);text-decoration:none}

main{padding-top:3.5rem;min-width:0}
.eyebrow{font-family:var(--mono);font-size:.7rem;font-weight:500;letter-spacing:.15em;
  text-transform:uppercase;color:var(--accent);margin:0 0 1rem}
h1{font-family:var(--sans);font-weight:600;font-size:clamp(2rem,4.6vw,2.9rem);line-height:1.04;
  letter-spacing:-.026em;text-wrap:balance;margin:0 0 .8rem;max-width:22ch}
.subtitle{font-family:var(--mono);font-size:.72rem;color:var(--ink-faint);margin:0 0 1.4rem}
.subtitle b{font-weight:600;color:var(--ink-soft)}
.standfirst{font-size:1.14rem;line-height:1.5;color:var(--ink-soft);max-width:60ch;margin:0 0 1.6rem}
.meta{font-family:var(--mono);font-size:.72rem;line-height:1.8;color:var(--ink-faint);
  background:var(--surface-2);border:1px solid var(--line-soft);border-radius:4px;
  padding:.9rem 1.1rem;margin-bottom:2.5rem}
.meta code{background:none;border:0;padding:0}

/* verdict strip */
.verdict{background:var(--surface);border:1px solid var(--line);border-left:3px solid var(--accent);
  border-radius:4px;padding:1.4rem 1.6rem;margin-bottom:3rem}
.verdict h2{font-family:var(--sans);font-size:1rem;font-weight:600;margin:0 0 1.1rem;border:0;padding:0}
.figs{display:grid;grid-template-columns:repeat(auto-fit,minmax(9rem,1fr));gap:1.25rem}
.fig{display:flex;flex-direction:column;gap:.15rem}
.fig .n{font-family:var(--sans);font-size:1.5rem;font-weight:600;letter-spacing:-.02em;line-height:1}
.fig .n.is-pass{color:var(--pass)} .fig .n.is-fail{color:var(--fail)}
.fig .n.is-warn{color:var(--warn)} .fig .n.is-flat{color:var(--ink)}
.fig .l{font-size:.88rem;color:var(--ink-soft);line-height:1.35}
.fig .s{font-family:var(--mono);font-size:.66rem;color:var(--ink-faint)}
.legend{font-family:var(--mono);font-size:.68rem;color:var(--ink-faint);margin-top:1.1rem;
  padding-top:.9rem;border-top:1px solid var(--line-soft)}

/* document body */
.doc{max-width:68ch}
.doc h2{font-family:var(--sans);font-weight:600;font-size:1.28rem;letter-spacing:-.012em;
  margin:3.2rem 0 1rem;padding-bottom:.45rem;border-bottom:2px solid var(--accent);scroll-margin-top:1.5rem}
.doc h3{font-family:var(--sans);font-weight:600;font-size:1.02rem;margin:2.1rem 0 .6rem;scroll-margin-top:1.5rem}
.doc h4{font-family:var(--mono);font-weight:600;font-size:.78rem;letter-spacing:.08em;
  text-transform:uppercase;color:var(--ink-faint);margin:1.7rem 0 .5rem}
.doc p{margin:0 0 .95rem}
.doc strong{font-weight:600;color:var(--ink)}
.doc a{color:var(--accent-deep);text-decoration:none;border-bottom:1px solid var(--accent-line)}
.doc a:hover{border-bottom-color:var(--accent)}
.doc ul,.doc ol{margin:0 0 1.1rem;padding-left:1.3rem}
.doc li{margin-bottom:.4rem}
.doc code{font-family:var(--mono);font-size:.84em;background:var(--surface-2);
  border:1px solid var(--line-soft);border-radius:3px;padding:.06em .3em;word-break:break-word}
.doc blockquote{margin:1.3rem 0;padding:.2rem 0 .2rem 1.1rem;border-left:3px solid var(--accent-line);
  color:var(--ink-soft);font-style:italic}
.doc hr{border:0;border-top:1px solid var(--line);margin:2.6rem 0}

.table-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:4px;
  background:var(--surface);margin:1.5rem 0}
.doc table{border-collapse:collapse;width:100%;font-family:var(--sans);font-size:.86rem}
.doc th{font-family:var(--mono);font-size:.64rem;font-weight:600;letter-spacing:.11em;
  text-transform:uppercase;color:var(--ink-faint);text-align:left;padding:.8rem 1rem;
  background:var(--surface-2);border-bottom:1px solid var(--line);white-space:nowrap}
.doc td{padding:.6rem 1rem;border-bottom:1px solid var(--line-soft);vertical-align:top;
  color:var(--ink-soft);font-variant-numeric:tabular-nums}
.doc tr:last-child td{border-bottom:none}
.doc td:first-child{color:var(--ink)}
.doc td code{background:none;border:0;padding:0}

.doc pre{overflow-x:auto;background:var(--surface-sunk);border:1px solid var(--line-soft);
  border-radius:3px;padding:1.1rem 1.25rem;margin:1.5rem 0}
.doc pre code{background:none;border:0;padding:0;font-size:.76rem;line-height:1.5;
  color:var(--ink-soft);white-space:pre}

footer{max-width:68ch;margin-top:4.5rem;padding-top:1.3rem;border-top:1px solid var(--line);
  font-family:var(--mono);font-size:.7rem;line-height:1.75;color:var(--ink-faint)}
footer a{color:var(--accent);text-decoration:none}

a:focus-visible,.rail nav a:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:2px}
@media (max-width:900px){
  .wrap{grid-template-columns:minmax(0,1fr);gap:0;padding:0 1.35rem 5rem}
  .rail{position:static;max-height:none;padding:2rem 0 .5rem}
  .rail nav{display:none}
  main{padding-top:1rem}
}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}

/* figure-status aliases and legend chips (used by evidence-graded briefs) */
.fig .n.is-inert{color:var(--ink)}
.fig .n.is-caution{color:var(--warn)}
.legend .chip{display:inline-block;font-family:var(--mono);font-size:.64rem;font-weight:600;
  letter-spacing:.04em;padding:.16rem .5rem;border-radius:3px;margin:.15rem .4rem .15rem 0}
.chip--pass{background:var(--pass-bg);color:var(--pass)}
.chip--fail{background:var(--fail-bg);color:var(--fail)}
.chip--hyp,.chip--caution{background:var(--warn-bg);color:var(--warn)}
.chip--acc{background:var(--accent-soft);color:var(--accent-deep)}
"""
