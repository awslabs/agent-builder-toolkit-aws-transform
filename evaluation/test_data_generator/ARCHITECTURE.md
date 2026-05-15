# Architecture Overview

## System Design

```
┌─────────────────────────────────────────────────────────────────────┐
│                    INTELLIGENT TEST GENERATOR                       │
└─────────────────────────────────────────────────────────────────────┘

INPUT                          PROCESSING                       OUTPUT
─────                          ──────────                       ──────

┌──────────────┐              ┌────────────────────┐         ┌─────────────┐
│   Teacher    │              │  Domain Analyzer   │         │  Generated  │
│   Samples    │─────────────>│                    │         │   Tests     │
│  (optional)  │              │  • Extract patterns│         │ (10-50 tests)│
└──────────────┘              │  • Understand      │         └─────────────┘
                              │    capabilities    │
┌──────────────┐              │  • Identify personas│        ┌─────────────┐
│  POWER.md    │─────────────>│  • Analyze         │        │   Domain    │
│  (optional)  │              │    assertions      │        │  Analysis   │
└──────────────┘              └────────┬───────────┘        └─────────────┘
                                       │
                                       │ Domain Understanding
                                       │
                                       ▼
                              ┌────────────────────┐
                              │ Intelligent Gen.   │
                              │                    │
                              │  • Build prompts   │
                              │  • Generate batches│
                              │  • Ensure diversity│
                              │  • Validate output │
                              └────────┬───────────┘
                                       │
                                       ▼
                              ┌────────────────────┐
                              │   AWS Bedrock      │
                              │  (Claude Models)   │
                              └────────────────────┘
```

## Component Architecture

```
test_data_generator/
│
├── domain_analyzer.py ─────────────────┐
│   ├─ DomainAnalyzer                   │
│   │  ├─ analyze_test_samples()        │ Phase 1: Understanding
│   │  ├─ _extract_structural_patterns()│
│   │  ├─ _extract_domain_understanding()
│   │  └─ _call_bedrock()               │
│                                        │
├── intelligent_generator.py ───────────┤
│   ├─ IntelligentTestGenerator         │
│   │  ├─ generate_test_cases()         │ Phase 2: Generation
│   │  ├─ _generate_batch()             │
│   │  ├─ _build_generation_prompt()    │
│   │  └─ _validate_and_fix_tests()     │
│                                        │
└── cli.py ─────────────────────────────┤
    ├─ main()                            │ Phase 3: Interface
    ├─ load_teacher_samples()            │
    └─ load_power_instructions()         │
```

## Data Flow

### Phase 1: Domain Analysis

```
Teacher Samples ───> Structural Analysis ───> Patterns
                              │
                              ▼
                     LLM Analysis (Bedrock)
                              │
                              ▼
                    Domain Understanding
                    ┌─────────────────────┐
                    │ • Capabilities      │
                    │ • Personas          │
                    │ • Success criteria  │
                    │ • Complexity factors│
                    │ • Edge cases        │
                    └─────────────────────┘
```

### Phase 2: Intelligent Generation

```
Domain Understanding ───> Prompt Builder ───> Bedrock API
       +                       │                   │
Teacher Samples                │                   │
       +                       ▼                   ▼
Diversity Factor        Batch Generation      LLM Response
       │                       │                   │
       │                       │<──────────────────┘
       │                       │
       └──────────────────> Validator
                               │
                               ▼
                       Valid Test Cases
```

### Phase 3: Output & Integration

```
Generated Tests ───> Individual Files ───> test_data_expanded/
      │                                           │
      └────────────> All Tests File              │
                           │                      │
                           └──────────────────────┤
                                                  │
Domain Analysis ───> Analysis File               │
                           │                      │
                           └──────────────────────┘
                                                  │
                                                  ▼
                                    Evolution Config Update
                                                  │
                                                  ▼
                                    Run Evolution Workflow
```

## Key Design Decisions

### 1. Two-Phase Approach (Analysis → Generation)

**Why?**
- Separate understanding from generation
- Reusable domain analysis
- Better quality control

**Tradeoffs:**
- Two LLM calls instead of one
- Slightly slower, but much better quality

### 2. Batch Generation

**Why?**
- Ensures diversity across batches
- Better progress tracking
- Fault tolerance (partial failures OK)

**Tradeoffs:**
- More API calls
- More complex code
- Better results and reliability

### 3. Validation & Auto-Fix

**Why?**
- LLM output can be imperfect
- Ensures structural consistency
- Reduces manual cleanup

**Tradeoffs:**
- May mask generation issues
- Extra processing
- Much better usability

### 4. Diversity Control

**Why?**
- Different use cases need different diversity
- Allows tuning based on needs
- Explicit control over exploration/exploitation

**Tradeoffs:**
- Extra parameter to tune
- Complexity in prompt engineering
- Flexibility worth the complexity

## Prompt Engineering Strategy

### Domain Analysis Prompt
```
Purpose: Deep understanding of domain
Structure:
  1. Context (teacher samples + POWER.md)
  2. Analysis requirements (capabilities, personas, etc.)
  3. Output format (structured JSON)
  
Temperature: 0.3 (low - want consistent analysis)
Max tokens: 8000
```

### Generation Prompt
```
Purpose: Create diverse, valid test cases
Structure:
  1. Domain understanding (from analysis)
  2. Teacher examples (2-3 samples)
  3. Generation requirements (count, complexity, diversity)
  4. Output format (test case array)
  
Temperature: 0.8 (higher - want creativity)
Max tokens: 16000
```

### Batch-Specific Focus
```
Purpose: Ensure diversity across batches
Strategy:
  - Batch 0: Core capabilities
  - Batch 1: User personas
  - Batch 2: Edge cases
  - Repeat with different aspects
  
Result: Natural diversity without explicit deduplication
```

## Validation Pipeline

```
Generated Test
      │
      ▼
┌─────────────┐
│ Has ID?     │ ─No─> Generate ID
└──────┬──────┘
       │ Yes
       ▼
┌─────────────┐
│ Has name?   │ ─No─> Generate name
└──────┬──────┘
       │ Yes
       ▼
┌─────────────┐
│ Valid       │ ─No─> Set default
│ complexity? │
└──────┬──────┘
       │ Yes
       ▼
┌─────────────┐
│ Has         │ ─No─> Skip test
│ assertions? │
└──────┬──────┘
       │ Yes
       ▼
┌─────────────┐
│ Validate    │ ─Invalid─> Remove invalid
│ assertions  │
└──────┬──────┘
       │ Valid
       ▼
┌─────────────┐
│ Add to      │
│ output set  │
└─────────────┘
```

## Integration Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   EVOLUTION WORKFLOW                         │
└─────────────────────────────────────────────────────────────┘

    ┌──────────────┐
    │  Test Data   │
    │  Generator   │ (NEW)
    └──────┬───────┘
           │ Expands test set
           ▼
    ┌──────────────┐
    │  Test Data   │
    │   Loader     │ (EXISTING)
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │  Evolution   │
    │ Orchestrator │ (EXISTING)
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │   Adapter    │
    │    (Agent)   │ (EXISTING)
    └──────────────┘
```

## Error Handling Strategy

```
Level 1: Graceful Degradation
  - Missing POWER.md? Continue without it
  - Some tests invalid? Use valid ones
  - Batch failed? Continue with others

Level 2: Validation & Auto-Fix
  - Missing fields? Add defaults
  - Invalid assertions? Remove them
  - Wrong structure? Fix if possible

Level 3: Clear Errors
  - No teacher samples? Error & exit
  - Bedrock unavailable? Error & exit
  - All tests invalid? Error & exit
```

## Scalability Considerations

### Current Scale
- Teacher samples: 1-10
- Generated tests: 10-50
- Time: 3-5 minutes
- Cost: $1-2

### Future Scale
- Teacher samples: 10-100
- Generated tests: 100-500
- Time: 10-30 minutes
- Cost: $10-20

### Optimization Opportunities
1. Cache domain analysis
2. Parallel batch generation
3. Incremental generation
4. Template extraction
5. Local model support

## Testing Strategy

### Unit Tests
```python
test_basic.py
  ├─ Import validation
  ├─ Structural analysis (no API)
  ├─ Complexity analysis (no API)
  └─ Assertion analysis (no API)
```

### Integration Tests
```bash
example.py
  ├─ Basic generation
  ├─ With POWER.md
  ├─ Domain analysis
  ├─ High diversity
  └─ Specific complexity
```

### End-to-End Tests
```bash
1. Generate tests
2. Update config
3. Run evolution
4. Validate metrics
```

## Configuration Management

```
CLI Arguments ───> Generator Config
                         │
                         ▼
                   ┌──────────┐
                   │ Region   │
                   │ Model ID │
                   │ Temp     │
                   └──────────┘
                         │
                         ▼
                   Bedrock Client
```

## Dependencies

```
External:
  ├─ boto3 (AWS SDK)
  ├─ json (stdlib)
  ├─ logging (stdlib)
  ├─ pathlib (stdlib)
  └─ argparse (stdlib)

Internal:
  ├─ domain_analyzer
  └─ intelligent_generator

Evolution Framework:
  ├─ TestCase (core.test_case)
  └─ TestCaseLoader (core.test_case)
```

## Summary

**Architecture Principles:**
1. **Separation of Concerns**: Analysis, generation, validation
2. **Fail-Safe**: Graceful degradation and auto-fixing
3. **Extensibility**: Easy to add new strategies
4. **Integration**: Minimal changes to existing workflow

**Key Strengths:**
- Modular design
- Clear data flow
- Robust error handling
- Well-documented
- Easy to extend

**Design Tradeoffs:**
- Complexity vs. Quality → Chose quality
- Speed vs. Diversity → Chose diversity
- Automation vs. Control → Balanced both
