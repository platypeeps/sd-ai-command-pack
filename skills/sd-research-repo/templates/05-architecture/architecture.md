# Architecture — Example Pipeline

Compiled 2026-10-21 from `owner/repo` @ `abc1234`, the service's public docs (read 2026-10-21), and ticket EX-1.

---

## 1. What this project studies

One or two sentences: the system or domain under study, where its boundary is, and what is out of scope.

## 2. The architecture at a glance

<div class="diagram">
<!-- Archify: draw the parts and their connections with the archify skill, export the diagram as SVG,
     and paste its <svg> element here in place of this comment, trailing whitespace stripped. The served
     page loads no external image; render scopes the diagram's styles to it. -->
</div>

```text
Without Archify, or for a Notion or Drive mirror: a plain diagram of the same parts.

  [ Client ] --HTTP--> [ Gateway ] --queue--> [ Worker ] --SQL--> [ Store ]
```

## 3. The parts and how they connect

| Part | What it does | Connects to | Source |
|---|---|---|---|
| Gateway | Accepts client requests and authenticates them | Worker, through a queue | `src/gateway/main.go:42` @ `abc1234` |
| Worker | Processes one request at a time | Store, over SQL | EX-1 |

## 4. Where each part is covered

| Part | Stage | Document |
|---|---|---|
| Gateway | 20-map | MAP-endpoints.md, rows C01 to C09 |
| Worker | 40-docs | SURVEY-worker.md |
| Store | not yet | named in open-questions.md |

## 5. Status

**Verified 2026-10-21:** which parts and connections were read in a source, and where.

**Not verified:** which parts or connections are inferred or assumed, and what would settle each.

**Diagram:** drawn with Archify on 2026-10-21, or why this page carries the plain diagram only.
