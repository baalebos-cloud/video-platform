"""Non-secret release identity for production incident diagnosis.

Railway git metadata is supplied by GitHub-triggered deployments. When a
service is deployed from a different source or a cached image, the source
fingerprint still identifies the exact director Python file being executed.
"""
import hashlib
import os
from pathlib import Path

from app.ai.director import director
from app.ai.prompts.video_director_v2 import PROMPT_VERSION


def current_release() -> dict[str, str]:
    """Describe the actual imported director implementation, not a desired version."""
    fingerprint = hashlib.sha256(Path(director.__file__).read_bytes()).hexdigest()[:12]
    return {
        "director_contract": PROMPT_VERSION,
        "director_source": fingerprint,
        "git_commit": os.getenv("RAILWAY_GIT_COMMIT_SHA", "unavailable"),
        "deployment_id": os.getenv("RAILWAY_DEPLOYMENT_ID", "unavailable"),
    }


def public_release() -> dict[str, str]:
    """Short health fields; don't disclose internal deployment IDs or secrets."""
    release = current_release()
    commit = release["git_commit"]
    return {
        "director_contract": release["director_contract"],
        "director_source": release["director_source"],
        "git_commit": commit[:12] if commit != "unavailable" else "unavailable",
    }
