"""Basic test to verify pytest setup."""

import alcyoneus as alc  # noqa: F401


def test_basic_functionality():
    """Test basic functionality to ensure pytest works."""
    expected_result = 2
    result = 1 + 1
    assert result == expected_result  # noqa: S101


def test_alcyoneus_import():
    """Test that alcyoneus module can be imported."""
    # If we get here without errors, the import worked
    assert True  # noqa: S101
