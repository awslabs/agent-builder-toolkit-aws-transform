"""Tests for experimental code execution support."""

import os
import warnings
from unittest import mock

# Import once at module level and filter warnings
warnings.filterwarnings(
    "ignore", category=FutureWarning, module="agent_builder_sdk.experimental"
)

from agent_builder_sdk.experimental.code_execution import python_repl  # noqa: E402


class TestPythonReplTool:
    """Tests for the python_repl tool."""

    def test_simple_print(self):
        """Test simple print statement execution."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            result = python_repl(code="print('hello world')")
        assert "hello world" in result

    def test_math_calculation(self):
        """Test mathematical calculation."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            result = python_repl(code="print(2 + 2)")
        assert "4" in result

    def test_multiline_code(self):
        """Test multiline code execution."""
        code = """
x = 10
y = 20
print(x + y)
"""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            result = python_repl(code=code)
        assert "30" in result

    def test_import_and_use_stdlib(self):
        """Test importing and using standard library."""
        code = """
import math
print(math.sqrt(16))
"""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            result = python_repl(code=code)
        assert "4.0" in result

    def test_syntax_error(self):
        """Test handling of syntax errors."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            result = python_repl(code="print('unclosed")
        assert "SyntaxError" in result

    def test_runtime_error(self):
        """Test handling of runtime errors."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            result = python_repl(code="print(undefined_variable)")
        assert "Error" in result

    def test_empty_code(self):
        """Test handling of empty code."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            result = python_repl(code="")
        assert "No code provided" in result

    def test_no_output(self):
        """Test code that produces no output."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            result = python_repl(code="x = 42")
        assert "(no output)" in result

    def test_data_analysis_example(self):
        """Test a realistic data analysis example."""
        code = """
data = [150, 230, 180, 310, 275, 195, 420]
mean = sum(data) / len(data)
print(f"Mean: {mean:.2f}")
print(f"Max: {max(data)}")
print(f"Min: {min(data)}")
"""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            result = python_repl(code=code)
        assert "Mean: 251.43" in result
        assert "Max: 420" in result
        assert "Min: 150" in result


class TestAgentFactoryCodeExecution:
    """Tests for code execution integration in agent factory."""

    @mock.patch.dict(os.environ, {"AWS_REGION": "us-west-2"}, clear=True)
    def test_enable_code_execution_adds_tool(self):
        """Test that enable_code_execution=True adds python_repl tool."""
        from agent_builder_sdk.agent_factory import (
            create_default_async_orchestrator_with_subagent,
        )

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            agent = create_default_async_orchestrator_with_subagent(
                system_prompt="Test prompt",
                enable_code_execution=True,
            )

        # Check that python_repl tool was added
        tool_names = [t.tool_name for t in agent.tool_registry.registry.values()]
        assert "python_repl" in tool_names

    @mock.patch.dict(os.environ, {"AWS_REGION": "us-west-2"}, clear=True)
    def test_code_execution_disabled_by_default(self):
        """Test that code execution is not added by default."""
        from agent_builder_sdk.agent_factory import (
            create_default_async_orchestrator_with_subagent,
        )

        agent = create_default_async_orchestrator_with_subagent(
            system_prompt="Test prompt",
        )

        # Check that python_repl tool was NOT added
        tool_names = [t.tool_name for t in agent.tool_registry.registry.values()]
        assert "python_repl" not in tool_names

    @mock.patch.dict(os.environ, {"AWS_REGION": "us-west-2"}, clear=True)
    def test_skills_and_code_execution_together(self):
        """Test enabling both skills and code execution."""
        from agent_builder_sdk.agent_factory import (
            create_default_async_orchestrator_with_subagent,
        )

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            agent = create_default_async_orchestrator_with_subagent(
                system_prompt="Test prompt",
                enable_skills=True,
                enable_code_execution=True,
            )

        tool_names = [t.tool_name for t in agent.tool_registry.registry.values()]
        assert "skills" in tool_names
        assert "python_repl" in tool_names
