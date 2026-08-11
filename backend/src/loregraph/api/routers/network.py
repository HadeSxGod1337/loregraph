from fastapi import APIRouter

from loregraph.api.deps import NetworkStatusDep
from loregraph.schemas.network import NetworkStatusOut, UpnpStatusOut

router = APIRouter(prefix="/network", tags=["network"])


@router.get("", response_model=NetworkStatusOut)
async def get_network_status(network: NetworkStatusDep) -> NetworkStatusOut:
    """How far the app is currently exposed and on what address.

    Both the launcher banner and the Players panel read this, so the address
    the DM is told to share and the one baked into invite links can never
    disagree."""
    upnp = (
        UpnpStatusOut(
            outcome=network.upnp.outcome,
            external_ip=network.upnp.external_ip,
            reachable=network.upnp.reachable,
        )
        if network.upnp is not None
        else None
    )
    return NetworkStatusOut(
        reach=network.reach,
        base_url=network.base_url,
        tls=network.tls,
        upnp=upnp,
    )
