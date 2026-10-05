# Labelling guide (draft for the team to adopt or change)

Every test clause gets exactly one expected label **before** the app is run on it. Two team members
label independently; disagreements are discussed and the outcome recorded.

| Label | Use it when | Must cite |
| --- | --- | --- |
| `possibly_unlawful` | A specific section in `sources/` says this term is not allowed, is void, or cannot be waived. | The chunk ID(s) of that section |
| `unusual` | No source forbids it, but a typical Boston student lease would not contain it, or it shifts a cost or risk to the tenant in a way worth asking about before signing. | Nothing |
| `lawful` | Ordinary lease language, or a clause no source addresses and that is not unusual. | Nothing |

Rules of thumb:

- **Unlawful versus unfavourable.** If you cannot point to a sentence in `sources/` that forbids it,
  it is not `possibly_unlawful`, however unfair it feels. Use `unusual`.
- **Partly unlawful clauses** (for example a payments clause where one fee out of three is not allowed)
  are `possibly_unlawful`.
- **Terms that are enforceable only under conditions** (automatic renewal under c. 186 §15C) are
  `unusual`. Note the reasoning in the review log.
- **Citations.** List every chunk ID that would justify the label. A prediction citing any of them
  counts as a correct citation.

Where the labels live:

- Synthetic leases: `eval/clause_bank.py` (labels) and `eval/test_set/gold.json` (generated from it).
- Consented real leases: `eval/test_set/private/` (git-ignored), with its own `gold.json` in the same format.
