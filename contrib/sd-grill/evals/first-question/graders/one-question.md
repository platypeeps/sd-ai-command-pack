---
type: llm
---

The response opens an interrogation of the user's proposal. Before its first
question it states a classification and invites the user to override it; the
skill requires that invitation, and it is not an interrogation question.

Pass if the response puts exactly one interrogation question to the user.
Fail if it puts two or more, counting a restatement of the same question as a
second one, or none.
