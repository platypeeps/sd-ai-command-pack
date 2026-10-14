# Work items

One directory per item, holding one `design.md`: `<YYYY-MM-DD>-<slug>/design.md`.
Write it only when the shape needs agreement before the code (sd:3000).
The item's sd row holds status, progress and decisions; `design.md` names it as `item: sd:<id>`.
Older items keep their `prd.md` and `implement.md`; write no new ones.

Status is read from the database.
Do not add `status:` to active PRD frontmatter.
Keep archived frontmatter as historical evidence.
Delete a done item's folder once its sd notes hold what a later reader needs; a note names the commit that keeps it (sd:3569).
The [archive index](archive/README.md) links the removed historical snapshot.
