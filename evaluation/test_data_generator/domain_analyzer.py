"""Domain analyzer that extracts patterns and requirements from teacher test samples."""

import json
import logging
import re
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from collections import Counter
import boto3

logger = logging.getLogger(__name__)


class DomainAnalyzer:
    """Analyzes teacher test samples to understand the domain and requirements."""

    MAX_INSTRUCTION_CHARS = 200000

    def __init__(
        self,
        region_name: str,
        model_id: str,
        use_two_pass_analysis: bool = False
    ):
        """Initialize domain analyzer.

        Args:
            region_name: AWS region for Bedrock
            model_id: Model ID for analysis
            use_two_pass_analysis: If True, use two-pass analysis for large instructions
        """
        self.region_name = region_name
        self.model_id = model_id
        self.use_two_pass_analysis = use_two_pass_analysis

        # Configure Bedrock client with longer timeout
        from botocore.config import Config
        config = Config(
            read_timeout=300,  # 5 minutes
            connect_timeout=60,
            retries={'max_attempts': 3, 'mode': 'adaptive'}
        )
        self.bedrock = boto3.client('bedrock-runtime', region_name=region_name, config=config)

    def analyze_test_samples(
        self,
        test_samples: List[Dict[str, Any]],
        source_context: str
    ) -> Dict[str, Any]:
        """Analyze source context and optional teacher test samples to extract domain understanding.

        Args:
            test_samples: List of teacher test samples (can be empty list)
            source_context: Source code/docs content - REQUIRED for domain understanding

        Returns:
            Analysis results with domain patterns, requirements, and characteristics
        """
        if not source_context:
            raise ValueError("source_context is required for domain understanding")

        mode = "teacher samples + source context" if test_samples else "source context only"
        logger.info(f"Analyzing domain from {mode}...")
        if test_samples:
            logger.info(f"  {len(test_samples)} teacher samples available")
        logger.info(f"  Using source context ({len(source_context)} chars)")

        # Extract structural patterns (only if samples exist)
        structural_patterns = self._extract_structural_patterns(test_samples) if test_samples else self._get_default_structure()

        # Choose analysis strategy based on instruction size and configuration
        if self.use_two_pass_analysis and source_context and len(source_context) > 80000:
            logger.info("Using two-pass analysis for comprehensive instruction understanding...")
            domain_understanding = self._two_pass_analysis(test_samples, source_context)
        else:
            # Standard analysis with smart chunking
            domain_understanding = self._extract_domain_understanding(
                test_samples,
                source_context
            )

        # Combine results
        analysis = {
            "structural_patterns": structural_patterns,
            "domain_understanding": domain_understanding,
            "sample_count": len(test_samples),
            "complexity_distribution": self._analyze_complexity(test_samples),
            "assertion_patterns": self._analyze_assertions(test_samples),
        }

        logger.info("Domain analysis complete")
        return analysis

    def _extract_structural_patterns(
        self,
        test_samples: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Extract structural patterns from test samples."""
        patterns = {
            "fields": {},
            "metadata_keys": set(),
            "assertion_types": Counter(),
            "tags": Counter(),
            "complexity_levels": Counter(),
        }

        for sample in test_samples:
            # Track field presence
            for field in sample.keys():
                if field not in patterns["fields"]:
                    patterns["fields"][field] = {
                        "count": 0,
                        "types": set(),
                        "examples": []
                    }
                patterns["fields"][field]["count"] += 1
                patterns["fields"][field]["types"].add(type(sample[field]).__name__)
                if len(patterns["fields"][field]["examples"]) < 3:
                    patterns["fields"][field]["examples"].append(sample[field])

            # Track metadata keys
            if "metadata" in sample:
                patterns["metadata_keys"].update(sample["metadata"].keys())

            # Track assertion types
            if "assertions" in sample:
                for assertion in sample["assertions"]:
                    assertion_type = assertion.get("type", "unknown")
                    patterns["assertion_types"][assertion_type] += 1

            # Track tags
            if "tags" in sample:
                patterns["tags"].update(sample["tags"])

            # Track complexity
            if "complexity" in sample:
                patterns["complexity_levels"][sample["complexity"]] += 1

        # Convert sets to lists for JSON serialization
        patterns["metadata_keys"] = list(patterns["metadata_keys"])
        for field_data in patterns["fields"].values():
            field_data["types"] = list(field_data["types"])
        patterns["assertion_types"] = dict(patterns["assertion_types"])
        patterns["tags"] = dict(patterns["tags"])
        patterns["complexity_levels"] = dict(patterns["complexity_levels"])

        return patterns

    def _get_default_structure(self) -> Dict[str, Any]:
        """Get default test structure when no teacher samples are available."""
        return {
            "fields": {
                "id": {"count": 0, "types": ["str"], "examples": []},
                "name": {"count": 0, "types": ["str"], "examples": []},
                "user_message": {"count": 0, "types": ["str"], "examples": []},
                "description": {"count": 0, "types": ["str"], "examples": []},
                "complexity": {"count": 0, "types": ["str"], "examples": ["simple", "medium", "complex"]},
                "tags": {"count": 0, "types": ["list"], "examples": []},
                "max_turns": {"count": 0, "types": ["int"], "examples": [10]},
                "timeout_seconds": {"count": 0, "types": ["int"], "examples": [300]},
                "simulated_human_guidance": {"count": 0, "types": ["str"], "examples": []},
                "metadata": {"count": 0, "types": ["dict"], "examples": []},
                "assertions": {"count": 0, "types": ["list"], "examples": []}
            },
            "metadata_keys": [],
            "assertion_types": {"llm_judge": 0, "tool_called": 0},
            "tags": {},
            "complexity_levels": {"simple": 0, "medium": 0, "complex": 0}
        }

    def _extract_domain_understanding(
        self,
        test_samples: List[Dict[str, Any]],
        source_context: Optional[str]
    ) -> Dict[str, Any]:
        """Use LLM to extract deep domain understanding."""
        logger.info("Extracting domain understanding via LLM...")

        # Build prompt with smart chunking
        prompt = self._build_analysis_prompt(test_samples, source_context)

        # Call LLM
        try:
            response = self._call_bedrock(prompt)
            understanding = self._parse_analysis_response(response)
            return understanding
        except Exception as e:
            logger.exception(f"LLM analysis failed: {e}")
            return {"error": str(e)}

    def _two_pass_analysis(
        self,
        test_samples: List[Dict[str, Any]],
        source_context: str
    ) -> Dict[str, Any]:
        """Two-pass analysis for comprehensive understanding of large instructions.

        Pass 1: Analyze instructions alone to extract key capabilities and rules
        Pass 2: Analyze test samples with condensed instruction summary
        """
        logger.info("Pass 1: Analyzing power instructions...")

        # Pass 1: Extract instruction summary
        instruction_summary = self._analyze_instructions(source_context)

        logger.info("Pass 2: Analyzing test samples with instruction context...")

        # Pass 2: Analyze test samples with condensed context
        domain_understanding = self._extract_domain_understanding(
            test_samples,
            instruction_summary.get("condensed_instructions", source_context[:80000])
        )

        # Merge instruction insights with domain understanding
        domain_understanding["instruction_analysis"] = instruction_summary

        return domain_understanding

    def _analyze_instructions(self, source_context: str) -> Dict[str, Any]:
        """Analyze power instructions alone to extract key information.

        Returns:
            Dictionary with:
                - core_capabilities: List of agent capabilities
                - key_rules: Important behavioral rules
                - success_criteria: Quality expectations
                - condensed_instructions: Summarized version for downstream use
        """
        prompt = f"""Analyze the following agent instructions and extract key information.

# Agent Instructions
```
{source_context}
```

# Task
Extract and summarize:
1. **Core Capabilities**: What can this agent do?
2. **Key Rules**: Critical behavioral constraints and guidelines
3. **Success Criteria**: Quality expectations and requirements
4. **Edge Cases**: Known failure modes or special scenarios
5. **Condensed Summary**: A comprehensive but condensed version (max 20K chars) preserving all critical information

Provide your analysis in JSON format:

```json
{{
  "core_capabilities": [
    {{"name": "capability1", "description": "what it does", "priority": "high|medium|low"}}
  ],
  "key_rules": [
    {{"rule": "rule description", "category": "category", "rationale": "why this matters"}}
  ],
  "success_criteria": {{
    "must_have": ["criterion1"],
    "should_have": ["criterion2"],
    "quality_signals": ["signal1"]
  }},
  "edge_cases": [
    {{"scenario": "edge case", "handling": "how to handle"}}
  ],
  "condensed_instructions": "Comprehensive summary preserving all critical information..."
}}
```"""

        try:
            response = self._call_bedrock(prompt, max_tokens=16000)
            analysis = self._parse_analysis_response(response)
            logger.info("Instruction analysis complete")
            return analysis
        except Exception as e:
            logger.exception(f"Instruction analysis failed: {e}")
            # Fallback to smart truncation
            return {
                "error": str(e),
                "condensed_instructions": self._smart_truncate(source_context, 80000)
            }

    def _smart_truncate(
        self,
        instructions: str,
        max_chars: int,
        preserve_structure: bool = True
    ) -> str:
        """Intelligently truncate instructions preserving key sections.

        Args:
            instructions: Full instruction text
            max_chars: Maximum character limit
            preserve_structure: If True, preserve markdown structure

        Returns:
            Truncated instructions with preserved key sections
        """
        if len(instructions) <= max_chars:
            return instructions

        logger.info(f"Smart truncating instructions from {len(instructions)} to {max_chars} chars...")

        if preserve_structure:
            # Extract key sections from markdown
            sections = self._extract_key_sections(instructions)

            # Prioritize sections
            prioritized = self._prioritize_sections(sections)

            # Build truncated content
            truncated = []
            current_length = 0

            for section_name, content in prioritized:
                section_text = f"\n# {section_name}\n{content}\n"
                if current_length + len(section_text) <= max_chars:
                    truncated.append(section_text)
                    current_length += len(section_text)
                else:
                    # Add partial section if space remains
                    remaining = max_chars - current_length
                    if remaining > 200:  # Only add if meaningful space left
                        truncated.append(section_text[:remaining] + "\n[... truncated ...]")
                    break

            result = "".join(truncated)
            logger.info(f"Preserved {len(truncated)} key sections in truncated instructions")
            return result
        else:
            # Simple truncation with warning
            return instructions[:max_chars] + "\n\n[... truncated ...]"

    def _extract_key_sections(self, instructions: str) -> Dict[str, str]:
        """Extract sections from markdown content.

        Returns:
            Dictionary mapping section names to their content
        """
        sections = {}
        current_section = "Introduction"
        current_content = []

        lines = instructions.split('\n')

        for line in lines:
            # Check for markdown headers
            header_match = re.match(r'^#+\s+(.+)$', line)
            if header_match:
                # Save previous section
                if current_content:
                    sections[current_section] = '\n'.join(current_content)

                # Start new section
                current_section = header_match.group(1)
                current_content = []
            else:
                current_content.append(line)

        # Save last section
        if current_content:
            sections[current_section] = '\n'.join(current_content)

        return sections

    def _prioritize_sections(
        self,
        sections: Dict[str, str]
    ) -> List[Tuple[str, str]]:
        """Prioritize sections by importance.

        Args:
            sections: Dictionary of section name to content

        Returns:
            List of (section_name, content) tuples in priority order
        """
        # Define priority keywords (higher score = higher priority)
        priority_keywords = {
            'capabilities': 100,
            'capability': 100,
            'features': 90,
            'rules': 85,
            'rule': 85,
            'requirements': 80,
            'behavior': 75,
            'guidelines': 70,
            'examples': 60,
            'example': 60,
            'edge cases': 55,
            'edge': 55,
            'scenarios': 50,
            'usage': 45,
            'overview': 40,
            'introduction': 30,
        }

        def calculate_priority(section_name: str) -> int:
            """Calculate priority score for a section.

            Uses the highest matching keyword score to avoid inflating
            scores for sections with multiple keywords.
            """
            name_lower = section_name.lower()
            max_score = 0
            for keyword, weight in priority_keywords.items():
                if keyword in name_lower:
                    max_score = max(max_score, weight)
            return max_score

        # Sort sections by priority
        prioritized = sorted(
            sections.items(),
            key=lambda x: calculate_priority(x[0]),
            reverse=True
        )

        return prioritized

    def _build_analysis_prompt(
        self,
        test_samples: List[Dict[str, Any]],
        source_context: str
    ) -> str:
        """Build prompt for domain analysis."""
        has_samples = bool(test_samples)

        if has_samples:
            prompt = """You are analyzing source code/documentation and test cases for an AI agent to understand the domain, requirements, and testing patterns.

# Your Task
Analyze the provided source context and teacher test samples to extract:
1. **Core capabilities** being tested
2. **Domain-specific patterns** and scenarios
3. **User personas** and interaction styles
4. **Success criteria** and quality expectations
5. **Edge cases** and complexity factors
6. **Assertion patterns** and what they validate

"""
        else:
            prompt = """You are analyzing source code and documentation for an AI agent to understand the domain and generate appropriate test cases.

# Your Task
From the provided source context, extract:
1. **Core capabilities** that should be tested
2. **Domain-specific patterns** and use cases
3. **User personas** who would interact with this system
4. **Success criteria** and quality expectations
5. **Edge cases** and complexity factors to test
6. **Appropriate assertion types** for validation

"""

        # source_context is always provided now
        # Smart truncation preserving structure
        if len(source_context) > self.MAX_INSTRUCTION_CHARS:
            logger.warning(
                f"Source context is very large ({len(source_context)} chars, ~{len(source_context)//4} tokens). "
                f"Using smart truncation to {self.MAX_INSTRUCTION_CHARS} chars (~{self.MAX_INSTRUCTION_CHARS//4} tokens) while preserving key sections. "
                f"For comprehensive analysis, consider using --use-two-pass-analysis flag."
            )
            truncated_instructions = self._smart_truncate(
                source_context,
                self.MAX_INSTRUCTION_CHARS,
                preserve_structure=True
            )
        else:
            truncated_instructions = source_context

        prompt += f"""# Source Context (Code, Documentation, Configuration)
```
{truncated_instructions}
```

"""

        if has_samples:
            prompt += f"""# Teacher Test Samples ({len(test_samples)} samples)

"""

            # Include representative samples
            for i, sample in enumerate(test_samples[:3]):  # Show max 3 full samples
                prompt += f"""## Sample {i+1}: {sample.get('name', 'Unnamed')}
```json
{json.dumps(sample, indent=2)}
```

"""
        else:
            prompt += """# Test Generation Mode
No teacher samples provided. You will need to infer appropriate test structures from the source context above.

"""

        prompt += """# Analysis Requirements

Provide a comprehensive analysis in JSON format:

```json
{
  "domain_description": "Brief description of what domain/system this tests",
  "core_capabilities": [
    {"name": "capability1", "description": "what it does", "criticality": "high|medium|low"}
  ],
  "user_personas": [
    {"name": "persona1", "characteristics": "description", "typical_scenarios": ["scenario1", "scenario2"]}
  ],
  "interaction_patterns": [
    {"pattern": "pattern_name", "description": "what the pattern is", "frequency": "common|occasional|rare"}
  ],
  "success_criteria": {
    "must_have": ["criterion1", "criterion2"],
    "should_have": ["criterion3"],
    "quality_signals": ["signal1", "signal2"]
  },
  "complexity_factors": {
    "simple": "what makes a test simple",
    "medium": "what makes a test medium complexity",
    "complex": "what makes a test complex"
  },
  "assertion_categories": [
    {"type": "assertion_type", "purpose": "what it validates", "examples": ["example1", "example2"]}
  ],
  "edge_cases_to_test": [
    {"scenario": "edge case", "why_important": "reason", "suggested_complexity": "simple|medium|complex"}
  ],
  "generation_guidance": {
    "key_dimensions": ["dimension1", "dimension2"],
    "diversity_strategies": ["strategy1", "strategy2"],
    "avoid_patterns": ["pattern1", "pattern2"]
  }
}
```

Be thorough and specific. This analysis will guide automated test generation."""

        return prompt

    def _call_bedrock(self, prompt: str, max_tokens: int = 8000) -> str:
        """Call Bedrock API.

        Args:
            prompt: The prompt to send
            max_tokens: Maximum tokens for response (default: 8000)

        Returns:
            Response text from the model
        """
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3  # Lower for analysis consistency
        })

        response = self.bedrock.invoke_model(
            modelId=self.model_id,
            body=body
        )

        response_body = json.loads(response['body'].read())
        return response_body['content'][0]['text']

    def _parse_analysis_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM analysis response."""
        # Find JSON in response
        json_match = re.search(r'\{[\s\S]*\}', response)
        if not json_match:
            logger.error("No JSON found in analysis response")
            return {"raw_response": response}

        try:
            analysis = json.loads(json_match.group(0))
            return analysis
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse analysis JSON: {e}")
            return {"raw_response": response, "error": str(e)}

    def _analyze_complexity(
        self,
        test_samples: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Analyze complexity distribution."""
        complexity_counts = Counter()
        complexity_characteristics = {}

        for sample in test_samples:
            complexity = sample.get("complexity", "unknown")
            complexity_counts[complexity] += 1

            # Gather characteristics for each complexity level
            if complexity not in complexity_characteristics:
                complexity_characteristics[complexity] = {
                    "avg_assertions": [],
                    "avg_max_turns": [],
                    "example_scenarios": []
                }

            if "assertions" in sample:
                complexity_characteristics[complexity]["avg_assertions"].append(
                    len(sample["assertions"])
                )

            if "max_turns" in sample:
                complexity_characteristics[complexity]["avg_max_turns"].append(
                    sample["max_turns"]
                )

            if len(complexity_characteristics[complexity]["example_scenarios"]) < 2:
                complexity_characteristics[complexity]["example_scenarios"].append(
                    sample.get("name", sample.get("id", "unnamed"))
                )

        # Calculate averages
        for complexity, chars in complexity_characteristics.items():
            if chars["avg_assertions"]:
                chars["avg_assertions"] = sum(chars["avg_assertions"]) / len(chars["avg_assertions"])
            else:
                chars["avg_assertions"] = 0

            if chars["avg_max_turns"]:
                chars["avg_max_turns"] = sum(chars["avg_max_turns"]) / len(chars["avg_max_turns"])
            else:
                chars["avg_max_turns"] = 0

        return {
            "distribution": dict(complexity_counts),
            "characteristics": complexity_characteristics,
            "total_samples": len(test_samples)
        }

    def _analyze_assertions(
        self,
        test_samples: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Analyze assertion patterns."""
        assertion_names = Counter()
        assertion_types = Counter()
        assertion_descriptions = []

        for sample in test_samples:
            if "assertions" in sample:
                for assertion in sample["assertions"]:
                    assertion_names[assertion.get("name", "unnamed")] += 1
                    assertion_types[assertion.get("type", "unknown")] += 1

                    if "description" in assertion:
                        assertion_descriptions.append({
                            "name": assertion.get("name"),
                            "type": assertion.get("type"),
                            "description": assertion["description"]
                        })

        return {
            "common_assertion_names": dict(assertion_names.most_common(10)),
            "assertion_types": dict(assertion_types),
            "assertion_examples": assertion_descriptions[:5]
        }

    def save_analysis(self, analysis: Dict[str, Any], output_path: str):
        """Save analysis results to file.

        Args:
            analysis: Analysis results
            output_path: Path to save JSON file
        """
        with open(output_path, 'w') as f:
            json.dump(analysis, f, indent=2)
        logger.info(f"Analysis saved to {output_path}")

    def load_analysis(self, input_path: str) -> Dict[str, Any]:
        """Load analysis results from file.

        Args:
            input_path: Path to JSON file

        Returns:
            Analysis results
        """
        with open(input_path, 'r') as f:
            return json.load(f)
