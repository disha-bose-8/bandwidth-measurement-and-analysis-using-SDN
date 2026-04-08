"""
topology_single.py
==================
Mininet topology: Single switch with 3 hosts (single,3 equivalent)

           h1
            \
    h2 --- [s1] --- (POX Controller)
            /
           h3

Usage:
    sudo python topology_single.py
"""

from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.topo import SingleSwitchTopo
from mininet.log import setLogLevel, info
from mininet.cli import CLI
import time


def run_single_topology():
    setLogLevel('info')

    info("\n*** Creating Single Switch Topology (1 switch, 3 hosts)\n")
    topo = SingleSwitchTopo(3)

    net = Mininet(
        topo=topo,
        controller=RemoteController('c0', ip='127.0.0.1', port=6633),
        switch=OVSSwitch,
        autoSetMacs=True   # assigns MACs: h1=00:00:00:00:00:01, etc.
    )

    net.start()
    info("*** Network started\n")
    time.sleep(2)  # allow controller to connect

    h1, h2, h3 = net.get('h1', 'h2', 'h3')

    # ------------------------------------------------------------------
    # TEST SCENARIO 1: Connectivity (pingall)
    # ------------------------------------------------------------------
    info("\n" + "="*60 + "\n")
    info("TEST SCENARIO 1: Basic Connectivity (pingall)\n")
    info("="*60 + "\n")
    info("Expected: h1<->h2 SUCCESS, h1<->h3 FAIL (firewall), h2<->h3 SUCCESS\n\n")
    net.pingAll()

    # ------------------------------------------------------------------
    # TEST SCENARIO 2: Bandwidth Measurement with iperf
    # ------------------------------------------------------------------
    info("\n" + "="*60 + "\n")
    info("TEST SCENARIO 2: Bandwidth Measurement (iperf)\n")
    info("="*60 + "\n")

    info("\n--- iperf: h1 -> h2 (ALLOWED) ---\n")
    net.iperf((h1, h2), seconds=5)

    info("\n--- iperf: h2 -> h3 (ALLOWED) ---\n")
    net.iperf((h2, h3), seconds=5)

    info("\n--- iperf: h1 -> h3 (BLOCKED by firewall – expect failure) ---\n")
    # This will fail/timeout because h1<->h3 is blocked by the controller
    result = h1.cmd('iperf -c', h3.IP(), '-t 3 -P 1 2>&1')
    info(result + "\n")

    # ------------------------------------------------------------------
    # TEST SCENARIO 3: Latency (ping)
    # ------------------------------------------------------------------
    info("\n" + "="*60 + "\n")
    info("TEST SCENARIO 3: Latency Measurement (ping)\n")
    info("="*60 + "\n")

    info("\n--- ping h1 -> h2 (10 packets) ---\n")
    info(h1.cmd('ping -c 10', h2.IP()) + "\n")

    info("\n--- ping h2 -> h3 (10 packets) ---\n")
    info(h2.cmd('ping -c 10', h3.IP()) + "\n")

    # ------------------------------------------------------------------
    # Flow table dump
    # ------------------------------------------------------------------
    info("\n" + "="*60 + "\n")
    info("FLOW TABLE DUMP (dpctl dump-flows)\n")
    info("="*60 + "\n")
    s1 = net.get('s1')
    info(s1.cmd('ovs-ofctl dump-flows s1') + "\n")

    info("\n*** Entering CLI – type 'exit' to quit\n")
    CLI(net)

    net.stop()
    info("*** Network stopped\n")


if __name__ == '__main__':
    run_single_topology()
