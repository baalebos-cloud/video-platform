"""
Domain layer — business rules and entities, framework-independent.

In this codebase, ORM models (app/db/models) double as the persistence
representation of these entities, and business rules live in
app/services/*. These per-bounded-context packages are kept as explicit
extension points: as a bounded context grows complex enough to need
entities distinct from its ORM model (e.g. a rich `VideoPlan` domain
object independent of SQLAlchemy), add it here rather than growing the
service layer indefinitely. See docs/architecture.md, "Separation of
concerns".
"""
