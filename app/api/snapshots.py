import hmac
from typing import Annotated

import httpx2
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.envelope import EnvelopeRoute
from app.core.http_client import get_http_client
from app.core.redis import get_redis
from app.core.settings import Settings, get_settings
from app.repositories.snapshot_runs import list_snapshot_runs
from app.schemas.snapshot import SnapshotPageQuery, SnapshotRunEntry, SnapshotRunPage
from app.services.snapshot_service import SnapshotLockHeldError, take_snapshot

router = APIRouter(prefix="/snapshots", tags=["snapshots"], route_class=EnvelopeRoute)


def require_snapshot_api_key(
    x_api_key: str = Header(...),
    settings: Settings = Depends(get_settings),
) -> None:
    if not hmac.compare_digest(x_api_key, settings.snapshot_api_key):
        raise HTTPException(status_code=401, detail="Invalid or missing X-Api-Key")


@router.get("")
async def list_snapshots(
    page: Annotated[SnapshotPageQuery, Query()],
    session: AsyncSession = Depends(get_session),
) -> SnapshotRunPage:
    # One extra row shows whether an older page exists, without a COUNT query.
    rows = await list_snapshot_runs(session, page.limit + 1, page.before_id)
    has_older_page = len(rows) > page.limit
    items = [
        SnapshotRunEntry(
            id=run.id,
            started_at=run.started_at,
            finished_at=run.finished_at,
            status=run.status,
            run_at=run_at,
            error_code=run.error_code,
        )
        for run, run_at in rows[: page.limit]
    ]
    next_before_id = items[-1].id if has_older_page else None
    return SnapshotRunPage(items=items, next_before_id=next_before_id)


@router.post("", dependencies=[Depends(require_snapshot_api_key)])
async def create_snapshot(
    client: httpx2.AsyncClient = Depends(get_http_client),
    settings: Settings = Depends(get_settings),
    redis: Redis = Depends(get_redis),
) -> JSONResponse:
    try:
        result = await take_snapshot(client, settings, redis)
    except SnapshotLockHeldError:
        raise HTTPException(
            status_code=409,
            detail={"code": "LOCK_HELD", "message": "A snapshot run is already in progress"},
        ) from None
    except httpx2.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "UPSTREAM_ERROR",
                "message": f"Open-Meteo returned {exc.response.status_code}",
            },
        ) from exc
    except httpx2.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "UPSTREAM_UNAVAILABLE", "message": "Could not reach Open-Meteo"},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=502, detail={"code": "UPSTREAM_ERROR", "message": str(exc)}
        ) from exc
    # Any other exception (e.g. a DB error) is a real bug, not an upstream
    # failure, so it is left to propagate to EnvelopeRoute's generic 500
    # handler instead of being mislabelled as a 502 here.

    status_code = 201 if result.status == "created" else 200
    return JSONResponse(
        status_code=status_code,
        content={
            "Status": result.status,
            "RunAt": result.run_at.isoformat() if result.run_at else None,
            "LocationsFetched": result.locations_fetched,
        },
    )
