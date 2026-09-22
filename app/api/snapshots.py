import hmac

import httpx2
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.envelope import EnvelopeRoute
from app.core.settings import Settings, get_settings
from app.services.snapshot_service import SnapshotLockHeldError, take_snapshot

router = APIRouter(prefix="/snapshots", tags=["snapshots"], route_class=EnvelopeRoute)


def require_snapshot_api_key(
    x_api_key: str = Header(...),
    settings: Settings = Depends(get_settings),
) -> None:
    if not hmac.compare_digest(x_api_key, settings.snapshot_api_key):
        raise HTTPException(status_code=401, detail="Invalid or missing X-Api-Key")


@router.post("", dependencies=[Depends(require_snapshot_api_key)])
async def create_snapshot(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    client = request.app.state.http_client
    try:
        result = await take_snapshot(client, settings)
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
