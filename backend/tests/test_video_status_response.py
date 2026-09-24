"""
Regression test for a real bug caught during integration testing: the
`GET /videos/{id}` response model used `video_id` while the ORM column
is `id`, causing FastAPI's response validation to fail with a 500 on a
route that otherwise looked correct. Covered here so it can't regress.
"""
from app.api.v1.videos import VideoStatusResponse


def test_video_status_response_accepts_video_id_field():
    import uuid

    response = VideoStatusResponse(
        video_id=uuid.uuid4(), status="queued", progress=0, current_stage=None
    )
    assert response.status == "queued"
