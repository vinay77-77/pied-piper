"""WebRTC RTCPeerConnection wrapper, STUN/ICE configuration, and connection handshake."""

import asyncio
import logging
import os
import re
import socket
from typing import Any, Callable, Dict, List, Optional

import aioice.ice
import ifaddr
from aiortc import (
    RTCConfiguration,
    RTCIceCandidate,
    RTCIceServer,
    RTCPeerConnection,
    RTCSessionDescription,
)
from aiortc.sdp import candidate_from_sdp, candidate_to_sdp

from backend.config import Settings, get_settings
from backend.signaling.client import SignalingClient, SignalingError
from backend.transport.data_channels import DataChannelManager

logger = logging.getLogger(__name__)

# Virtual / internal interface prefixes and subnets that should not be used as ICE host candidates
VIRTUAL_IFACE_PATTERNS = ("vboxnet", "virtualbox", "docker", "br-", "virbr", "vmnet", "veth")
VIRTUAL_IP_PREFIXES = ("192.168.56.", "169.254.")


def filter_host_addresses(use_ipv4: bool, use_ipv6: bool) -> List[str]:
    """Return local IP addresses excluding virtual host-only and container bridge adapters.

    Prevents gathering unroutable host-only interfaces (e.g. VirtualBox, Docker host bridges)
    that incur 5-second STUN timeouts and cannot route across networks.
    Falls back to unfiltered list if all addresses would otherwise be excluded.
    """
    all_addresses: List[str] = []
    filtered_addresses: List[str] = []

    for adapter in ifaddr.get_adapters():
        adapter_name = adapter.name.lower()
        is_virtual_adapter = any(pattern in adapter_name for pattern in VIRTUAL_IFACE_PATTERNS)

        for ip in adapter.ips:
            if isinstance(ip.ip, str) and use_ipv4 and ip.ip != "127.0.0.1":
                all_addresses.append(ip.ip)
                is_virtual_ip = any(ip.ip.startswith(prefix) for prefix in VIRTUAL_IP_PREFIXES)
                if not is_virtual_adapter and not is_virtual_ip:
                    filtered_addresses.append(ip.ip)
            elif use_ipv6 and ip.ip[0] != "::1" and ip.ip[2] == 0:
                all_addresses.append(ip.ip[0])
                if not is_virtual_adapter:
                    filtered_addresses.append(ip.ip[0])

    return filtered_addresses if filtered_addresses else all_addresses


# Patch aioice get_host_addresses to use the clean host address filter
aioice.ice.get_host_addresses = filter_host_addresses


# -----------------------------------------------------------------------------
# Multi-endpoint TURN Gathering Support for aiortc & aioice
# -----------------------------------------------------------------------------
import aioice.turn
from aiortc import rtcicetransport

orig_connection_kwargs = rtcicetransport.connection_kwargs


def patched_connection_kwargs(servers: List[RTCIceServer]) -> Dict[str, Any]:
    """Parse all TURN server URIs into kwargs['turn_servers'] so all transports are gathered."""
    kwargs = orig_connection_kwargs(servers)
    all_turns: List[tuple] = []
    for server in servers:
        uris = server.urls if isinstance(server.urls, list) else [server.urls]
        for uri in uris:
            try:
                parsed = rtcicetransport.parse_stun_turn_uri(uri)
                if parsed["scheme"] in ["turn", "turns"]:
                    ssl_flag = (parsed["scheme"] == "turns")
                    transport = parsed["transport"]
                    all_turns.append(
                        ((parsed["host"], parsed["port"]), server.username, server.credential, ssl_flag, transport)
                    )
            except Exception:
                pass
    if all_turns:
        kwargs["turn_servers"] = all_turns
    return kwargs


rtcicetransport.connection_kwargs = patched_connection_kwargs

orig_connection_init = aioice.ice.Connection.__init__


def patched_connection_init(self, *args, turn_servers=None, **kwargs):
    orig_connection_init(self, *args, **kwargs)
    self.turn_servers = turn_servers or []
    if not self.turn_servers and self.turn_server:
        self.turn_servers = [(self.turn_server, self.turn_username, self.turn_password, self.turn_ssl, self.turn_transport)]


aioice.ice.Connection.__init__ = patched_connection_init

orig_get_component_candidates = aioice.ice.Connection.get_component_candidates


async def patched_get_component_candidates(self, component: int, addresses: List[str], timeout: int = 5) -> List[Any]:
    turn_servers = getattr(self, "turn_servers", [])
    if not turn_servers:
        return await orig_get_component_candidates(self, component, addresses, timeout=timeout)

    candidates = []
    loop = asyncio.get_event_loop()

    host_protocols = []
    for address in addresses:
        try:
            transport, protocol = await loop.create_datagram_endpoint(
                lambda: aioice.ice.StunProtocol(self), local_addr=(address, 0)
            )
            sock = transport.get_extra_info("socket")
            if sock is not None:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, aioice.turn.UDP_SOCKET_BUFFER_SIZE)
        except OSError:
            continue
        host_protocols.append(protocol)

        candidate_address = protocol.transport.get_extra_info("sockname")
        protocol.local_candidate = aioice.ice.Candidate(
            foundation=aioice.ice.candidate_foundation("host", "udp", candidate_address[0]),
            component=component,
            transport="udp",
            priority=aioice.ice.candidate_priority(component, "host"),
            host=candidate_address[0],
            port=candidate_address[1],
            type="host",
        )
        if self._transport_policy == aioice.ice.TransportPolicy.ALL:
            candidates.append(protocol.local_candidate)
    self._protocols += host_protocols

    tasks = []
    if self.stun_server:
        for protocol in host_protocols:
            if aioice.ice.ipaddress.ip_address(protocol.local_candidate.host).version == 4:
                tasks.append(
                    asyncio.create_task(
                        aioice.ice.server_reflexive_candidate(protocol, self.stun_server)
                    )
                )

    for srv, user, pwd, ssl_flag, trans in turn_servers:
        tasks.append(
            asyncio.create_task(
                aioice.ice.relayed_candidate(
                    component=component,
                    protocol_factory=lambda: aioice.ice.StunProtocol(self),
                    turn_server=srv,
                    turn_username=user,
                    turn_password=pwd,
                    turn_ssl=ssl_flag,
                    turn_transport=trans,
                )
            )
        )

    if len(tasks):
        done, pending = await asyncio.wait(tasks, timeout=timeout)
        for task in done:
            if task.exception() is None:
                candidate, protocol = task.result()
                candidates.append(candidate)
                if protocol is not None:
                    self._protocols.append(protocol)
        for task in pending:
            task.cancel()

    return candidates


aioice.ice.Connection.get_component_candidates = patched_get_component_candidates


STUN_URL_REGEX = re.compile(r"^stun:(?P<host>[^:]+)(:(?P<port>[0-9]+))?$")


def probe_single_stun(host: str, port: int, timeout: float = 0.35) -> bool:
    """Send a lightweight 20-byte RFC 5389 STUN Binding Request to verify server responsiveness."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    tx_id = os.urandom(12)
    req = b"\x00\x01\x00\x00\x21\x12\xa4\x42" + tx_id
    try:
        sock.sendto(req, (host, port))
        data, _ = sock.recvfrom(512)
        return len(data) >= 20 and data[:2] == b"\x01\x01"
    except Exception:
        return False
    finally:
        sock.close()


def prioritize_stun_servers(stun_urls: List[str], timeout: float = 0.35) -> List[str]:
    """Test STUN URLs and order the first responsive server at index 0.

    Because aioice only uses the first STUN server in the RTCConfiguration list,
    this ensures an accessible STUN endpoint is selected even if the primary URL
    (or port 19302 vs 3478) is blocked by local firewalls.
    """
    if len(stun_urls) <= 1:
        return list(stun_urls)

    for url in stun_urls:
        match = STUN_URL_REGEX.match(url.strip())
        if not match:
            continue
        host = match.group("host")
        port = int(match.group("port")) if match.group("port") else 3478
        if probe_single_stun(host, port, timeout=timeout):
            logger.debug("Prioritizing responsive STUN server: %s", url)
            return [url] + [u for u in stun_urls if u != url]

    return list(stun_urls)


class PeerConnectionError(Exception):
    """Exception raised when a WebRTC transport error occurs."""
    pass


class PeerConnectionWrapper:
    """Wraps aiortc RTCPeerConnection and DataChannels, managing STUN, SDP, and ICE."""

    def __init__(self, settings: Optional[Settings] = None, role: str = "send") -> None:
        self.settings: Settings = settings if settings is not None else get_settings()
        self.role: str = role

        # Build STUN/TURN server configuration
        ice_servers: List[RTCIceServer] = []
        ordered_stun = prioritize_stun_servers(self.settings.stun_urls_list)
        for stun_url in ordered_stun:
            ice_servers.append(RTCIceServer(urls=stun_url))

        turn_urls = self.settings.turn_urls_list
        if turn_urls and self.settings.turn_username.strip() and self.settings.turn_credential.strip():
            ice_servers.append(
                RTCIceServer(
                    urls=turn_urls if len(turn_urls) > 1 else turn_urls[0],
                    username=self.settings.turn_username.strip(),
                    credential=self.settings.turn_credential.strip(),
                )
            )

        self.configuration = RTCConfiguration(iceServers=ice_servers)
        self.pc = RTCPeerConnection(configuration=self.configuration)

        self.channels = DataChannelManager()
        self._connected_event = asyncio.Event()
        self._failed_event = asyncio.Event()
        self._pending_candidates: List[Dict[str, Any]] = []
        self._logged_active_pair: bool = False

        # Setup DataChannels based on role
        if self.role == "send":
            self.channels.setup_offerer_channels(self.pc)
        else:
            self.channels.setup_answerer_channels(self.pc)

        # Attach connection state listeners for observability
        self._setup_listeners()

    def _setup_listeners(self) -> None:
        """Attach state change handlers to RTCPeerConnection."""
        @self.pc.on("icecandidate")
        def on_ice_candidate(candidate: Optional[RTCIceCandidate]) -> None:
            if candidate:
                logger.info(
                    "Discovered local ICE candidate: type=%s, protocol=%s, ip=%s, port=%s",
                    getattr(candidate, "type", "unknown"),
                    getattr(candidate, "protocol", "unknown"),
                    getattr(candidate, "ip", "unknown"),
                    getattr(candidate, "port", "unknown"),
                )

        @self.pc.on("icegatheringstatechange")
        def on_ice_gathering_state_change() -> None:
            state = self.pc.iceGatheringState
            logger.info("RTCPeerConnection iceGatheringState -> %s", state)

        @self.pc.on("connectionstatechange")
        def on_connection_state_change() -> None:
            state = self.pc.connectionState
            logger.info("RTCPeerConnection connectionState -> %s", state)
            if state in ("connected", "completed"):
                self._connected_event.set()
                self._log_active_candidate_pair()
            elif state in ("failed", "closed"):
                self._failed_event.set()

        @self.pc.on("iceconnectionstatechange")
        def on_ice_state_change() -> None:
            state = self.pc.iceConnectionState
            logger.info("RTCPeerConnection iceConnectionState -> %s", state)
            if state in ("connected", "completed"):
                self._connected_event.set()
                self._log_active_candidate_pair()
            elif state == "failed":
                self._failed_event.set()

    def _log_active_candidate_pair(self) -> None:
        """Identify and log active/selected ICE candidate pair and connection mode."""
        if self._logged_active_pair:
            return
        try:
            if self.pc.sctp and self.pc.sctp.transport:
                dtls_transport = self.pc.sctp.transport
                ice_transport = getattr(dtls_transport, "transport", None)
                connection = getattr(ice_transport, "_connection", None)
                nominated = getattr(connection, "_nominated", None)
                if nominated:
                    pair = nominated.get(1) or (list(nominated.values())[0] if nominated else None)
                    if pair:
                        local_cand = getattr(pair, "local_candidate", None)
                        remote_cand = getattr(pair, "remote_candidate", None)
                        local_type = getattr(local_cand, "type", "unknown")
                        remote_type = getattr(remote_cand, "type", "unknown")

                        if local_type == "relay" or remote_type == "relay":
                            conn_mode = "TURN relay"
                        elif local_type in ("srflx", "prflx") or remote_type in ("srflx", "prflx"):
                            conn_mode = "STUN server-reflexive (srflx)"
                        elif local_type == "host" and remote_type == "host":
                            conn_mode = "direct/host"
                        else:
                            conn_mode = f"{local_type} <-> {remote_type}"

                        local_host = getattr(local_cand, "host", "unknown")
                        local_port = getattr(local_cand, "port", "unknown")
                        remote_host = getattr(remote_cand, "host", "unknown")
                        remote_port = getattr(remote_cand, "port", "unknown")

                        self._logged_active_pair = True
                        logger.info(
                            "Selected ICE candidate pair: %s (%s candidate [%s:%s] <-> %s candidate [%s:%s])",
                            conn_mode,
                            local_type,
                            local_host,
                            local_port,
                            remote_type,
                            remote_host,
                            remote_port,
                        )
                        return
            logger.info("Active ICE candidate pair detail not available from transport.")
        except Exception as exc:
            logger.debug("Error retrieving active ICE candidate pair: %s", exc)

    @property
    def connection_state(self) -> str:
        """Current WebRTC connection state."""
        return self.pc.connectionState

    @property
    def ice_connection_state(self) -> str:
        """Current ICE connection state."""
        return self.pc.iceConnectionState

    @property
    def is_connected(self) -> bool:
        """Check if WebRTC or ICE state is connected/completed."""
        return (
            self.pc.connectionState in ("connected", "completed")
            or self.pc.iceConnectionState in ("connected", "completed")
        )

    @property
    def connection_mode(self) -> str:
        """Return the active connection mode: 'P2P (LAN)', 'P2P (STUN)', 'Relay (TURN)', or 'P2P'."""
        try:
            if self.pc.sctp and self.pc.sctp.transport:
                dtls_transport = self.pc.sctp.transport
                ice_transport = getattr(dtls_transport, "transport", None)
                connection = getattr(ice_transport, "_connection", None)
                nominated = getattr(connection, "_nominated", None)
                if nominated:
                    pair = nominated.get(1) or (list(nominated.values())[0] if nominated else None)
                    if pair:
                        local_cand = getattr(pair, "local_candidate", None)
                        remote_cand = getattr(pair, "remote_candidate", None)
                        local_type = getattr(local_cand, "type", "unknown")
                        remote_type = getattr(remote_cand, "type", "unknown")

                        if local_type == "relay" or remote_type == "relay":
                            return "Relay (TURN)"
                        elif local_type in ("srflx", "prflx") or remote_type in ("srflx", "prflx"):
                            return "P2P (STUN)"
                        elif local_type == "host" and remote_type == "host":
                            return "P2P (LAN)"
        except Exception:
            pass
        return "P2P"

    async def create_offer(self) -> Dict[str, Any]:
        """Create SDP offer, set local description, and return offer signal dictionary."""
        offer = await self.pc.createOffer()
        await self.pc.setLocalDescription(offer)
        logger.info("SDP offer created and set as local description")
        return {"type": "offer", "sdp": self.pc.localDescription.sdp}

    async def handle_offer(self, offer_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming SDP offer, create answer, set descriptions, and return answer signal dictionary."""
        offer_sdp = offer_data.get("sdp")
        if not offer_sdp:
            raise PeerConnectionError("Missing SDP in offer payload")

        desc = RTCSessionDescription(sdp=offer_sdp, type="offer")
        await self.pc.setRemoteDescription(desc)
        logger.info("Remote SDP offer set successfully")

        # Flush any queued ICE candidates received before remote description
        await self._flush_pending_candidates()

        answer = await self.pc.createAnswer()
        await self.pc.setLocalDescription(answer)
        logger.info("SDP answer created and set as local description")
        return {"type": "answer", "sdp": self.pc.localDescription.sdp}

    async def handle_answer(self, answer_data: Dict[str, Any]) -> None:
        """Handle incoming SDP answer and set remote description."""
        answer_sdp = answer_data.get("sdp")
        if not answer_sdp:
            raise PeerConnectionError("Missing SDP in answer payload")

        desc = RTCSessionDescription(sdp=answer_sdp, type="answer")
        await self.pc.setRemoteDescription(desc)
        logger.info("Remote SDP answer set successfully")

        # Flush any queued ICE candidates
        await self._flush_pending_candidates()

    async def handle_candidate(self, candidate_data: Dict[str, Any]) -> None:
        """Handle incoming ICE candidate payload, applying or queueing if remote description not yet set."""
        if self.pc.remoteDescription is None:
            logger.debug("Queueing ICE candidate until remote description is set")
            self._pending_candidates.append(candidate_data)
            return
        await self._apply_candidate(candidate_data)

    async def _apply_candidate(self, candidate_data: Dict[str, Any]) -> None:
        """Parse and add a single ICE candidate to the RTCPeerConnection."""
        sdp_str = candidate_data.get("candidate")
        if not sdp_str:
            await self.pc.addIceCandidate(None)
            return

        try:
            cand = candidate_from_sdp(sdp_str)
            cand.sdpMid = candidate_data.get("sdpMid")
            cand.sdpMLineIndex = candidate_data.get("sdpMLineIndex")
            logger.info(
                "Discovered remote ICE candidate: type=%s, protocol=%s, ip=%s, port=%s",
                getattr(cand, "type", "unknown"),
                getattr(cand, "protocol", "unknown"),
                getattr(cand, "ip", "unknown"),
                getattr(cand, "port", "unknown"),
            )
            await self.pc.addIceCandidate(cand)
            logger.debug("Applied ICE candidate: %s", cand)
        except Exception as exc:
            logger.warning("Failed to apply ICE candidate: %s", exc)

    async def _flush_pending_candidates(self) -> None:
        """Apply all pending ICE candidates once remote description is set."""
        if not self._pending_candidates:
            return
        logger.info("Flushing %d pending ICE candidate(s)", len(self._pending_candidates))
        for cand_data in self._pending_candidates:
            await self._apply_candidate(cand_data)
        self._pending_candidates.clear()

    def _diagnose_ice_failure(self) -> str:
        """Inspect local and remote SDP to diagnose why ICE failed to connect."""
        try:
            local_desc = self.pc.localDescription
            local_sdp = local_desc.sdp if local_desc else ""
        except Exception:
            local_sdp = ""

        try:
            remote_desc = self.pc.remoteDescription
            remote_sdp = remote_desc.sdp if remote_desc else ""
        except Exception:
            remote_sdp = ""

        local_cands: List[str] = []
        for line in local_sdp.splitlines():
            if line.startswith("a=candidate:"):
                try:
                    c = candidate_from_sdp(line[12:])
                    local_cands.append(f"{c.type}({c.ip}:{c.port})")
                except Exception:
                    pass

        remote_cands: List[str] = []
        for line in remote_sdp.splitlines():
            if line.startswith("a=candidate:"):
                try:
                    c = candidate_from_sdp(line[12:])
                    remote_cands.append(f"{c.type}({c.ip}:{c.port})")
                except Exception:
                    pass

        has_local_srflx = any("srflx" in c for c in local_cands)
        has_remote_srflx = any("srflx" in c for c in remote_cands)
        has_local_relay = any("relay" in c for c in local_cands)
        has_remote_relay = any("relay" in c for c in remote_cands)

        details = f"[Local candidates: {', '.join(local_cands) or 'none'} | Remote candidates: {', '.join(remote_cands) or 'none'}]"

        if has_local_relay or has_remote_relay:
            return f"{details} TURN relay candidate was present, but relay connection check failed. Verify TURN credentials and connectivity."

        if has_local_srflx and has_remote_srflx:
            return (
                f"{details} Both peers gathered STUN public candidates, but direct P2P checks failed. "
                "This indicates Symmetric NAT, Carrier-Grade NAT (CGNAT), or firewall UDP blocking between the networks. "
                "A TURN relay server is required for this network environment (configure TURN_URL in .env)."
            )

        if not has_local_srflx and not has_remote_srflx:
            return (
                f"{details} Neither peer gathered public (srflx) candidates. "
                "Direct connection across different networks is impossible without public or relay candidates. "
                "Check STUN server configuration or ensure peers are on the same local network."
            )

        if not has_remote_srflx:
            return (
                f"{details} Remote peer did not gather any public (srflx) candidates (only private host candidates). "
                "The remote peer's network may be blocking STUN UDP queries. A TURN relay server is required."
            )

        if not has_local_srflx:
            return (
                f"{details} Local peer did not gather any public (srflx) candidates. "
                "Local network may be blocking STUN UDP queries. A TURN relay server is required."
            )

        return details

    async def wait_connected(self, timeout: float = 30.0) -> None:
        """Wait until connection reaches 'connected' or 'completed' state."""
        if self.is_connected:
            return

        done, pending = await asyncio.wait(
            [
                asyncio.create_task(self._connected_event.wait()),
                asyncio.create_task(self._failed_event.wait()),
            ],
            timeout=timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()

        if not done or self._failed_event.is_set():
            diag = self._diagnose_ice_failure()
            state_msg = f"state: {self.pc.connectionState}, iceState: {self.pc.iceConnectionState}"
            if not done:
                logger.error("WebRTC connection timed out after %.1fs (%s). %s", timeout, state_msg, diag)
                raise PeerConnectionError(f"WebRTC connection timed out after {timeout}s ({state_msg}). {diag}")
            else:
                logger.error("WebRTC connection failed (%s). %s", state_msg, diag)
                raise PeerConnectionError(f"WebRTC connection failed ({state_msg}). {diag}")

    async def wait_channels_open(self, timeout: float = 15.0) -> None:
        """Wait until both control and data channels are open."""
        await self.channels.wait_channels_open(timeout=timeout)

    async def close(self) -> None:
        """Close DataChannels and RTCPeerConnection cleanly."""
        self.channels.close()
        await self.pc.close()
        logger.info("PeerConnectionWrapper closed")


async def establish_webrtc_connection(
    role: str,
    signaling_client: SignalingClient,
    settings: Optional[Settings] = None,
    timeout: float = 30.0,
) -> PeerConnectionWrapper:
    """Coordinate full WebRTC SDP offer/answer and ICE exchange through signaling client.

    Returns the established PeerConnectionWrapper with open DataChannels.
    """
    wrapper = PeerConnectionWrapper(settings=settings, role=role)

    # Relay local ICE candidate events to peer via signaling
    @wrapper.pc.on("icecandidate")
    async def on_local_candidate(candidate: Optional[RTCIceCandidate]) -> None:
        if candidate is not None:
            cand_payload = {
                "type": "candidate",
                "candidate": candidate_to_sdp(candidate),
                "sdpMid": candidate.sdpMid,
                "sdpMLineIndex": candidate.sdpMLineIndex,
            }
            try:
                await signaling_client.send_signal(cand_payload)
            except Exception as exc:
                logger.warning("Failed to send local ICE candidate: %s", exc)

    async def signaling_signal_loop() -> None:
        """Process incoming signaling signals for SDP and ICE exchange."""
        async for msg in signaling_client.messages():
            if msg.get("type") != "signal":
                continue
            payload = msg.get("payload", {})
            signal_type = payload.get("type")

            if signal_type == "offer" and role == "receive":
                answer_signal = await wrapper.handle_offer(payload)
                await signaling_client.send_signal(answer_signal)
            elif signal_type == "answer" and role == "send":
                await wrapper.handle_answer(payload)
            elif signal_type == "candidate":
                await wrapper.handle_candidate(payload)

            if wrapper.is_connected:
                break

    signal_task = asyncio.create_task(signaling_signal_loop())

    try:
        if role == "send":
            offer_signal = await wrapper.create_offer()
            await signaling_client.send_signal(offer_signal)

        # Wait until connectionState or iceConnectionState reaches connected
        await wrapper.wait_connected(timeout=timeout)
        logger.info("WebRTC connection established. Waiting for DataChannels to open...")

        # Await DataChannels open
        await wrapper.wait_channels_open(timeout=timeout)
        logger.info("DataChannels open. Reporting connected to signaling server...")
        await signaling_client.report_connected()
        return wrapper

    except Exception as exc:
        await wrapper.close()
        raise PeerConnectionError(f"WebRTC establishment failed: {exc}") from exc
    finally:
        if not signal_task.done():
            signal_task.cancel()
            try:
                await signal_task
            except asyncio.CancelledError:
                pass
