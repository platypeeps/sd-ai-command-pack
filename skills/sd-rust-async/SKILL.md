---
name: sd-rust-async
description: Use when writing, designing, or debugging async or multithreaded Rust — spawned tasks, channels, select loops, Send or 'static bound errors, suspected blocking inside async code, lock-across-await questions, or cancellation-safety concerns.
---

# sd-rust-async

Async Rust is cooperative: tasks yield only at `.await`, every `.await` is a
place the task can be cancelled, and every spawn is a resource that needs an
owner. This skill holds the discipline that keeps executors unblocked,
tasks accounted for, and cancellation survivable.

## When to use

Use when writing or restructuring async functions, spawning tasks, choosing
between blocking and async primitives, fixing `Send`/`'static` bound
errors, wiring shutdown, or deciding how concurrent work is dispatched and
collected.

Do not use for the domain types the tasks operate on — that is
`sd-rust-design` — or for general idioms — that is `sd-rust-quality`. For
judging a finished diff, `sd-rust-review` applies this bar as a local lens,
and the `sd-review` lane owns the verdict.

## Arguments

None.

This skill takes no `key=value` arguments.
Unknown argument names are an error — stop and report them before starting.

## Workflow

1. Establish the runtime context: which runtime and flavor the crate
   uses, whether the code is library or application, and what the
   surrounding code already does. Do not nest or interleave runtimes on
   one thread: entering one from inside another panics on either flavor,
   because the check is on the thread's runtime context and not on how
   many workers back it. Where a multi-thread runtime genuinely must block
   on async work, the sanctioned route is the runtime's own hand-off —
   `block_in_place`, then the current handle — never a second entry. Treat
   a second runtime on its own thread as a deliberate bridge to record,
   never a default. Keep library code runtime-agnostic where the
   API allows it, and record the runtime choice where a new one is made.
2. Keep the executor unblocked. Worker threads are scarce — roughly one
   per core — so a task that runs long between `.await` points starves
   every other task on that thread. There is no universal budget: the
   limit is whatever the service's latency target can absorb, so measure
   against that rather than a number quoted from a blog post. Route work
   by kind:
   - synchronous I/O (files, blocking database drivers) to the runtime's
     blocking pool (`spawn_blocking`);
   - sustained CPU-bound computation to a compute pool such as `rayon`,
     handing the result back over a oneshot channel;
   - a long-lived blocking loop to a dedicated `std::thread`.
   Blocking sleeps, sync file reads, and busy loops inside an async fn
   are defects, not style choices.
3. Satisfy `Send + 'static` by structure, not by force. Data held across
   an `.await` inside a spawned future must be `Send`: scope non-`Send`
   values (`Rc`, `RefCell`) so they drop before the `.await`, prefer
   `Arc` and `std::sync::Mutex` for shared state, and use `move` closures
   or `Arc` instead of borrowing from the caller — spawned tasks cannot
   borrow.
4. Lock with intent. Default to `std::sync::Mutex`: lock, operate, drop
   the guard before the next `.await`. Reach for the async mutex only
   when the guard genuinely must span an `.await`, and say so — it is
   slower and harder to reason about.
5. Design for cancellation. Any future can be dropped at any `.await` —
   racing branches drop the losers, timeouts drop the slow, shutdown
   drops everything. Do not leave shared state half-mutated across an
   `.await`; in racing branches use only operations that are safe to
   abandon mid-poll (a receive that loses the race must not have consumed
   a message it did not return); wire teardown through an explicit
   shutdown signal rather than relying on drop order.
6. Keep spawn hygiene: every spawned task has an owner. Hold the join
   handle or collect tasks into a set that is joined or aborted at
   shutdown; dropping a join handle detaches the task rather than
   stopping it, so it runs on unsupervised past the request that spawned
   it and swallows its own panics. Check join results —
   a task that panicked reports it there and nowhere else.
7. Remember `Drop` is synchronous. Cleanup that needs async work is
   handed off through a channel to a background task that performs the
   graceful shutdown; the drop impl only sends.
8. Pick the dispatch tool by shape: a task set with a join loop for a
   dynamic number of spawned tasks; join-all or try-join-all for a
   collection of futures; a select expression to race a fixed set; a
   stream of futures for pipelined processing; the fixed-arity join
   macros for a handful of differently-typed futures.

## Safety rules

- Never hide blocking by enlarging thread pools or sprinkling yields; fix
  the routing of the blocking work itself.
- Never hold a lock guard, database transaction, or other exclusive
  resource across an `.await` without stating why the async-aware
  primitive is required.
- Never claim code is cancellation-safe without walking its `.await`
  points; cancellation defects are invisible to the compiler and to
  happy-path tests.
- Do not silently change concurrency semantics — ordering, parallelism
  degree, backpressure — while refactoring; call every such change out.
- This skill informs authoring. It carries no review verdict; the
  `sd-review` lane owns review outcomes.

## Final report

- **Runtime context** — runtime, flavor, and any new choice recorded;
- **Blocking audit** — blocking work found in async context and where it
  was routed;
- **Bounds** — `Send`/`'static` conflicts hit and the structural fix
  applied;
- **Cancellation notes** — the `.await` points examined, the racing or
  timeout branches involved, and the state they can abandon;
- **Task ledger** — each spawn, its owner, and its shutdown path;
- **Open risks** — concurrency behavior the compiler cannot check and
  targeted tests do not yet cover.
