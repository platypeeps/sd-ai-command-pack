# Work items

One directory per item, holding one `design.md`: `<YYYY-MM-DD>-<slug>/design.md`.
Write it only when the shape needs agreement before the code (sd:3000).
The item's sd row holds status, progress and decisions; `design.md` names it as `item: sd:<id>`.
Older items keep their `prd.md` and `implement.md`; write no new ones.

Status is read from the database.
Do not add `status:` to active PRD frontmatter.
Keep archived frontmatter as historical evidence.
Move completed items to `archive/YYYY-MM/` when their archive conditions hold.
The [archive index](archive/README.md) links the removed historical snapshot.
