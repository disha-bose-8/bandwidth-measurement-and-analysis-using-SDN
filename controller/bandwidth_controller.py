"""
bandwidth_controller.py
=======================
Custom POX SDN Controller for Bandwidth Measurement and Analysis Project
Author: [Your Name]
Date:   2025

Description:
    This controller implements:
      1. L2 Learning Switch  – learns MAC-to-port mappings and installs
                               explicit OpenFlow flow rules with match-action.
      2. Firewall / Blocking – blocks traffic between specific host pairs
                               (h1 <-> h3 by default) to demonstrate
                               access-control via SDN.
      3. Controller Logging  – prints detailed events for every packet_in,
                               every flow rule installed, and every blocked flow.

Tested with: POX (carp / dart), Mininet 2.3, Open vSwitch

Usage (from POX root directory):
    python pox.py log.level --DEBUG bandwidth_controller
"""

from pox.core import core
from pox.lib.util import dpidToStr
import pox.openflow.libopenflow_01 as of
from pox.lib.addresses import EthAddr
from pox.lib.packet.ethernet import ethernet

log = core.getLogger()

# ---------------------------------------------------------------------------
# FIREWALL RULES
# Define pairs of MAC addresses that should be BLOCKED from communicating.
# These are populated at runtime once we learn the MACs.
# You can also hard-code them if your topology assigns static MACs.
# Format: frozenset({EthAddr("xx:xx:xx:xx:xx:xx"), EthAddr("yy:yy:yy:yy:yy:yy")})
# ---------------------------------------------------------------------------
BLOCKED_PAIRS = set()   # filled dynamically – see register_blocked_pair()

# Hard-coded block: h1 (00:00:00:00:00:01) <-> h3 (00:00:00:00:00:03)
# Mininet assigns MACs sequentially by default: h1=...01, h2=...02, h3=...03
_BLOCK_H1 = EthAddr("00:00:00:00:00:01")
_BLOCK_H3 = EthAddr("00:00:00:00:00:03")
BLOCKED_PAIRS.add(frozenset([_BLOCK_H1, _BLOCK_H3]))


def is_blocked(src_mac, dst_mac):
    """Return True if this src->dst pair is in the firewall block list."""
    return frozenset([src_mac, dst_mac]) in BLOCKED_PAIRS


class BandwidthController(object):
    """
    Per-switch controller instance.
    One BandwidthController object is created for each switch that connects.
    """

    def __init__(self, connection):
        self.connection = connection
        self.dpid = dpidToStr(connection.dpid)

        # MAC -> port mapping table (the "learning" table)
        self.mac_to_port = {}

        # Statistics counters
        self.packet_in_count = 0
        self.flow_install_count = 0
        self.blocked_count = 0

        # Register to receive OpenFlow messages from this switch
        connection.addListeners(self)

        log.info("[Switch %s] Connected – controller ready.", self.dpid)

        # Install a default low-priority drop rule so unmatched traffic
        # does NOT flood the controller indefinitely.
        self._install_table_miss_rule()

    # ------------------------------------------------------------------
    # OpenFlow event handlers
    # ------------------------------------------------------------------

    def _handle_PacketIn(self, event):
        """
        Called every time a packet arrives at the controller
        (i.e., no matching flow rule exists on the switch).
        """
        self.packet_in_count += 1

        packet   = event.parsed          # parsed Ethernet packet
        in_port  = event.port             # ingress port on the switch
        src_mac  = packet.src             # source MAC address
        dst_mac  = packet.dst             # destination MAC address

        log.info(
            "[Switch %s] Packet #%d received | src=%s dst=%s in_port=%d",
            self.dpid, self.packet_in_count, src_mac, dst_mac, in_port
        )

        # 1. Learn the source MAC -> port mapping
        if self.mac_to_port.get(src_mac) != in_port:
            self.mac_to_port[src_mac] = in_port
            log.debug("[Switch %s] Learned MAC %s on port %d", self.dpid, src_mac, in_port)

        # 2. Firewall check – drop and install a block rule if needed
        if is_blocked(src_mac, dst_mac):
            self.blocked_count += 1
            log.warning(
                "[Switch %s] BLOCKED flow: %s -> %s (firewall rule). Total blocked: %d",
                self.dpid, src_mac, dst_mac, self.blocked_count
            )
            self._install_block_rule(src_mac, dst_mac)
            return   # do NOT forward this packet

        # 3. Determine output port
        if dst_mac in self.mac_to_port:
            out_port = self.mac_to_port[dst_mac]
            log.info(
                "[Switch %s] Installing flow rule: %s -> %s on port %d",
                self.dpid, src_mac, dst_mac, out_port
            )
            self._install_flow_rule(src_mac, dst_mac, in_port, out_port, event)
        else:
            # Destination unknown – flood the packet
            log.debug("[Switch %s] Unknown destination %s – flooding.", self.dpid, dst_mac)
            self._flood_packet(event)

    # ------------------------------------------------------------------
    # Flow rule installation helpers
    # ------------------------------------------------------------------

    def _install_table_miss_rule(self):
        """
        Install a lowest-priority rule that sends unmatched packets
        to the controller (standard table-miss behavior).
        Priority 0, no timeouts (permanent).
        """
        msg = of.ofp_flow_mod()
        msg.priority   = 0
        msg.match      = of.ofp_match()   # wildcard match = match everything
        msg.actions.append(of.ofp_action_output(port=of.OFPP_CONTROLLER))
        self.connection.send(msg)
        log.debug("[Switch %s] Table-miss rule installed (priority=0).", self.dpid)

    def _install_flow_rule(self, src_mac, dst_mac, in_port, out_port, event):
        """
        Install a unicast forwarding flow rule:
          Match:  src_mac, dst_mac, in_port
          Action: output to out_port
          Priority: 10 (higher than table-miss)
          Idle timeout: 30 s  (rule removed after 30 s of no matching traffic)
          Hard timeout: 120 s (rule removed after 2 min regardless)
        """
        msg = of.ofp_flow_mod()
        msg.match         = of.ofp_match.from_packet(event.data, in_port)
        msg.priority      = 10
        msg.idle_timeout  = 30
        msg.hard_timeout  = 120
        msg.data          = event.ofp     # send the buffered packet immediately
        msg.actions.append(of.ofp_action_output(port=out_port))

        self.connection.send(msg)
        self.flow_install_count += 1

        log.info(
            "[Switch %s] Flow rule #%d installed | match=(%s->%s, port %d) "
            "action=output:%d | idle_to=30s hard_to=120s priority=10",
            self.dpid, self.flow_install_count,
            src_mac, dst_mac, in_port, out_port
        )

    def _install_block_rule(self, src_mac, dst_mac):
        """
        Install a DROP rule for blocked src->dst MAC pairs.
          Match:  src_mac, dst_mac
          Action: (none = drop)
          Priority: 20 (higher than forwarding rules so it always wins)
          Hard timeout: 0 (permanent – firewall rules don't expire)
        """
        # Block src -> dst
        msg = of.ofp_flow_mod()
        msg.match            = of.ofp_match()
        msg.match.dl_src     = src_mac
        msg.match.dl_dst     = dst_mac
        msg.priority         = 20
        msg.idle_timeout     = 0
        msg.hard_timeout     = 0
        # No actions = DROP
        self.connection.send(msg)

        # Block dst -> src (bidirectional)
        msg2 = of.ofp_flow_mod()
        msg2.match           = of.ofp_match()
        msg2.match.dl_src    = dst_mac
        msg2.match.dl_dst    = src_mac
        msg2.priority        = 20
        msg2.idle_timeout    = 0
        msg2.hard_timeout    = 0
        self.connection.send(msg2)

        log.warning(
            "[Switch %s] DROP rules installed (bidirectional): %s <-> %s | "
            "priority=20 permanent",
            self.dpid, src_mac, dst_mac
        )

    def _flood_packet(self, event):
        """Send an OpenFlow packet-out with FLOOD action (no flow rule installed)."""
        msg = of.ofp_packet_out()
        msg.data    = event.ofp
        msg.actions.append(of.ofp_action_output(port=of.OFPP_FLOOD))
        msg.in_port = event.port
        self.connection.send(msg)


# ---------------------------------------------------------------------------
# Component launch point
# ---------------------------------------------------------------------------

class SDNController(object):
    """
    Top-level controller object registered with the POX core.
    Listens for new switch connections and spawns a BandwidthController
    instance for each one.
    """

    def __init__(self):
        log.info("SDN Bandwidth Controller starting up...")
        core.openflow.addListeners(self)

    def _handle_ConnectionUp(self, event):
        """Fired when a new switch connects to the controller."""
        log.info("Switch %s connected.", dpidToStr(event.dpid))
        BandwidthController(event.connection)

    def _handle_ConnectionDown(self, event):
        """Fired when a switch disconnects."""
        log.info("Switch %s disconnected.", dpidToStr(event.dpid))


def launch():
    """Entry point called by POX when this module is loaded."""
    core.registerNew(SDNController)
    log.info("Bandwidth Controller launched. Firewall: h1<->h3 blocked.")
