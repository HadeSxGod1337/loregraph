"""Asking the router to forward our port, the way Foundry does.

This is the only way a player outside the local network reaches a self-hosted
app without anyone installing anything: the router maps an external port to
this machine. UPnP lets us ask for that mapping automatically.

It will not always work, and saying *why* matters more than the automation:
a router with UPnP disabled, or an ISP that puts the whole subscriber behind
CGNAT, cannot be worked around from here — but the difference between "turn
UPnP on" and "your provider does not hand out public addresses" is the
difference between a two-minute fix and an evening lost guessing.

Deliberately hand-rolled over httpx (already a dependency) rather than pulling
in a UPnP stack: this needs three SOAP calls and one SSDP search.
"""

import asyncio
import ipaddress
import logging
import re
import socket
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger(__name__)

SSDP_ADDRESS = "239.255.255.250"
SSDP_PORT = 1900
SSDP_TIMEOUT_SECONDS = 3.0
# Router descriptions are small; a cap keeps a malformed or hostile response
# from being parsed at all (ElementTree is not hardened against entity bombs).
MAX_DESCRIPTION_BYTES = 256 * 1024
HTTP_TIMEOUT_SECONDS = 5.0
# An hour, refreshed while we run, so a crash cannot leave the port open
# forever. Routers that only accept permanent mappings fall back to 0.
LEASE_SECONDS = 3600
MAPPING_DESCRIPTION = "Loregraph"

_IGD_SEARCH_TARGETS = (
    "urn:schemas-upnp-org:device:InternetGatewayDevice:1",
    "urn:schemas-upnp-org:service:WANIPConnection:1",
    "urn:schemas-upnp-org:service:WANPPPConnection:1",
)
_WAN_SERVICE_TYPES = (
    "urn:schemas-upnp-org:service:WANIPConnection:1",
    "urn:schemas-upnp-org:service:WANPPPConnection:1",
)
# UPnP error code for routers that refuse a timed lease.
_ONLY_PERMANENT_LEASES = "725"

# Why the port is (not) reachable from the internet. Machine-readable so the
# UI can translate it; every value has a different thing for the user to do.
UpnpOutcome = Literal[
    "mapped",  # router forwarded the port and the address is public
    "cgnat",  # provider hands out a shared address — nothing to forward to
    "no_router",  # no UPnP-capable router answered (often disabled)
    "refused",  # router answered but declined to map
    "failed",  # something else broke; details in the log
]


@dataclass(frozen=True)
class UpnpMapping:
    """Result of trying to open the port to the internet."""

    outcome: UpnpOutcome
    external_ip: str | None = None
    external_port: int | None = None
    # Set when a lease was accepted, so it can be refreshed while we run.
    lease_seconds: int = 0

    @property
    def reachable(self) -> bool:
        return self.outcome == "mapped"


def is_public_address(ip: str) -> bool:
    """False for anything the internet cannot route back to.

    CGNAT (100.64.0.0/10) is the interesting case: the router reports it as its
    "external" address, but it is really one more layer of NAT owned by the
    provider, so no port forwarding on this end can help."""
    try:
        parsed = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if parsed in ipaddress.ip_network("100.64.0.0/10"):
        return False
    return not (
        parsed.is_private
        or parsed.is_loopback
        or parsed.is_link_local
        or parsed.is_reserved
        or parsed.is_unspecified
    )


def _local_ipv4_addresses() -> list[str]:
    """Every local IPv4 address, so the search can go out each of them.

    A machine with Docker, WSL or a VPN has several interfaces, and a multicast
    sent only from the default route routinely misses the actual router — which
    looks exactly like "this router has no UPnP". Empty string = let the OS
    choose, kept first because it is right on simple setups."""
    addresses = [""]
    try:
        _host, _aliases, ips = socket.gethostbyname_ex(socket.gethostname())
        addresses.extend(ip for ip in ips if not ip.startswith("127."))
    except OSError:
        logger.debug("Could not enumerate local addresses", exc_info=True)
    return addresses


def _search_from(local_ip: str, target: str) -> str | None:
    request = (
        "M-SEARCH * HTTP/1.1\r\n"
        f"HOST: {SSDP_ADDRESS}:{SSDP_PORT}\r\n"
        'MAN: "ssdp:discover"\r\n'
        "MX: 2\r\n"
        f"ST: {target}\r\n"
        "\r\n"
    ).encode()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(SSDP_TIMEOUT_SECONDS)
        try:
            if local_ip:
                sock.bind((local_ip, 0))
                sock.setsockopt(
                    socket.IPPROTO_IP,
                    socket.IP_MULTICAST_IF,
                    socket.inet_aton(local_ip),
                )
            sock.sendto(request, (SSDP_ADDRESS, SSDP_PORT))
            while True:
                data, _addr = sock.recvfrom(8192)
                match = re.search(
                    rb"^LOCATION:\s*(\S+)", data, re.IGNORECASE | re.MULTILINE
                )
                if match:
                    return match.group(1).decode("ascii", "ignore")
        except TimeoutError:
            return None
        except OSError:
            logger.debug(
                "SSDP search failed from %s for %s", local_ip or "default", target
            )
            return None


def _discover_igd_blocking() -> str | None:
    """SSDP M-SEARCH for an internet gateway; returns its description URL."""
    for local_ip in _local_ipv4_addresses():
        for target in _IGD_SEARCH_TARGETS:
            location = _search_from(local_ip, target)
            if location is not None:
                logger.debug(
                    "Found a gateway at %s via %s", location, local_ip or "default"
                )
                return location
    return None


def _local_ip_towards_blocking(host: str) -> str | None:
    """Which of our addresses the router would reach us on. Connectionless —
    a UDP socket only picks a route, it sends nothing."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect((host, 80))
            local: str = sock.getsockname()[0]
            return local
    except OSError:
        return None


def _find_wan_service(description_xml: str) -> str | None:
    """Control URL of the router's WAN connection service."""
    try:
        root = ET.fromstring(description_xml)
    except ET.ParseError:
        logger.debug("Router description is not valid XML", exc_info=True)
        return None
    namespace = "{urn:schemas-upnp-org:device-1-0}"
    for service in root.iter(f"{namespace}service"):
        service_type = service.findtext(f"{namespace}serviceType")
        control_url = service.findtext(f"{namespace}controlURL")
        if service_type in _WAN_SERVICE_TYPES and control_url:
            return control_url
    return None


def _soap_envelope(service_type: str, action: str, body: str) -> str:
    return (
        '<?xml version="1.0"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
        's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
        f'<s:Body><u:{action} xmlns:u="{service_type}">{body}'
        f"</u:{action}></s:Body></s:Envelope>"
    )


class UpnpClient:
    """One router, discovered once and reused for the mapping's lifetime."""

    def __init__(self) -> None:
        self._control_url: str | None = None
        self._service_type: str | None = None
        self._local_ip: str | None = None

    async def connect(self) -> bool:
        """Find the router and its WAN service. False when there is none."""
        loop = asyncio.get_running_loop()
        location = await loop.run_in_executor(None, _discover_igd_blocking)
        if location is None:
            return False

        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
                response = await client.get(location)
                response.raise_for_status()
                description = response.text[:MAX_DESCRIPTION_BYTES]
        except httpx.HTTPError:
            logger.debug("Could not read router description", exc_info=True)
            return False

        control_url = _find_wan_service(description)
        if control_url is None:
            return False

        self._control_url = urljoin(location, control_url)
        router_host = urlparse(location).hostname
        if router_host is None:
            return False
        self._local_ip = await loop.run_in_executor(
            None, _local_ip_towards_blocking, router_host
        )
        # Which of the two WAN service flavours answered is only known by
        # trying; WANIPConnection is by far the common one.
        self._service_type = _WAN_SERVICE_TYPES[0]
        return self._local_ip is not None

    async def _call(self, action: str, body: str) -> str | None:
        """One SOAP call. Returns the response body, or None on failure."""
        if self._control_url is None or self._service_type is None:
            return None
        for service_type in _WAN_SERVICE_TYPES:
            envelope = _soap_envelope(service_type, action, body)
            headers = {
                "Content-Type": 'text/xml; charset="utf-8"',
                "SOAPAction": f'"{service_type}#{action}"',
            }
            try:
                async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
                    response = await client.post(
                        self._control_url, content=envelope, headers=headers
                    )
            except httpx.HTTPError:
                logger.debug("UPnP %s failed to send", action, exc_info=True)
                return None
            if response.status_code == 200:
                self._service_type = service_type
                return response.text[:MAX_DESCRIPTION_BYTES]
            # A wrong service type answers 500 with a SOAP fault; try the other
            # flavour before giving up, but surface a real refusal.
            if _ONLY_PERMANENT_LEASES in response.text:
                return None
        logger.debug("UPnP %s refused by the router", action)
        return None

    async def external_ip(self) -> str | None:
        body = await self._call("GetExternalIPAddress", "")
        if body is None:
            return None
        match = re.search(r"<NewExternalIPAddress>([^<]*)</NewExternalIPAddress>", body)
        return match.group(1).strip() if match else None

    async def add_port_mapping(self, port: int, lease: int) -> bool:
        if self._local_ip is None:
            return False
        body = (
            "<NewRemoteHost></NewRemoteHost>"
            f"<NewExternalPort>{port}</NewExternalPort>"
            "<NewProtocol>TCP</NewProtocol>"
            f"<NewInternalPort>{port}</NewInternalPort>"
            f"<NewInternalClient>{self._local_ip}</NewInternalClient>"
            "<NewEnabled>1</NewEnabled>"
            f"<NewPortMappingDescription>{MAPPING_DESCRIPTION}"
            "</NewPortMappingDescription>"
            f"<NewLeaseDuration>{lease}</NewLeaseDuration>"
        )
        return await self._call("AddPortMapping", body) is not None

    async def delete_port_mapping(self, port: int) -> bool:
        body = (
            "<NewRemoteHost></NewRemoteHost>"
            f"<NewExternalPort>{port}</NewExternalPort>"
            "<NewProtocol>TCP</NewProtocol>"
        )
        return await self._call("DeletePortMapping", body) is not None


async def open_port(port: int) -> tuple[UpnpMapping, UpnpClient | None]:
    """Try to make `port` reachable from the internet.

    Returns the outcome and, when a mapping was made, the client that owns it
    so the caller can refresh and remove it."""
    client = UpnpClient()
    try:
        if not await client.connect():
            return UpnpMapping(outcome="no_router"), None

        external_ip = await client.external_ip()
        if external_ip is not None and not is_public_address(external_ip):
            # Mapping the port would succeed and still be useless — the address
            # the router owns is not reachable from the internet.
            logger.info(
                "Router's external address %s is not publicly routable (CGNAT "
                "or double NAT); port forwarding cannot help here.",
                external_ip,
            )
            return UpnpMapping(outcome="cgnat", external_ip=external_ip), None

        lease = LEASE_SECONDS
        if not await client.add_port_mapping(port, lease):
            # Some routers only accept permanent mappings; take one and rely on
            # removing it at shutdown.
            lease = 0
            if not await client.add_port_mapping(port, lease):
                return UpnpMapping(outcome="refused", external_ip=external_ip), None

        logger.info("UPnP mapped port %s, external address %s", port, external_ip)
        return (
            UpnpMapping(
                outcome="mapped",
                external_ip=external_ip,
                external_port=port,
                lease_seconds=lease,
            ),
            client,
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.warning("UPnP port mapping failed", exc_info=True)
        return UpnpMapping(outcome="failed"), None
