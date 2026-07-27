"""Server-side source pins (the Pinned section of the Sources screen).

Pins live on the server, not in client prefs, so they follow the account across
devices, and they are scoped to ``(user_id, profile_id)`` like every other
per-user row: two accounts never see each other's pins, and neither do two
profiles on one account.

``source_id`` is a connector key, not a foreign key -- connectors are code, not
rows. A pinned source can therefore stop resolving (connector excluded, renamed,
or hidden by the mature gate); such a pin is still returned, flagged
``available: false``, rather than silently vanishing from the user's ordering.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from connectors.registry import ConnectorDescriptor, list_installed_connectors
from core.config import get_settings
from core.errors import AppError
from core.profile_context import (
    ProfileContext,
    require_profile_context,
    resolve_profile_context,
)
from database.models import ReadingProfile, SourcePin
from database.session import get_db

SOURCE_ID_MAX = 64


class SourcePinService:
    # Pinning is a shortcut, not a second catalog: enough room for every
    # installed source and no more, so the payload stays bounded.
    MAX_PINS = 50

    def __init__(self, db: Session, ctx: ProfileContext) -> None:
        self._db = db
        self._user_id = ctx.user_id
        self._profile_id = ctx.profile_id

    # --- scoping -------------------------------------------------------------

    def _scoped(self):
        return select(SourcePin).where(
            SourcePin.user_id == self._user_id,
            SourcePin.profile_id == self._profile_id,
        )

    def _mature_enabled(self) -> bool:
        """Active mature gate (mirrors routes.settings._mature_enabled): the
        active profile's own toggle, else the global config default."""
        if self._profile_id is not None:
            profile = self._db.get(ReadingProfile, self._profile_id)
            if profile is not None:
                return bool(profile.mature_content_enabled)
        return get_settings().mature_content_enabled

    def _pinnable_sources(self) -> dict[str, ConnectorDescriptor]:
        """Sources the caller can actually see, keyed by connector id.

        Same filter GET /sources applies, so a source hidden behind the mature
        gate can neither be pinned nor surface through an older pin."""
        return {
            descriptor.source_type: descriptor
            for descriptor in list_installed_connectors(
                browsable_only=True,
                include_mature=self._mature_enabled(),
            )
        }

    # --- serialization -------------------------------------------------------

    @staticmethod
    def _serialize(
        pin: SourcePin, descriptor: ConnectorDescriptor | None
    ) -> dict[str, object]:
        return {
            "source_id": pin.source_id,
            "sort_order": pin.sort_order,
            # Falls back to the raw id so an unresolvable pin still renders as a
            # row the user can drop from their ordering.
            "name": descriptor.name if descriptor is not None else pin.source_id,
            "icon_url": descriptor.icon_url if descriptor is not None else None,
            "mature": bool(descriptor.mature) if descriptor is not None else False,
            "available": descriptor is not None,
        }

    # --- reads ---------------------------------------------------------------

    def list_pins(self) -> list[dict[str, object]]:
        if self._user_id is None:
            # Pins are owned rows (user_id NOT NULL); the unscoped/legacy bucket
            # has none rather than sharing one global set.
            return []
        available = self._pinnable_sources()
        rows = self._db.execute(
            self._scoped().order_by(SourcePin.sort_order, SourcePin.id)
        ).scalars()
        return [self._serialize(pin, available.get(pin.source_id)) for pin in rows]

    # --- writes --------------------------------------------------------------

    def _validate(self, source_ids: list[str]) -> list[str]:
        """Normalize the requested set: trimmed, de-duplicated, order preserved."""
        normalized: list[str] = []
        for raw in source_ids:
            if not isinstance(raw, str):
                raise AppError(
                    "Source ids must be strings.",
                    code="invalid_source_pin",
                    status_code=422,
                )
            candidate = raw.strip()
            if not candidate or len(candidate) > SOURCE_ID_MAX:
                raise AppError(
                    "Source ids must be 1-64 characters.",
                    code="invalid_source_pin",
                    status_code=422,
                )
            if candidate not in normalized:
                normalized.append(candidate)

        if len(normalized) > self.MAX_PINS:
            raise AppError(
                f"At most {self.MAX_PINS} sources can be pinned.",
                code="too_many_pins",
                status_code=422,
            )

        available = self._pinnable_sources()
        unknown = [item for item in normalized if item not in available]
        if unknown:
            raise AppError(
                "Unknown source.",
                code="unknown_source",
                status_code=422,
                details={"source_ids": unknown},
            )
        return normalized

    def replace_pins(self, source_ids: list[str]) -> list[dict[str, object]]:
        """Replace the whole pinned set, in the order given.

        Whole-set replace (not add/remove) because the client owns the ordering:
        it sends the list it wants and gets that exact list back. Rows that
        survive keep their identity so ``created_at`` still records when the
        source was first pinned.
        """
        if self._user_id is None:
            raise AppError(
                "Authentication required.", code="not_authenticated", status_code=401
            )

        wanted = self._validate(source_ids)
        existing = {
            pin.source_id: pin
            for pin in self._db.execute(self._scoped()).scalars()
        }

        for source_id, pin in existing.items():
            if source_id not in wanted:
                self._db.delete(pin)

        for order, source_id in enumerate(wanted):
            pin = existing.get(source_id)
            if pin is None:
                self._db.add(
                    SourcePin(
                        user_id=self._user_id,
                        profile_id=self._profile_id,
                        source_id=source_id,
                        sort_order=order,
                    )
                )
            elif pin.sort_order != order:
                pin.sort_order = order

        self._db.commit()
        return self.list_pins()


def get_source_pin_service(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[ProfileContext, Depends(resolve_profile_context)],
) -> SourcePinService:
    """Read path: a bad/absent profile header degrades to the unscoped bucket."""
    return SourcePinService(db, ctx)


def require_source_pin_service(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[ProfileContext, Depends(require_profile_context)],
) -> SourcePinService:
    """Write path: an account that owns profiles must name the one it is
    writing for, so pins can never land in the wrong profile's set."""
    return SourcePinService(db, ctx)
