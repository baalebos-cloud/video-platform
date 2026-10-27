"""Release trace regression tests, no third-party credentials or network."""
from app.api.v1.videos import public_generation_error_message
from app.config.release import current_release, public_release
from app.ai.prompts.video_director_v4 import PROMPT_VERSION


def test_worker_release_identifies_actually_imported_director(monkeypatch):
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "f114fbef538b24e965e884859e64c9a52ff99775")
    monkeypatch.setenv("RAILWAY_DEPLOYMENT_ID", "test-deployment-id")
    info = current_release()
    assert info["director_contract"] == PROMPT_VERSION == "video-director-v4"
    assert info["git_commit"] == "f114fbef538b24e965e884859e64c9a52ff99775"
    assert info["deployment_id"] == "test-deployment-id"
    assert len(info["director_source"]) == 12
    assert all(char in "0123456789abcdef" for char in info["director_source"])


def test_public_health_identifies_version_without_deployment_ids(monkeypatch):
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "abcdef1234567890")
    monkeypatch.setenv("RAILWAY_DEPLOYMENT_ID", "private-deploy-identifier")
    info = public_release()
    assert info["git_commit"] == "abcdef123456"
    assert info["director_contract"] == "video-director-v4"
    assert "deployment_id" not in info
    assert "private-deploy-identifier" not in str(info)


def test_legacy_pydantic_failure_is_a_saved_record_not_new_generation():
    old = (
        "AI director output failed validation: 6 validation errors for VideoPlan "
        "hook Field required [type=missing, input_value={'secret': 'do-not-repeat'}]"
    )
    message = public_generation_error_message(old)
    assert "older AI director" in message
    assert "new video" in message
    assert "secret" not in message


def test_modern_validation_errors_are_not_overwritten():
    modern = "AI director returned an invalid plan; fields: scenes.0.sequence"
    assert public_generation_error_message(modern) == modern
    assert public_generation_error_message(None) is None


def test_release_fallback_is_safe_without_railway_variables(monkeypatch):
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
    monkeypatch.delenv("RAILWAY_DEPLOYMENT_ID", raising=False)
    assert current_release()["git_commit"] == "unavailable"
    assert public_release()["git_commit"] == "unavailable"
