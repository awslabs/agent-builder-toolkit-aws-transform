# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for ValidatorInterface Protocol and ValidationResult."""

from eval_runner.validators.interface import ValidationResult, ValidatorInterface


class TestValidationResult:
    def test_passed_result(self):
        result = ValidationResult(valid=True, reason="All checks passed")
        assert result.valid is True
        assert result.reason == "All checks passed"

    def test_failed_result_with_details(self):
        result = ValidationResult(
            valid=False,
            reason="Patch too large",
            details={"lines_added": 500, "max_allowed": 200},
        )
        assert result.valid is False
        assert result.reason == "Patch too large"
        assert result.details["lines_added"] == 500

    def test_defaults(self):
        result = ValidationResult(valid=True)
        assert result.reason == ""
        assert result.details == {}


class TestValidatorInterface:
    def test_structural_typing_satisfied(self):
        class MyValidator:
            @property
            def name(self) -> str:
                return "my_validator"

            def validate(self, patch: str, context: dict) -> ValidationResult:
                return ValidationResult(valid=True)

        v = MyValidator()
        assert isinstance(v, ValidatorInterface)
        assert v.name == "my_validator"

    def test_missing_method_not_satisfied(self):
        class NotAValidator:
            pass

        assert not isinstance(NotAValidator(), ValidatorInterface)

    def test_missing_name_not_satisfied(self):
        class NoName:
            def validate(self, patch: str, context: dict) -> ValidationResult:
                return ValidationResult(valid=True)

        assert not isinstance(NoName(), ValidatorInterface)
