"""Canonical payload digest binds a second-factor approval to one exact adjustment."""
import hashlib
import json
import uuid

from pydantic import BaseModel, Field, model_validator


class CreditAdjustment(BaseModel):
    user_id: uuid.UUID
    amount: int = Field(ge=-1000, le=1000)
    request_id: uuid.UUID
    reason: str = Field(min_length=12, max_length=300)

    @model_validator(mode="after")
    def validate_adjustment(self):
        if self.amount == 0:
            raise ValueError("Credit adjustment amount cannot be zero")
        if len(self.reason.strip()) < 12:
            raise ValueError("A meaningful adjustment reason is required")
        return self


def digest_credit_adjustment(payload: CreditAdjustment) -> str:
    parts = payload.model_dump(mode="json")
    parts["reason"] = parts["reason"].strip()
    canonical = json.dumps(parts, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
