"""
End-to-end smoke test: creates a user/project/video, runs the full
generation pipeline synchronously (bypassing the Redis queue so this can
run in CI without a worker process), and asserts a real MP4 was rendered
and registered as an asset.

Usage:
    DATABASE_URL=postgresql+asyncpg://app:password@localhost:5432/aivideo \
    JWT_SECRET=test PYTHONPATH=. python scripts/smoke_test.py
"""
import asyncio
import sys
import uuid

from moto import mock_aws
import boto3

from app.config.settings import get_settings
from app.db.models.generation_job import GenerationJob, JobStatus, JobType
from app.db.models.project import Project
from app.db.models.user import User
from app.db.models.video import Video, VideoStatus
from app.db.models.asset import Asset
from app.db.models.scene import Scene
from app.workers.tasks.rerender_task import rerender_video
from sqlalchemy import select
from app.db.session import session_scope
from app.security.auth import hash_password
from app.workers.tasks.pipeline_task import generation_pipeline
from app.api.v1.captions import CaptionEdit, edit_captions, get_captions
from app.api.v1.creator import creator_overview

settings = get_settings()


async def main() -> int:
    async with session_scope() as db:
        user = User(email="smoke-test@example.com", password_hash=hash_password("password123"))
        db.add(user)
        await db.flush()

        project = Project(user_id=user.id, name="Smoke Test Project")
        db.add(project)
        await db.flush()

        video = Video(
            project_id=project.id,
            topic="Five unbelievable ocean discoveries",
            language="English",
            locale="en-NG",
            duration_seconds=10,
            platform="youtube_shorts",
            status=VideoStatus.QUEUED,
        )
        db.add(video)
        await db.flush()

        job = GenerationJob(video_id=video.id, type=JobType.VIDEO_GENERATION, status=JobStatus.QUEUED)
        db.add(job)
        await db.flush()

        video_id, job_id = str(video.id), str(job.id)

    print(f"Created video={video_id} job={job_id}. Running pipeline...")
    await generation_pipeline(ctx={}, payload={"video_id": video_id, "job_id": job_id})

    async with session_scope() as db:
        video = await db.get(Video, video.id)
        job = await db.get(GenerationJob, job.id)
        print(f"Video status: {video.status.value} | progress: {video.progress}% | stage: {video.current_stage}")
        print(f"Job status: {job.status.value} | attempts: {job.attempts} | error: {job.error_message}")

        if video.status != VideoStatus.READY or job.status != JobStatus.SUCCEEDED:
            print("FAILED: pipeline did not complete successfully")
            return 1

        from app.db.models.asset import Asset
        from app.services.storage_service import get_object_bytes

        asset = await db.get(Asset, video.output_asset_id)
        video_bytes = get_object_bytes(asset.storage_key)
        print(f"Final asset: {asset.storage_key} ({len(video_bytes)} bytes, mime={asset.mime_type})")

        if len(video_bytes) < 1000 or video_bytes[4:8] != b"ftyp":
            print("FAILED: output does not look like a valid MP4")
            return 1

    # Re-render the persisted scene assets without recreating them.
    original_output_id = video.output_asset_id
    async with session_scope() as db:
        video = await db.get(Video, video.id)
        scenes = (await db.execute(select(Scene).where(Scene.video_id == video.id))).scalars().all()
        assert scenes and all(s.visual_asset_id and s.audio_asset_id for s in scenes)
        assert video.thumbnail_asset_id
        # Exercise the same caption and style endpoints as the creator UI.
        await edit_captions(
            video.id, CaptionEdit(scene_id=scenes[0].id, text="Edited in creator studio"),
            user=user, db=db,
        )
        await edit_captions(video.id, CaptionEdit(style="social"), user=user, db=db)
        captions = await get_captions(video.id, user=user, db=db)
        assert captions["style"] == "social"
        assert captions["scenes"][0]["text"] == "Edited in creator studio"
        assert video.needs_rerender
        video.status = VideoStatus.RENDERING
        render_job = GenerationJob(video_id=video.id, type=JobType.RENDER, status=JobStatus.QUEUED)
        db.add(render_job)
        await db.flush()
        render_job_id = str(render_job.id)

    await rerender_video(ctx={}, payload={"video_id": video_id, "job_id": render_job_id})

    async with session_scope() as db:
        updated_video = await db.get(Video, video.id)
        new_job = await db.get(GenerationJob, uuid.UUID(render_job_id))
        assert updated_video.status == VideoStatus.READY, updated_video.error_message
        assert new_job.status == JobStatus.SUCCEEDED, new_job.error_message
        assert updated_video.output_asset_id != original_output_id
        assert updated_video.needs_rerender is False
        new_asset = await db.get(Asset, updated_video.output_asset_id)
        assert get_object_bytes(new_asset.storage_key)[4:8] == b"ftyp"
        overview = await creator_overview(user=user, db=db)
        assert overview["stats"]["projects"] == 1
        assert overview["stats"]["total_videos"] == 1
        assert overview["stats"]["views"] == 0
        assert len(overview["recent_videos"]) == 1
    print("SMOKE TEST PASSED: creator overview, caption edits and two rendered MP4s.")
    return 0


if __name__ == "__main__":
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=get_settings().storage_bucket)
        exit_code = asyncio.run(main())
    sys.exit(exit_code)
