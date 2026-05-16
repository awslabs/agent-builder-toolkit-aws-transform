#!/usr/bin/env python3
"""Unit tests for test data generator modules (no AWS credentials required)."""

import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Import modules to test
from evaluation.test_data_generator.context_loader import (
    LoadingStrategy,
    ContextLoader,
    LOADING_STRATEGIES,
    create_custom_strategy
)
from evaluation.test_data_generator.deduplicate_tests import deduplicate_tests
from evaluation.test_data_generator.domain_analyzer import DomainAnalyzer


class TestContextLoader(unittest.TestCase):
    """Test ContextLoader without filesystem access."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)

    def tearDown(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_loading_strategy_creation(self):
        """Test LoadingStrategy can be created with valid config."""
        strategy = LoadingStrategy(
            name="test_strategy",
            description="Test description",
            priority_patterns={'main.py': 100},
            extension_priorities={'.py': 50},
            max_file_size=50000
        )
        self.assertEqual(strategy.name, "test_strategy")
        self.assertEqual(strategy.description, "Test description")
        self.assertIn('main.py', strategy.priority_patterns)
        self.assertIn('.py', strategy.extension_priorities)
        self.assertEqual(strategy.max_file_size, 50000)

    def test_predefined_strategies_exist(self):
        """Test that predefined loading strategies are available."""
        self.assertIn('agent_evaluation', LOADING_STRATEGIES)
        self.assertIn('generic', LOADING_STRATEGIES)
        self.assertIsInstance(LOADING_STRATEGIES['agent_evaluation'], LoadingStrategy)

    def test_context_loader_initialization(self):
        """Test ContextLoader initializes with a strategy."""
        loader = ContextLoader(strategy='generic')
        self.assertIsNotNone(loader.strategy)
        self.assertEqual(loader.strategy.name, 'generic')

    def test_context_loader_invalid_strategy(self):
        """Test ContextLoader falls back to generic for invalid strategy."""
        loader = ContextLoader(strategy='nonexistent_strategy')
        # Should fall back to 'generic'
        self.assertEqual(loader.strategy.name, 'generic')

    def test_context_loader_with_custom_strategy(self):
        """Test ContextLoader accepts custom strategy object."""
        custom = create_custom_strategy(
            name="custom",
            description="Custom test strategy",
            exclude_patterns=['node_modules/**']
        )
        loader = ContextLoader(custom_strategy=custom)
        self.assertEqual(loader.strategy.name, "custom")

    def test_is_text_file_detects_binary(self):
        """Test binary file detection."""
        # Create binary file
        binary_file = self.temp_path / "binary.bin"
        binary_file.write_bytes(b'\x00\x01\x02\xff')

        # Create text file
        text_file = self.temp_path / "text.txt"
        text_file.write_text("Hello world")

        loader = ContextLoader(strategy='generic')
        self.assertFalse(loader._is_text_file(binary_file))
        self.assertTrue(loader._is_text_file(text_file))

    def test_load_single_file(self):
        """Test loading a single text file."""
        test_file = self.temp_path / "test.md"
        test_content = "# Test Document\n\nThis is a test."
        test_file.write_text(test_content)

        loader = ContextLoader(strategy='generic')
        result = loader.load(str(test_file))

        self.assertIsNotNone(result)
        self.assertIn("Test Document", result)
        self.assertIn(test_content, result)

    def test_load_nonexistent_path(self):
        """Test loading from nonexistent path returns None."""
        loader = ContextLoader(strategy='generic')
        result = loader.load("/nonexistent/path/to/nowhere")
        self.assertIsNone(result)

    def test_skip_directories(self):
        """Test that skip_dirs are properly excluded."""
        # Create directory structure
        (self.temp_path / ".git").mkdir()
        (self.temp_path / ".git" / "config").write_text("git config")
        (self.temp_path / "src").mkdir()
        (self.temp_path / "src" / "main.py").write_text("print('hello')")

        loader = ContextLoader(strategy='generic')
        result = loader.load(str(self.temp_path))

        # Should have main.py but not .git/config
        self.assertIsNotNone(result)
        self.assertIn("main.py", result)
        self.assertNotIn("git config", result)

    def test_skip_large_files(self):
        """Test that files exceeding max_file_size are skipped."""
        large_file = self.temp_path / "large.txt"
        large_file.write_text("x" * (200 * 1024))  # 200KB

        small_file = self.temp_path / "small.txt"
        small_file.write_text("small content")

        loader = ContextLoader(strategy='generic')
        result = loader.load(str(self.temp_path))

        self.assertIsNotNone(result)
        self.assertIn("small content", result)
        self.assertNotIn("x" * 1000, result)  # Large file should be skipped


class TestDeduplication(unittest.TestCase):
    """Test deduplication logic."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)

    def tearDown(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_deduplicate_keep_first(self):
        """Test keep_first strategy."""
        tests = [
            {"name": "test_one", "id": "1", "complexity": "simple"},
            {"name": "test_one", "id": "2", "complexity": "medium"},
            {"name": "test_two", "id": "3", "complexity": "complex"}
        ]

        input_file = self.temp_path / "input.json"
        output_file = self.temp_path / "output.json"
        input_file.write_text(json.dumps(tests))

        deduplicate_tests(str(input_file), str(output_file), strategy="keep_first")

        result = json.loads(output_file.read_text())
        self.assertEqual(len(result), 2)
        # Should keep first "test_one" (id=1)
        test_one = [t for t in result if t["name"] == "test_one"][0]
        self.assertEqual(test_one["id"], "1")

    def test_deduplicate_keep_best(self):
        """Test keep_best strategy (keeps test with most assertions)."""
        tests = [
            {"name": "test_one", "id": "1", "complexity": "simple", "assertions": [{"name": "a1"}]},
            {"name": "test_one", "id": "2", "complexity": "medium", "assertions": [{"name": "a2"}, {"name": "a3"}]},
            {"name": "test_two", "id": "3", "complexity": "complex", "assertions": []}
        ]

        input_file = self.temp_path / "input.json"
        output_file = self.temp_path / "output.json"
        input_file.write_text(json.dumps(tests))

        deduplicate_tests(str(input_file), str(output_file), strategy="keep_best")

        result = json.loads(output_file.read_text())
        self.assertEqual(len(result), 2)
        # Should keep "test_one" with most assertions (id=2, 2 assertions)
        test_one = [t for t in result if t["name"] == "test_one"][0]
        self.assertEqual(test_one["id"], "2")
        self.assertEqual(len(test_one["assertions"]), 2)

    def test_deduplicate_keep_all_unique(self):
        """Test keep_all_unique strategy (renames duplicates)."""
        tests = [
            {
                "name": "test_one",
                "id": "1",
                "assertions": [{"name": "a1"}, {"name": "a2"}]
            },
            {
                "name": "test_one",
                "id": "2",
                "assertions": [{"name": "a3"}]
            }
        ]

        input_file = self.temp_path / "input.json"
        output_file = self.temp_path / "output.json"
        input_file.write_text(json.dumps(tests))

        deduplicate_tests(str(input_file), str(output_file), strategy="keep_all_unique")

        result = json.loads(output_file.read_text())
        self.assertEqual(len(result), 2)
        # Should have renamed second test
        names = {t["name"] for t in result}
        self.assertIn("test_one", names)
        self.assertIn("test_one (variant 2)", names)

    def test_deduplicate_no_duplicates(self):
        """Test deduplication with no duplicates."""
        tests = [
            {"name": "test_one", "id": "1"},
            {"name": "test_two", "id": "2"},
            {"name": "test_three", "id": "3"}
        ]

        input_file = self.temp_path / "input.json"
        output_file = self.temp_path / "output.json"
        input_file.write_text(json.dumps(tests))

        deduplicate_tests(str(input_file), str(output_file), strategy="keep_first")

        result = json.loads(output_file.read_text())
        self.assertEqual(len(result), 3)


class TestDomainAnalyzer(unittest.TestCase):
    """Test DomainAnalyzer structural analysis (no API calls)."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock boto3 to avoid needing AWS credentials
        self.boto_patcher = patch('evaluation.test_data_generator.domain_analyzer.boto3')
        self.mock_boto = self.boto_patcher.start()
        self.mock_boto.client.return_value = MagicMock()

        self.analyzer = DomainAnalyzer(
            region_name='us-west-2',
            model_id='test-model'
        )

        self.sample_tests = [
            {
                "id": "test-1",
                "name": "Test One",
                "complexity": "simple",
                "tags": ["unit", "basic"],
                "metadata": {"domain": "testing", "type": "functional"},
                "assertions": [
                    {"name": "assert_1", "type": "llm_judge", "check": "something"},
                    {"name": "assert_2", "type": "tool_called", "check": "tool_name"}
                ]
            },
            {
                "id": "test-2",
                "name": "Test Two",
                "complexity": "medium",
                "tags": ["integration"],
                "metadata": {"domain": "testing", "category": "api"},
                "assertions": [
                    {"name": "assert_3", "type": "transcript_contains", "check": "expected"}
                ]
            }
        ]

    def tearDown(self):
        """Clean up patches."""
        self.boto_patcher.stop()

    def test_extract_structural_patterns(self):
        """Test structural pattern extraction."""
        patterns = self.analyzer._extract_structural_patterns(self.sample_tests)

        self.assertIn('fields', patterns)
        self.assertIn('metadata_keys', patterns)
        self.assertIn('assertion_types', patterns)
        self.assertIn('tags', patterns)

        # Check field extraction
        self.assertIn('id', patterns['fields'])
        self.assertIn('name', patterns['fields'])
        self.assertIn('complexity', patterns['fields'])

        # Check metadata keys
        self.assertIn('domain', patterns['metadata_keys'])
        self.assertIn('type', patterns['metadata_keys'])

        # Check assertion types
        self.assertIn('llm_judge', patterns['assertion_types'])
        self.assertIn('tool_called', patterns['assertion_types'])

    def test_analyze_complexity(self):
        """Test complexity distribution analysis."""
        analysis = self.analyzer._analyze_complexity(self.sample_tests)

        self.assertIn('distribution', analysis)
        self.assertIn('simple', analysis['distribution'])
        self.assertIn('medium', analysis['distribution'])
        self.assertEqual(analysis['distribution']['simple'], 1)
        self.assertEqual(analysis['distribution']['medium'], 1)

    def test_analyze_assertions(self):
        """Test assertion pattern analysis."""
        analysis = self.analyzer._analyze_assertions(self.sample_tests)

        self.assertIn('assertion_types', analysis)
        self.assertIn('llm_judge', analysis['assertion_types'])
        self.assertIn('tool_called', analysis['assertion_types'])
        self.assertIn('transcript_contains', analysis['assertion_types'])

        # Check counts
        self.assertEqual(analysis['assertion_types']['llm_judge'], 1)
        self.assertEqual(analysis['assertion_types']['tool_called'], 1)

    def test_get_default_structure(self):
        """Test default structure when no samples provided."""
        default = self.analyzer._get_default_structure()

        self.assertIn('fields', default)
        self.assertIn('metadata_keys', default)
        self.assertIn('assertion_types', default)
        self.assertIsInstance(default['fields'], dict)

    def test_analyze_empty_samples(self):
        """Test analysis handles empty sample list."""
        patterns = self.analyzer._extract_structural_patterns([])
        self.assertIn('fields', patterns)
        self.assertEqual(len(patterns['fields']), 0)


class TestCustomStrategyCreation(unittest.TestCase):
    """Test custom strategy creation helper."""

    def test_create_custom_strategy_basic(self):
        """Test basic custom strategy creation."""
        strategy = create_custom_strategy(
            name="my_strategy",
            description="My test strategy",
            exclude_patterns=['test/**']
        )
        self.assertEqual(strategy.name, "my_strategy")
        self.assertEqual(strategy.description, "My test strategy")
        self.assertIn('test/**', strategy.exclude_patterns)

    def test_create_custom_strategy_with_priorities(self):
        """Test custom strategy with priority patterns."""
        strategy = create_custom_strategy(
            name="extended",
            description="Extended strategy",
            priority_patterns={'important.md': 100},
            extension_priorities={'.md': 80}
        )
        self.assertEqual(strategy.name, "extended")
        self.assertIn('important.md', strategy.priority_patterns)
        self.assertIn('.md', strategy.extension_priorities)
        self.assertEqual(strategy.priority_patterns['important.md'], 100)

    def test_create_custom_strategy_file_size(self):
        """Test custom max_file_size setting."""
        strategy = create_custom_strategy(
            name="large_files",
            description="Strategy for large files",
            max_file_size=500000
        )
        self.assertEqual(strategy.max_file_size, 500000)


def run_tests():
    """Run all unit tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestContextLoader))
    suite.addTests(loader.loadTestsFromTestCase(TestDeduplication))
    suite.addTests(loader.loadTestsFromTestCase(TestDomainAnalyzer))
    suite.addTests(loader.loadTestsFromTestCase(TestCustomStrategyCreation))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == '__main__':
    import sys
    success = run_tests()
    sys.exit(0 if success else 1)
