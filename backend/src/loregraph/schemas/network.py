from pydantic import BaseModel

from loregraph.services.upnp import UpnpOutcome


class UpnpStatusOut(BaseModel):
    """Result of asking the router to forward our port. `outcome` is the part
    that matters: each value means a different thing for the DM to do."""

    outcome: UpnpOutcome
    external_ip: str | None = None
    reachable: bool = False


class NetworkStatusOut(BaseModel):
    """Where the app is reachable from, and the address invite links use.

    Master-only: the external address and the exposure level are not something
    a player has any business reading."""

    # local = this machine only, lan = the local network, internet = a router
    # port-forward is in place.
    reach: str
    base_url: str
    tls: bool
    # None when internet mode was never asked for.
    upnp: UpnpStatusOut | None = None
