# API Reference

Base URL: `http://localhost:8000/api/v1` (interactive docs at `/docs`,
OpenAPI schema at `/openapi.json`).

All endpoints except `/auth/signup` and `/auth/login` require
`Authorization: Bearer <access_token>`.

## Auth

| Method | Path | Notes |
|---|---|---|
| POST | `/auth/signup` | Returns `{access_token, refresh_token}` |
| POST | `/auth/login` | Same response shape |

## Users

| Method | Path |
|---|---|
| GET | `/users/me` |

## Projects

| Method | Path | Notes |
|---|---|---|
| POST | `/projects` | Create |
| GET | `/projects` | List the caller's projects |
| GET | `/projects/{id}` | Object-level ownership enforced (404 if not owner) |
| DELETE | `/projects/{id}` | Cascades to its videos |

## Videos

| Method | Path | Notes |
|---|---|---|
| POST | `/videos/generate` | Body matches `GenerateVideoRequest`; accepts an `Idempotency-Key` header — repeating the same key returns the existing job instead of creating a duplicate. Rate-limited (10/min/user). |
| GET | `/videos/{id}` | Poll for `status`, `progress`, `current_stage` |
| POST | `/videos/{id}/script` | Regenerate the script + storyboard from scratch |
| GET | `/videos/{id}/scripts` | Version history |
| GET | `/videos/{id}/storyboard` | List scenes |
| POST | `/videos/{id}/storyboard/scenes/{scene_id}/regenerate` | Regenerate one scene's visual without re-running the whole project |

### `POST /videos/generate` request

```json
{
  "project_id": "uuid",
  "topic": "Five unbelievable ocean discoveries",
  "language": "English",
  "locale": "en-NG",
  "duration_seconds": 60,
  "platform": "youtube_shorts",
  "visual_style": "cinematic_realistic",
  "creativity": "high",
  "voice": { "gender": "female", "personality": "confident", "pace": 0.96 }
}
```

### Response

```json
{ "video_id": "uuid", "status": "queued", "job_id": "uuid", "message": "Video generation queued" }
```

### Status polling response

```json
{ "video_id": "uuid", "status": "rendering", "progress": 78, "current_stage": "rendering" }
```

## Jobs

| Method | Path |
|---|---|
| GET | `/jobs/{id}` |

## Voices

| Method | Path |
|---|---|
| GET | `/voices?locale=en-NG` |
| POST | `/voices/preview` — returns base64-encoded audio |

## Assets

| Method | Path |
|---|---|
| GET | `/assets/{id}` — returns a short-lived signed URL |

## Publishing

| Method | Path |
|---|---|
| POST | `/publishing/{platform}` — queues an async publish job |

## Analytics

| Method | Path |
|---|---|
| GET | `/analytics?video_id=uuid` |

## Billing

| Method | Path |
|---|---|
| GET | `/billing/credits` |
| GET | `/billing/credits/history` |

## Error shape

Every error response has a stable `error_code`:

```json
{ "error_code": "http_404", "message": "Project not found" }
```
