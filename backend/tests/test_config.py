from core.config import Settings


def test_config_defaults(monkeypatch):
    """Test that settings load with correct defaults when no env vars are set."""
    # Ensure no conflicting env vars from the runner or .env file
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    # Instantiate directly to bypass lru_cache for testing
    # We also pass _env_file=None so it ignores the physical .env file in the folder
    settings = Settings(_env_file=None)

    assert settings.environment == "dev"
    assert settings.port == 8080
    assert settings.host == "0.0.0.0"
    assert settings.gemini_api_key == ""


def test_config_overrides(monkeypatch):
    """Test that environment variables override defaults."""
    monkeypatch.setenv("PORT", "5000")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")

    settings = Settings()

    assert settings.port == 5000
    assert settings.environment == "production"
    assert settings.gemini_api_key == "test-key-123"
