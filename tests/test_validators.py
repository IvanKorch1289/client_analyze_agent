"""
Tests for validation utilities.

Tests both shared security validators and frontend validators.
"""

from app.frontend.lib.validators import (
    ValidationResult,
    validate_client_name,
    validate_client_name_extended,
    validate_date_range,
    validate_date_range_extended,
    validate_email,
    validate_email_extended,
    validate_inn,
    validate_inn_extended,
    validate_phone,
    validate_phone_extended,
)
from app.shared.security import (
    INNValidationResult,
    validate_inn as validate_inn_shared,
    validate_inn_extended as validate_inn_extended_shared,
)


class TestSharedSecurityValidators:
    """Tests for app.shared.security validators."""

    def test_validate_inn_valid_10_digits(self):
        """Test valid 10-digit INN (legal entity)."""
        is_valid, error = validate_inn_shared("7707083893")
        assert is_valid is True
        assert error == ""

    def test_validate_inn_valid_12_digits(self):
        """Test valid 12-digit INN (individual/entrepreneur)."""
        is_valid, error = validate_inn_shared("771234567890")
        assert is_valid is True
        assert error == ""

    def test_validate_inn_invalid_length(self):
        """Test invalid INN length."""
        is_valid, error = validate_inn_shared("123")
        assert is_valid is False
        assert "10" in error and "12" in error

    def test_validate_inn_invalid_non_numeric(self):
        """Test INN with non-numeric characters."""
        is_valid, error = validate_inn_shared("abc123")
        assert is_valid is False
        assert "только цифры" in error

    def test_validate_inn_empty_not_required(self):
        """Test empty INN when not required."""
        is_valid, error = validate_inn_shared("", required=False)
        assert is_valid is True
        assert error == ""

    def test_validate_inn_empty_required(self):
        """Test empty INN when required."""
        is_valid, error = validate_inn_shared("", required=True)
        assert is_valid is False
        assert "обязателен" in error

    def test_validate_inn_extended(self):
        """Test extended INN validation with suggestions."""
        result = validate_inn_extended_shared("123")
        assert isinstance(result, INNValidationResult)
        assert result.is_valid is False
        assert "10 или 12 цифр" in result.error_message
        assert result.suggestion != ""


class TestFrontendValidators:
    """Tests for app.frontend.lib.validators."""

    def test_validate_inn_wrapper(self):
        """Test frontend validate_inn wrapper."""
        is_valid, error = validate_inn("7707083893")
        assert is_valid is True
        assert error == ""

    def test_validate_inn_extended_wrapper(self):
        """Test frontend validate_inn_extended wrapper."""
        result = validate_inn_extended("abc")
        assert isinstance(result, ValidationResult)
        assert result.is_valid is False
        assert result.field_name == "ИНН"
        assert result.suggestion is not None

    def test_validate_client_name_valid(self):
        """Test valid client name."""
        is_valid, error = validate_client_name("ООО Ромашка")
        assert is_valid is True
        assert error == ""

    def test_validate_client_name_too_short(self):
        """Test client name too short."""
        is_valid, error = validate_client_name("A")
        assert is_valid is False
        assert "короткое" in error

    def test_validate_client_name_too_long(self):
        """Test client name too long."""
        long_name = "A" * 201
        is_valid, error = validate_client_name(long_name)
        assert is_valid is False
        assert "длинное" in error

    def test_validate_client_name_empty_required(self):
        """Test empty client name when required."""
        is_valid, error = validate_client_name("", required=True)
        assert is_valid is False
        assert "обязательно" in error

    def test_validate_client_name_extended(self):
        """Test extended client name validation."""
        result = validate_client_name_extended("A")
        assert isinstance(result, ValidationResult)
        assert result.is_valid is False
        assert result.field_name == "Название компании"
        assert result.suggestion is not None

    def test_validate_email_valid(self):
        """Test valid email."""
        is_valid, error = validate_email("test@example.com")
        assert is_valid is True
        assert error == ""

    def test_validate_email_invalid_no_at(self):
        """Test email without @ symbol."""
        is_valid, error = validate_email("invalid-email")
        assert is_valid is False
        assert "@" in error

    def test_validate_email_invalid_no_domain(self):
        """Test email without domain."""
        is_valid, error = validate_email("test@example")
        assert is_valid is False
        assert "домен" in error

    def test_validate_email_extended(self):
        """Test extended email validation."""
        result = validate_email_extended("invalid")
        assert isinstance(result, ValidationResult)
        assert result.is_valid is False
        assert result.field_name == "Email"
        assert result.suggestion is not None

    def test_validate_phone_valid(self):
        """Test valid Russian phone number."""
        is_valid, error = validate_phone("+7 (999) 123-45-67")
        assert is_valid is True
        assert error == ""

    def test_validate_phone_valid_11_digits(self):
        """Test valid 11-digit phone."""
        is_valid, error = validate_phone("79991234567")
        assert is_valid is True
        assert error == ""

    def test_validate_phone_too_short(self):
        """Test phone number too short."""
        is_valid, error = validate_phone("123")
        assert is_valid is False
        assert "короткий" in error

    def test_validate_phone_too_long(self):
        """Test phone number too long."""
        is_valid, error = validate_phone("1234567890123")
        assert is_valid is False
        assert "длинный" in error

    def test_validate_phone_invalid_prefix(self):
        """Test phone with invalid prefix."""
        is_valid, error = validate_phone("99991234567")
        assert is_valid is False
        assert "7 или 8" in error

    def test_validate_phone_extended(self):
        """Test extended phone validation."""
        result = validate_phone_extended("123")
        assert isinstance(result, ValidationResult)
        assert result.is_valid is False
        assert result.field_name == "Телефон"
        assert result.suggestion is not None

    def test_validate_date_range_valid(self):
        """Test valid date range."""
        from datetime import date

        start = date(2024, 1, 1)
        end = date(2024, 1, 31)
        is_valid, error = validate_date_range(start, end)
        assert is_valid is True
        assert error == ""

    def test_validate_date_range_invalid_order(self):
        """Test date range with end before start."""
        from datetime import date

        start = date(2024, 1, 31)
        end = date(2024, 1, 1)
        is_valid, error = validate_date_range(start, end)
        assert is_valid is False
        assert "позже" in error or "раньше" in error

    def test_validate_date_range_extended(self):
        """Test extended date range validation."""
        from datetime import date

        start = date(2024, 1, 31)
        end = date(2024, 1, 1)
        result = validate_date_range_extended(start, end)
        assert isinstance(result, ValidationResult)
        assert result.is_valid is False
        assert result.field_name == "Период"
        assert result.suggestion is not None

    def test_validation_result_bool(self):
        """Test ValidationResult boolean conversion."""
        valid_result = ValidationResult(is_valid=True, error_message="")
        invalid_result = ValidationResult(is_valid=False, error_message="Error")

        assert bool(valid_result) is True
        assert bool(invalid_result) is False


class TestValidatorIntegration:
    """Integration tests to ensure validators work together."""

    def test_shared_and_frontend_inn_consistency(self):
        """Test that shared and frontend INN validators return consistent results."""
        test_inns = ["7707083893", "771234567890", "123", "abc", ""]

        for inn in test_inns:
            shared_valid, shared_error = validate_inn_shared(inn, required=False)
            frontend_valid, frontend_error = validate_inn(inn, required=False)

            assert shared_valid == frontend_valid, f"Inconsistent validation for INN: {inn}"

    def test_extended_validation_includes_suggestions(self):
        """Test that extended validators provide helpful suggestions."""
        # INN
        inn_result = validate_inn_extended("123")
        assert inn_result.suggestion != ""
        assert len(inn_result.suggestion) > 10  # Non-trivial suggestion

        # Client name
        name_result = validate_client_name_extended("A")
        assert name_result.suggestion != ""

        # Email
        email_result = validate_email_extended("invalid")
        assert email_result.suggestion != ""

        # Phone
        phone_result = validate_phone_extended("123")
        assert phone_result.suggestion != ""
