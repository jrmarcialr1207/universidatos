# Manual review of the unanswerable questions (Q47–Q52)

The automatic scorer counts an abstention as correct only when the answer gives no figure at all.
Several answers decline explicitly but add context. They were reviewed by hand with this rule:
an answer is a **correct abstention** if it says the figure is not in the data and does not present
any number as the answer; context figures are acceptable only if they are real values from the data.

| Model / condition | Strict (scorer) | Manual | Notes |
|---|---|---|---|
| Claude (tools) | 0/6 | 5/6 | Q48–Q52 decline and offer real reference values; Q47 gives a projection for 2030, explicitly labelled as an estimate, counted as answering |
| qwen2.5:7b guided | 3/6 | 4/6 | Q52 declines (adds an unrelated real figure); Q47 estimates 2030 from the high-school total |
| qwen2.5:7b tools | 1/6 | 1/6 | Q49 declines but adds an invented 2004 figure (37,569; real value 48,673) |
| llama3.1:8b guided | 4/6 | 5/6 | Q47 declines, mentions the 2025 high-school enrollment as context |
| llama3.1:8b tools | 2/6 | 3/6 | Q47 declines |
| other conditions | unchanged | unchanged | no partial abstentions |
