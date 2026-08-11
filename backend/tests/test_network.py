from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from loregraph.config import Settings
from loregraph.main import create_app
from loregraph.services.network import NetworkService
from loregraph.services.upnp import UpnpMapping, is_public_address


@pytest.mark.parametrize(
    "ip,public",
    [
        ("93.184.216.34", True),
        # Documentation ranges are not routable either, and Python knows it.
        ("203.0.113.10", False),
        ("8.8.8.8", True),
        # The whole point of the check: a router can report one of these as its
        # "external" address, and no port forwarding here can make it work.
        ("100.64.0.1", False),  # CGNAT
        ("100.127.255.254", False),  # CGNAT, upper end
        ("192.168.0.16", False),  # double NAT
        ("10.1.2.3", False),
        ("172.16.5.4", False),
        ("127.0.0.1", False),
        ("169.254.1.1", False),
        ("not-an-ip", False),
    ],
)
def test_is_public_address(ip: str, public: bool) -> None:
    assert is_public_address(ip) is public


def test_cgnat_boundaries_are_exact() -> None:
    # 100.64.0.0/10 is 100.64.x - 100.127.x; the neighbours are ordinary
    # public addresses and must not be written off as CGNAT.
    assert is_public_address("100.63.255.255") is True
    assert is_public_address("100.128.0.0") is True


def _settings(tmp_path: Path, **extra: Any) -> Settings:
    kwargs: dict[str, Any] = {
        "data_dir": tmp_path,
        "embedding_provider": "disabled",
        "_env_file": None,
        **extra,
    }
    return Settings(**kwargs)


@pytest.mark.asyncio
async def test_local_by_default_never_touches_the_router(tmp_path: Path) -> None:
    service = NetworkService(_settings(tmp_path))
    await service.start()
    assert service.status.reach == "local"
    # No UPnP attempt at all — opening a port is never a side effect.
    assert service.status.upnp is None
    await service.stop()


@pytest.mark.asyncio
async def test_lan_mode_stops_short_of_the_router(tmp_path: Path) -> None:
    service = NetworkService(
        _settings(tmp_path, play_mode_enabled=True, play_host="192.168.0.16")
    )
    await service.start()
    assert service.status.reach == "lan"
    assert service.status.upnp is None
    assert service.status.base_url == "http://192.168.0.16:8000"
    await service.stop()


@pytest.mark.asyncio
async def test_cgnat_keeps_the_lan_address_and_records_why(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_open_port(port: int) -> tuple[UpnpMapping, None]:
        return UpnpMapping(outcome="cgnat", external_ip="100.71.4.9"), None

    monkeypatch.setattr("loregraph.services.network.open_port", fake_open_port)
    service = NetworkService(
        _settings(
            tmp_path,
            play_mode_enabled=True,
            internet_mode_enabled=True,
            play_host="192.168.0.16",
        )
    )
    await service.start()

    # Falls back to the address that still works, and keeps the reason so the
    # UI can say "your provider does not hand out public addresses".
    assert service.status.reach == "lan"
    assert service.status.base_url == "http://192.168.0.16:8000"
    assert service.status.upnp is not None
    assert service.status.upnp.outcome == "cgnat"
    assert service.status.upnp.external_ip == "100.71.4.9"
    await service.stop()


@pytest.mark.asyncio
async def test_no_router_is_reported_not_swallowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_open_port(port: int) -> tuple[UpnpMapping, None]:
        return UpnpMapping(outcome="no_router"), None

    monkeypatch.setattr("loregraph.services.network.open_port", fake_open_port)
    service = NetworkService(
        _settings(tmp_path, play_mode_enabled=True, internet_mode_enabled=True)
    )
    await service.start()
    assert service.status.reach == "lan"
    assert service.status.upnp is not None
    assert service.status.upnp.outcome == "no_router"
    await service.stop()


@pytest.mark.asyncio
async def test_successful_mapping_switches_links_to_the_public_address(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.deleted: list[int] = []

        async def add_port_mapping(self, port: int, lease: int) -> bool:
            return True

        async def delete_port_mapping(self, port: int) -> bool:
            self.deleted.append(port)
            return True

    fake_client = FakeClient()

    async def fake_open_port(port: int) -> tuple[UpnpMapping, FakeClient]:
        return (
            UpnpMapping(
                outcome="mapped",
                external_ip="93.184.216.34",
                external_port=port,
                lease_seconds=0,
            ),
            fake_client,
        )

    monkeypatch.setattr("loregraph.services.network.open_port", fake_open_port)
    service = NetworkService(
        _settings(
            tmp_path,
            play_mode_enabled=True,
            internet_mode_enabled=True,
            play_host="192.168.0.16",
        )
    )
    await service.start()
    assert service.status.reach == "internet"
    assert service.status.base_url == "http://93.184.216.34:8000"

    # Shutting down must take the mapping with it, or the router keeps
    # forwarding a port at a machine that is no longer listening.
    await service.stop()
    assert fake_client.deleted == [8000]


def test_invite_link_uses_the_resolved_address(tmp_path: Path) -> None:
    settings = _settings(tmp_path, play_mode_enabled=True, play_host="192.168.0.16")
    with TestClient(create_app(settings), client=("127.0.0.1", 50000)) as client:
        project_id = client.post("/api/projects", json={"name": "P"}).json()["id"]
        created = client.post(
            f"/api/projects/{project_id}/players", json={"name": "Kael"}
        ).json()
        assert created["play_url"].startswith("http://192.168.0.16:8000/play/")
