"""Intelligent test data generator that understands the task and generates diverse samples."""

import json
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
import boto3

from .domain_analyzer import DomainAnalyzer

logger = logging.getLogger(__name__)


class IntelligentTestGenerator:
    """Generates test cases based on domain understanding from teacher samples."""

    def __init__(
        self,
        region_name: str,
        model_id: str,
        temperature: float = 0.8
    ):
        """Initialize intelligent test generator.

        Args:
            region_name: AWS region for Bedrock
            model_id: Model ID for generation
            temperature: Temperature for creative generation (0-1)
        """
        self.region_name = region_name
        self.model_id = model_id
        self.temperature = temperature

        # Configure Bedrock client with longer timeout
        from botocore.config import Config
        config = Config(
            read_timeout=300,  # 5 minutes
            connect_timeout=60,
            retries={'max_attempts': 3, 'mode': 'adaptive'}
        )
        self.bedrock = boto3.client('bedrock-runtime', region_name=region_name, config=config)
        self.analyzer = DomainAnalyzer(region_name, model_id)

    def generate_test_cases(
        self,
        teacher_samples: List[Dict[str, Any]],
        count: int,
        source_context: str,
        complexity: Optional[str] = None,
        diversity_factor: float = 0.8,
        output_dir: Optional[str] = None,
        deduplicate: bool = True,
        ensure_complex_tests: bool = True
    ) -> List[Dict[str, Any]]:
        """Generate diverse test cases based on source context and optional teacher samples.

        Args:
            teacher_samples: Teacher test samples to learn from (can be empty list)
            count: Number of test cases to generate
            source_context: Source context (POWER.md, code, etc.) - REQUIRED for domain understanding
            complexity: Optional complexity filter (simple/medium/complex)
            diversity_factor: How diverse to make tests (0=similar, 1=very diverse)
            output_dir: Optional directory to save generated tests
            deduplicate: Remove duplicate test names (default: True)
            ensure_complex_tests: Ensure at least 20% complex tests (default: True)

        Returns:
            List of generated test cases
        """
        if not source_context:
            raise ValueError("source_context is required for domain understanding")

        mode = "teacher samples + source context" if teacher_samples else "source context only"
        logger.info(f"Generating {count} test cases from {mode}...")
        if teacher_samples:
            logger.info(f"  Using {len(teacher_samples)} teacher samples")
        logger.info(f"  Using source context ({len(source_context)} chars)")

        # Step 1: Analyze domain
        logger.info("Step 1: Analyzing domain from teacher samples...")
        domain_analysis = self.analyzer.analyze_test_samples(
            teacher_samples,
            source_context
        )

        # Save analysis if output directory provided
        if output_dir:
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            analysis_path = Path(output_dir) / "domain_analysis.json"
            self.analyzer.save_analysis(domain_analysis, str(analysis_path))

        # Step 2: Calculate target complexity distribution
        target_complex = 0
        if ensure_complex_tests and not complexity:
            target_complex = max(int(count * 0.2), 1)  # At least 20% complex
            logger.info(f"Target: {target_complex} complex tests ({target_complex/count*100:.0f}%)")

        # Step 3: Generate test cases in batches with diversity enforcement
        logger.info("Step 2: Generating test cases...")
        generated_tests = []
        seen_names = set()  # Track names for deduplication
        batch_size = min(5, count)
        num_batches = (count + batch_size - 1) // batch_size

        # Increase batch size to account for deduplication
        if deduplicate:
            num_batches = int(num_batches * 1.5)  # Generate 50% more for filtering

        for batch_idx in range(num_batches):
            if len(generated_tests) >= count:
                break

            batch_count = min(batch_size, count - len(generated_tests) + 3)  # +3 buffer
            logger.info(f"Generating batch {batch_idx + 1}/{num_batches} ({batch_count} tests)...")

            # Adjust complexity for this batch
            batch_complexity = complexity
            if ensure_complex_tests and not complexity:
                # Ensure we generate enough complex tests
                complex_so_far = sum(1 for t in generated_tests if t.get('complexity') == 'complex')
                if complex_so_far < target_complex and batch_idx >= num_batches // 2:
                    batch_complexity = 'complex'
                    logger.info(f"  Focusing on complex tests (have {complex_so_far}/{target_complex})")

            batch_tests = self._generate_batch(
                teacher_samples=teacher_samples,
                domain_analysis=domain_analysis,
                count=batch_count,
                complexity=batch_complexity,
                diversity_factor=diversity_factor,
                batch_idx=batch_idx,
                existing_names=seen_names  # Pass for deduplication
            )

            # Add unique tests only
            for test in batch_tests:
                test_name = test.get('name', '')
                if not deduplicate or test_name not in seen_names:
                    generated_tests.append(test)
                    seen_names.add(test_name)
                    if len(generated_tests) >= count:
                        break

        # Trim to exact count
        generated_tests = generated_tests[:count]

        # Step 4: Validate and post-process
        logger.info("Step 3: Validating generated tests...")
        validated_tests = self._validate_and_fix_tests(generated_tests, teacher_samples)

        # Step 5: Final quality checks
        logger.info("Step 4: Final quality checks...")
        validated_tests = self._final_quality_pass(validated_tests, count, ensure_complex_tests)

        # Reassign IDs after final quality pass to ensure sequential numbering
        for i, test in enumerate(validated_tests):
            test["id"] = f"generated_{i+1:03d}"

        # Save tests if output directory provided
        if output_dir:
            for i, test in enumerate(validated_tests):
                test_file = Path(output_dir) / f"generated_test_{i+1:03d}.json"
                with open(test_file, 'w') as f:
                    json.dump([test], f, indent=2)
                logger.debug(f"Saved test to {test_file}")

            # Also save all tests in one file
            all_tests_file = Path(output_dir) / "all_generated_tests.json"
            with open(all_tests_file, 'w') as f:
                json.dump(validated_tests, f, indent=2)
            logger.info(f"Saved all tests to {all_tests_file}")

        logger.info(f"Successfully generated {len(validated_tests)} test cases")
        return validated_tests

    def _generate_batch(
        self,
        teacher_samples: List[Dict[str, Any]],
        domain_analysis: Dict[str, Any],
        count: int,
        complexity: Optional[str],
        diversity_factor: float,
        batch_idx: int,
        existing_names: Optional[set] = None
    ) -> List[Dict[str, Any]]:
        """Generate a batch of test cases."""
        prompt = self._build_generation_prompt(
            teacher_samples=teacher_samples,
            domain_analysis=domain_analysis,
            count=count,
            complexity=complexity,
            diversity_factor=diversity_factor,
            batch_idx=batch_idx,
            existing_names=existing_names
        )

        # Retry logic for timeouts
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                response = self._call_bedrock(prompt)
                tests = self._parse_generation_response(response)
                return tests
            except Exception as e:
                if attempt < max_retries and ('timeout' in str(e).lower() or 'timed out' in str(e).lower()):
                    logger.warning(f"Batch generation attempt {attempt + 1} timed out, retrying...")
                    continue
                else:
                    logger.exception(f"Batch generation failed after {attempt + 1} attempts: {e}")
                    return []

        logger.error("Batch generation exited retry loop without returning a result; returning empty list.")
        return []

    def _build_generation_prompt(
        self,
        teacher_samples: List[Dict[str, Any]],
        domain_analysis: Dict[str, Any],
        count: int,
        complexity: Optional[str],
        diversity_factor: float,
        batch_idx: int,
        existing_names: Optional[set] = None
    ) -> str:
        """Build prompt for test case generation."""
        has_samples = bool(teacher_samples)

        prompt = f"""You are an expert test case generator for AI agent evaluation. Your task is to generate {count} diverse, realistic test cases.

# Domain Context

## Domain Understanding
{json.dumps(domain_analysis.get("domain_understanding", {}), indent=2)}

## Structural Patterns
{json.dumps(domain_analysis.get("structural_patterns", {}), indent=2)}

## Complexity Distribution
{json.dumps(domain_analysis.get("complexity_distribution", {}), indent=2)}

"""

        if has_samples:
            prompt += """# Teacher Test Samples (Learn from these)

"""
            # Show 2-3 representative teacher samples
            num_examples = min(3, len(teacher_samples))
            for i in range(num_examples):
                sample = teacher_samples[i % len(teacher_samples)]
                prompt += f"""## Teacher Sample {i+1}
```json
{json.dumps(sample, indent=2)}
```

"""
            prompt += f"""# Generation Requirements

Generate **{count} NEW, DIVERSE test cases** that:

1. **Follow the same structure** as teacher samples (same fields, assertion patterns)
2. **Test different scenarios** - do NOT simply copy teacher samples with minor changes
3. **Maintain quality** - assertions should be specific and validate real capabilities
4. **Match complexity**: {complexity if complexity else "Mix of simple (30%), medium (50%), complex (20%)"}
5. **Diversity level**: {diversity_factor:.1f} (0=similar to teachers, 1=very different scenarios)"""
        else:
            prompt += f"""# Test Structure Requirements

Since no teacher samples are available, generate tests with this structure:
- **id**: Unique identifier (generated_001, generated_002, etc.)
- **name**: Descriptive name
- **user_message** or **prompt**: User's initial message/request
- **description**: What this test validates
- **complexity**: simple, medium, or complex
- **tags**: Array of relevant tags
- **max_turns**: Expected conversation length (default: 10)
- **timeout_seconds**: Timeout for the test (default: 300)
- **simulated_human_guidance**: Detailed instructions for simulated user behavior
- **metadata**: Domain-specific metadata (domain, scenario_type, etc.)
- **assertions**: Array of assertion objects with:
  - name: assertion identifier
  - type: llm_judge, tool_called, transcript_not_contains, etc.
  - description: What is being validated
  - check: The validation criteria or tool name

# Generation Requirements

Generate **{count} NEW, DIVERSE test cases** that:

1. **Test different capabilities** identified in the domain understanding above
2. **Cover various scenarios** - include both common and edge cases
3. **Maintain quality** - assertions should be specific and validate real capabilities
4. **Match complexity**: {complexity if complexity else "Mix of simple (30%), medium (50%), complex (20%)"}
5. **Diversity level**: {diversity_factor:.1f} (0=similar scenarios, 1=very different scenarios)

## Diversity Guidelines (factor: {diversity_factor:.1f})
"""

        if diversity_factor >= 0.7:
            prompt += """
- Explore edge cases and unusual scenarios
- Test failure modes and error handling
- Include different user personas and skill levels
- Vary interaction patterns significantly
- Test boundary conditions
"""
        elif diversity_factor >= 0.4:
            prompt += """
- Cover different aspects of core capabilities
- Include variations in user requests
- Test both happy paths and some error cases
- Moderate variation in complexity and scope
"""
        else:
            prompt += """
- Stay close to teacher sample patterns
- Focus on core capability variations
- Mostly happy path scenarios
- Similar complexity and scope
"""

        # Add deduplication instructions
        if existing_names:
            prompt += f"""
## CRITICAL: Avoid Duplicates
The following test names have already been generated - DO NOT create tests with these names:
{chr(10).join(f'  - "{name}"' for name in sorted(existing_names)[:20])}
{'  ... and more' if len(existing_names) > 20 else ''}

Create COMPLETELY NEW scenarios with UNIQUE names.
"""

        # Add batch-specific guidance for diversity across batches
        if batch_idx > 0:
            prompt += f"""
## Batch #{batch_idx + 1} Focus
This is batch {batch_idx + 1}. Generate scenarios that are distinct from earlier batches.
Focus on: {self._get_batch_focus(batch_idx, domain_analysis)}
"""

        prompt += """
# Output Format

Return a JSON array of test cases. Each test must include:
- **id**: Unique identifier (generated_001, generated_002, etc.)
- **name**: Descriptive name
- **user_message** or **prompt**: User's initial message
- **description**: What this test validates
- **complexity**: simple, medium, or complex
- **tags**: Array of relevant tags
- **max_turns**: Expected conversation length
- **timeout_seconds**: Timeout for the test
- **simulated_human_guidance**: Detailed instructions for simulated user behavior
- **metadata**: Domain-specific metadata (domain, source_platform, target_platform, scenario_type, etc.)
- **assertions**: Array of assertion objects with:
  - name: assertion identifier
  - type: llm_judge, tool_called, transcript_not_contains, etc.
  - description: What is being validated
  - check: The validation criteria or tool name

**CRITICAL**: Generate COMPLETE, VALID test cases. Do not use placeholders like "..." or "etc."

```json
[
  {
    "id": "generated_001",
    "name": "...",
    "user_message": "...",
    "description": "...",
    "complexity": "...",
    "tags": [...],
    "max_turns": ...,
    "timeout_seconds": ...,
    "simulated_human_guidance": "...",
    "metadata": {...},
    "assertions": [...]
  }
]
```

Generate exactly {count} complete test cases now:"""

        return prompt

    def _get_batch_focus(self, batch_idx: int, domain_analysis: Dict[str, Any]) -> str:
        """Get focus area for a specific batch to ensure diversity."""
        domain_understanding = domain_analysis.get("domain_understanding", {})

        # Extract focus areas from domain analysis
        capabilities = domain_understanding.get("core_capabilities", [])
        personas = domain_understanding.get("user_personas", [])
        edge_cases = domain_understanding.get("edge_cases_to_test", [])

        focus_areas = []

        # Rotate through different aspects
        if batch_idx % 3 == 0 and capabilities:
            # Focus on specific capabilities
            cap_idx = (batch_idx // 3) % len(capabilities)
            cap = capabilities[cap_idx]
            focus_areas.append(f"capability '{cap.get('name', 'unknown')}'")

        if batch_idx % 3 == 1 and personas:
            # Focus on specific persona
            persona_idx = (batch_idx // 3) % len(personas)
            persona = personas[persona_idx]
            focus_areas.append(f"user persona '{persona.get('name', 'unknown')}'")

        if batch_idx % 3 == 2 and edge_cases:
            # Focus on edge cases
            edge_idx = (batch_idx // 3) % len(edge_cases)
            edge = edge_cases[edge_idx]
            focus_areas.append(f"edge case: {edge.get('scenario', 'unknown')}")

        if not focus_areas:
            focus_areas.append("alternative scenarios and variations")

        return ", ".join(focus_areas)

    def _call_bedrock(self, prompt: str) -> str:
        """Call Bedrock API."""
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 16000,  # Large for multiple test cases
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": self.temperature
        })

        response = self.bedrock.invoke_model(
            modelId=self.model_id,
            body=body
        )

        response_body = json.loads(response['body'].read())
        return response_body['content'][0]['text']

    def _parse_generation_response(self, response: str) -> List[Dict[str, Any]]:
        """Parse LLM generation response."""
        import re

        # Find JSON array in response
        json_match = re.search(r'\[[\s\S]*\]', response)
        if not json_match:
            logger.error("No JSON array found in generation response")
            return []

        try:
            tests = json.loads(json_match.group(0))
            if not isinstance(tests, list):
                logger.error("Response is not a list")
                return []
            return tests
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse generation JSON: {e}")
            return []

    def _validate_and_fix_tests(
        self,
        generated_tests: List[Dict[str, Any]],
        teacher_samples: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Validate and fix generated test cases."""
        validated = []

        # Get required fields from teacher samples or use defaults
        if teacher_samples:
            required_fields = set(teacher_samples[0].keys())
        else:
            # Default required fields when no teacher samples
            required_fields = {
                "id", "name", "description", "complexity", "tags",
                "max_turns", "timeout_seconds", "simulated_human_guidance",
                "metadata", "assertions"
            }

        for i, test in enumerate(generated_tests):
            try:
                # Ensure required fields (ID will be assigned after final quality pass)
                missing_fields = required_fields - set(test.keys())
                if missing_fields:
                    logger.warning(f"Test {i} missing required fields: {sorted(missing_fields)}")
                    for field in missing_fields:
                        if field in {"tags", "assertions"}:
                            test[field] = []
                        elif field in {"metadata"}:
                            test[field] = {}
                        elif field in {"max_turns", "timeout_seconds"}:
                            test[field] = 0
                        elif field in {"complexity"}:
                            test[field] = "medium"
                        else:
                            test[field] = ""
                if not test.get("name"):
                    test["name"] = f"Generated Test {i+1}"

                if not test.get("description"):
                    test["description"] = test.get("name", "Generated test case")

                # Ensure complexity
                if not test.get("complexity") or test.get("complexity") not in ["simple", "medium", "complex"]:
                    test["complexity"] = "medium"

                # Ensure metadata
                if "metadata" not in test:
                    test["metadata"] = {}

                # Ensure assertions exist
                if "assertions" not in test or not test["assertions"]:
                    logger.warning(f"Test {test['id']} has no assertions, skipping")
                    continue

                # Ensure user_message or prompt
                if not test.get("user_message") and not test.get("prompt"):
                    test["user_message"] = f"User message for {test['name']}"

                # Ensure simulated_human_guidance
                if not test.get("simulated_human_guidance"):
                    test["simulated_human_guidance"] = f"Simulated user behavior for {test['name']}"

                # Ensure reasonable defaults
                if not test.get("max_turns"):
                    test["max_turns"] = 10

                if not test.get("timeout_seconds"):
                    test["timeout_seconds"] = 300

                if not test.get("tags"):
                    test["tags"] = ["generated"]

                # Validate assertions
                valid_assertions = []
                for assertion in test.get("assertions", []):
                    if assertion.get("name") and assertion.get("type") and assertion.get("check"):
                        valid_assertions.append(assertion)
                    else:
                        logger.warning(f"Invalid assertion in test {test['id']}: {assertion}")

                test["assertions"] = valid_assertions

                if valid_assertions:
                    validated.append(test)
                else:
                    logger.warning(f"Test {test['id']} has no valid assertions, skipping")

            except Exception as e:
                logger.exception(f"Failed to validate test {i}: {e}")

        logger.info(f"Validated {len(validated)}/{len(generated_tests)} tests")
        return validated

    def generate_from_analysis(
        self,
        domain_analysis_path: str,
        teacher_samples: List[Dict[str, Any]],
        count: int,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Generate test cases from pre-computed domain analysis.

        Args:
            domain_analysis_path: Path to domain analysis JSON
            teacher_samples: Teacher samples (for structure reference)
            count: Number of tests to generate
            **kwargs: Additional generation parameters

        Returns:
            Generated test cases
        """
        logger.info(f"Loading domain analysis from {domain_analysis_path}")
        domain_analysis = self.analyzer.load_analysis(domain_analysis_path)

        generated_tests = []
        batch_size = min(5, count)
        num_batches = (count + batch_size - 1) // batch_size

        for batch_idx in range(num_batches):
            batch_count = min(batch_size, count - len(generated_tests))
            batch_tests = self._generate_batch(
                teacher_samples=teacher_samples,
                domain_analysis=domain_analysis,
                count=batch_count,
                complexity=kwargs.get("complexity"),
                diversity_factor=kwargs.get("diversity_factor", 0.8),
                batch_idx=batch_idx
            )
            generated_tests.extend(batch_tests)

        validated_tests = self._validate_and_fix_tests(generated_tests, teacher_samples)
        return validated_tests

    def _final_quality_pass(
        self,
        tests: List[Dict[str, Any]],
        target_count: int,
        ensure_complex: bool
    ) -> List[Dict[str, Any]]:
        """Final quality check: deduplication and complexity balance.

        Args:
            tests: Validated test cases
            target_count: Target number of tests
            ensure_complex: Whether to ensure complex test quota

        Returns:
            Quality-checked tests
        """
        # Deduplication by name
        seen_names = {}
        deduplicated = []

        for test in tests:
            name = test.get('name', '')
            if name not in seen_names:
                deduplicated.append(test)
                seen_names[name] = test
            else:
                # Keep the one with more assertions
                existing = seen_names[name]
                if len(test.get('assertions', [])) > len(existing.get('assertions', [])):
                    # Replace with better version
                    deduplicated.remove(existing)
                    deduplicated.append(test)
                    seen_names[name] = test

        if len(deduplicated) < len(tests):
            logger.info(f"Removed {len(tests) - len(deduplicated)} duplicate tests")

        # Check complexity distribution
        complexity_counts = {}
        for test in deduplicated:
            comp = test.get('complexity', 'medium')
            complexity_counts[comp] = complexity_counts.get(comp, 0) + 1

        logger.info(f"Complexity distribution: {complexity_counts}")

        # Warn if complex tests are missing
        if ensure_complex and len(deduplicated) >= 10:
            complex_count = complexity_counts.get('complex', 0)
            target_complex = max(int(len(deduplicated) * 0.2), 1)
            if complex_count < target_complex:
                logger.warning(
                    f"Only {complex_count}/{target_complex} complex tests. "
                    f"Consider regenerating with --ensure-complex-tests or generating more batches."
                )

        return deduplicated[:target_count]
