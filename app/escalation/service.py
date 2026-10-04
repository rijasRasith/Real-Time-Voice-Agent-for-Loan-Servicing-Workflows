from __future__ import annotations

import json
from typing import List, Optional
from pydantic import BaseModel

from app.data.models import EscalationPriority, EscalationQueue
from app.data.repository import escalation_repo


class EscalationItem(BaseModel):
    id: str
    call_id: str
    reason_code: str
    priority: str
    packaged_context: dict
    created_at: str


class EscalationService:
    def get_pending_queue(self) -> List[EscalationItem]:
        records = escalation_repo.list_queued()
        items = []
        for r in records:
            try:
                context = json.loads(r.packaged_context)
            except Exception:
                context = {"raw": r.packaged_context}
            items.append(
                EscalationItem(
                    id=r.id,
                    call_id=r.call_id,
                    reason_code=r.reason_code,
                    priority=r.priority.value,
                    packaged_context=context,
                    created_at=r.created_at.isoformat() if r.created_at else "",
                )
            )
        return items


escalation_service = EscalationService()
