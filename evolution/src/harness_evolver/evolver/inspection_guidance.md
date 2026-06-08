# Code Inspection Decision Criteria

## When to Use Detailed Code Inspection

The evolution history provides high-level summaries for fast pattern recognition.
Use git diff to inspect actual code changes when you encounter these signals:

### 🚨 MUST INSPECT (High Priority)

1. **Validation Regression**
   - Training improved BUT validation dropped
   - Signal: Possible overfitting to training data
   - Action: `git diff <prev_sha>..<curr_sha>` to see what was added
   - Goal: Identify training-specific changes to remove

2. **Unclear Causation**
   - History says "Added X" but outcome is unexpected
   - Example: "Added error handling" → validation dropped 10%
   - Signal: Summary may miss important details
   - Action: Check actual code changes
   - Goal: Understand what really happened

3. **Regression After Success**
   - Task flipped to pass, then regressed back to fail
   - Signal: Fragile change or unintended side effects
   - Action: Compare the two states
   - Goal: Identify what broke the task again

### ⚠️ SHOULD INSPECT (Medium Priority)

4. **Multiple Failed Attempts**
   - Same type of change tried 2+ times with similar results
   - Signal: Pattern not clear from summaries
   - Action: Review exact changes across attempts
   - Goal: Avoid repeating the same mistake differently

5. **Large Changes with Mixed Results**
   - History mentions many changes, outcomes vary
   - Signal: Need to separate what worked from what didn't
   - Action: Review full diff
   - Goal: Extract successful patterns

6. **Contradictory Patterns**
   - History shows pattern A works, but later pattern A fails
   - Signal: Context or implementation differs subtly
   - Action: Compare the two implementations
   - Goal: Understand the difference

### 💡 COULD INSPECT (Low Priority)

7. **Curiosity or Verification**
   - Pattern is clear but want to verify assumption
   - Action: Quick spot-check
   - Goal: Build confidence

8. **Learning Context**
   - First few steps, building mental model
   - Action: Review changes to understand codebase
   - Goal: Understand what's being evolved

## How to Decide: Decision Tree

```
┌─────────────────────────────────┐
│ Read evolution_history.md       │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ Is validation trend diverging?  │
│ (train↑ val↓)                   │
└────────┬────────────────────────┘
         │
    YES  │  NO
    ┌────▼────┐
    │ INSPECT │
    │ Priority│
    │ HIGH    │
    └─────────┘
         │
         ▼
┌─────────────────────────────────┐
│ Is the outcome surprising?      │
│ (expected improvement but got   │
│  regression, or vice versa)     │
└────────┬────────────────────────┘
         │
    YES  │  NO
    ┌────▼────┐
    │ INSPECT │
    │ Priority│
    │ HIGH    │
    └─────────┘
         │
         ▼
┌─────────────────────────────────┐
│ Have I seen similar pattern     │
│ fail before? (check history)    │
└────────┬────────────────────────┘
         │
    YES  │  NO
    ┌────▼────┐
    │ INSPECT │
    │ Priority│
    │ MEDIUM  │
    └─────────┘
         │
         ▼
┌─────────────────────────────────┐
│ Pattern is clear enough?        │
└────────┬────────────────────────┘
         │
    YES  │  NO
         │  ┌────▼────┐
         │  │ INSPECT │
         │  │ Priority│
         │  │ LOW     │
         │  └─────────┘
         ▼
┌─────────────────────────────────┐
│ Proceed with pattern-based      │
│ decision (no inspection needed) │
└─────────────────────────────────┘
```

## Commands to Use

### View Changes Between Steps
```bash
git --git-dir=<snapshots_dir> diff <prev_sha>..<curr_sha>
```

### View Specific File Changes
```bash
git --git-dir=<snapshots_dir> diff <prev_sha>..<curr_sha> -- AGENT.md
```

### View Full File at Step
```bash
git --git-dir=<snapshots_dir> show <sha>:AGENT.md
```

### Compare Across Multiple Steps
```bash
# See cumulative changes from baseline to step 3
git --git-dir=<snapshots_dir> diff baseline..post_step_003
```

## Examples

### Example 1: Clear Pattern (No Inspection)

```markdown
## Step 1
Training: 50% (+15%)
Validation: 45% (+10%)
Evolution Output: Added error handling section
```

**Decision**: Pattern is clear - error handling helped both metrics.  
**Action**: Continue building on this success. No inspection needed.

---

### Example 2: Overfitting Signal (MUST INSPECT)

```markdown
## Step 2
Training: 60% (+10%)
Validation: 40% (-5%) ⚠️
Evolution Output: Added mandatory keyword_search rule
```

**Decision**: Training improved but validation dropped = overfitting!  
**Action**: 
```bash
git diff post_step_001..post_step_002 -- AGENT.md
```
**Findings**: Added "MANDATORY: Always call keyword_search before ANY task"  
**Insight**: "ANY task" is too broad, training-specific. Need to simplify.

---

### Example 3: Unclear Causation (SHOULD INSPECT)

```markdown
## Step 3
Training: 65% (+5%)
Validation: 50% (+10%) ✅
Flipped: batch_operations, concurrent_updates
Regressed: simple_query, basic_list
Evolution Output: Restructured instruction flow
```

**Decision**: Good overall but why did simple tasks regress?  
**Action**:
```bash
git diff post_step_002..post_step_003
```
**Findings**: Moved basic instructions to later section, added complex rules at top  
**Insight**: Simple tasks now read complex rules first, getting confused.

---

### Example 4: Pattern from History (Medium Priority)

```markdown
## Step 4
History shows:
- Step 1: Added rules → validation dropped
- Step 2: Simplified → validation recovered
- Step 3: Added rules again → validation flat
- Step 4: Should I simplify again?
```

**Decision**: Pattern suggests "adding complexity hurts validation" but is it the SAME kind of complexity?  
**Action**:
```bash
git diff post_step_001..post_step_002  # First complexity
git diff post_step_003..post_step_004  # Second complexity
```
**Findings**: First was training-specific examples, second was general principles  
**Insight**: General principles OK, specific examples are the problem.

## Summary

**Default**: Trust the summary and make pattern-based decisions (80% of cases).

**Inspect when**:
- Validation trend diverges from training (overfitting signal)
- Outcome is surprising/unclear
- Debugging persistent failures
- Need to verify assumptions

**Goal**: Efficient decision-making with precise investigation when needed.
