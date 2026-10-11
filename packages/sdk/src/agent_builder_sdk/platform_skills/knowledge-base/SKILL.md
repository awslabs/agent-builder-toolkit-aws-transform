---
name: knowledge-base
description: Use to look up authoritative AWS or AWS Transform product knowledge when a factual question would otherwise be a guess — service limits, API/feature specifics, how the product expects something done. Covers retrieve_from_knowledge_base and its two scopes.
---

# Knowledge Base Lookup

`retrieve_from_knowledge_base` searches a curated knowledge base and returns relevant passages.
Reach for it instead of guessing when a decision turns on a fact you're not sure of — an AWS
service limit or behavior, an API detail, or how the AWS Transform product expects a task to be
done.

```
retrieve_from_knowledge_base(retrieval_query="...", retrieval_scope="AWS" | "PRODUCT")
  -> {"retrieved_content": ["passage", ...]}
```

## Pick the scope

- `AWS` — general AWS knowledge: service behavior, limits, API specifics (e.g. "S3 Tables
  Iceberg compaction defaults", "Glue job bookmark semantics").
- `PRODUCT` — AWS Transform product knowledge: how the product/platform itself works and what
  it expects (e.g. "how Transform surfaces a migration deliverable to the user").

Choose by where the answer lives. When unsure which side a question falls on, query the more
likely scope first and re-query the other only if the result is thin.

## Rules

- Query with specific terms, not a whole sentence of context — you're searching, not chatting.
- Treat results as **reference, not ground truth about this job**: they inform your reasoning,
  they don't override what you observed in the customer's actual data or what the user told you.
  When a passage conflicts with the live data, the live data wins.
- If a lookup returns nothing useful, say what you couldn't confirm rather than inventing an
  answer — an unconfirmed fact is a question for the user, not a guess.
- This is read-only background knowledge; it is not a source of customer data (that comes
  through a connector).
