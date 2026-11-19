# Plan Shape: Placement, Nesting, Deletion

Read this when appending a step to a specific position, nesting sub-steps, or removing part of
the plan.

## Where a step lands

Ordering inside a level is a float score assigned **once, at insert**. Nothing re-scores a step
later, so decide placement in the `append` call.

`afterStepId` controls position among the children of the `parentStepId` you passed:

| `afterStepId` | Result |
|---|---|
| omitted, or `"last"` | end of that level (the default, and usually what an honest plan wants) |
| `"head"` | front of that level |
| a real sibling step id | immediately after that sibling |

Several nodes in one append keep the order you listed them, at successive positions.

Give sibling steps distinct positions and let the platform assign the scores. Steps that end up
with equal scores render in arbitrary order, so the user sees them **reshuffle every few seconds**
as the view polls.

### Three ways a concrete `afterStepId` is rejected

- The parent has **no children yet** → *"An afterStepId was passed in for a parent with no
  children"*. Only `null`, `"head"`, or `"last"` are accepted there.
- The id is not a **direct child** of the `parentStepId` you passed → *"is not a child of the
  given parent"*. Never reuse an id from another branch.
- The id belongs to an **old plan version** → 404 *"afterStep does not exist in the plan"*.

Recovery for all three: `list_job_plan_steps`, pick a real sibling of that parent, retry.

## Nesting

`parentStepId` is either the literal `"root"` (case-insensitive) for a top-level step, or an
existing step id in the **current** plan version to nest under — a stale or unknown parent 404s.

`afterStepId` positions **only the top level of your request**. Any `subSteps` you send are laid
out at fresh, evenly spaced scores under their new parent. So you cannot reach an
already-populated sub-level through a nested `subSteps` list: to insert a sub-step between two
existing sub-steps, issue a separate `append` whose `parentStepId` is that parent and whose
`afterStepId` is the sibling it should follow.

## Deletion

Delete **bottom-up**. A step with any non-deleted child is rejected with *"Attempting to delete a
plan step that has substeps"*. To remove a subtree: list that step's children, delete every leaf,
then the parent.

Deletion is a soft delete. After it succeeds, treat the id as dead — later `update_job_plan_step`
or append-under-it calls 404, and the step disappears from listings. Anything already attached to
it stays attached to a step the user can no longer see, so prefer marking a step `FAILED` over
deleting it when work was genuinely attempted.

## Moving or renaming a step

There is no move and no rename. `update_job_plan_step` changes only `status`, `startTime`,
`endTime`, and `description`; `stepName`, `stepLabel`, and the parent are immutable.

If a step truly must move or be renamed: append a replacement in the right position, then delete
the old one. The replacement has a **new id**, so re-point your bookkeeping — anything already
attached to the old step stays on the old step. Don't promise the user a reorder you can't
perform.
