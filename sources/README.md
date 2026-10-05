# Sources the app reads

Every `## id | citation` section in the `.md` files here is one retrieval chunk. The app embeds them
(cached in `index.npz`) and shows the model only the passages most similar to each clause.

| File | Official source | Why we may use it |
| --- | --- | --- |
| `c186_15B_security_deposits.md` | https://malegislature.gov/Laws/GeneralLaws/PartII/TitleI/Chapter186/Section15B | Massachusetts General Laws, a public government publication |
| `cmr940_3_17_landlord_tenant.md` | https://www.mass.gov/regulations/940-CMR-3-general-regulations | Code of Massachusetts Regulations, a public government publication |
| `ag_guide_landlord_tenant.md` | https://www.mass.gov/guides/the-attorney-generals-guide-to-landlord-and-tenant-rights | Free public guide from the Attorney General's Office |

**The current files are paraphrased notes, not the official texts.** They were written without access
to the official sites. Before the demo:

1. Run `python scripts/fetch_sources.py`. It saves the official pages to `sources/official/`.
2. Go section by section and correct each note's wording and subsection number against the official
   text. Keep the `## id | citation` header format.
3. Delete `index.npz` (or just change any text; the cache rebuilds itself when the sources change).

The `ag_guide` file cites a few c. 186 sections beyond §15B (§14, §15, §15C, §18, §20). The guide is
where those come from. Add them to the proposal's source list or drop those chunks.
