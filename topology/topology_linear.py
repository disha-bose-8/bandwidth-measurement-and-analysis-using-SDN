"""
topology_linear.py
==================
Mininet topology: Linear chain of 3 switches, each with 1 host (linear,3 equivalent)

    h1 - [s1] - [s2] - [s3] - h3
                  |
                  h2
                  
          (all switches connect to remote POX controller)

The linear topology introduces multiple hops between h1 and h3,
which increases latency and reduces throughput compared to the
single-switch topology. This difference is measured and analyzed.

Usage:
    sudo python topology_linear.py
"""

from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.topo import LinearTopo
from mininet.log import setLogLevel, info
from mininet.cli import CLI
import time


def run_linear_topology():
    setLogLevel('info')

    info("\n*** Creating Linear Topology (3 switches, 3 hosts)\n")
    topo = LinearTopo(3)

    net = Mininet(
        topo=topo,
        controller=RemoteController('c0', ip='127.0.0.1', port=6633),
        switch=OVSSwitch,
        autoSetMacs=True
    )

    net.start()
    info("*** Network started\n")
    time.sleep(2)

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

    info("\n--- iperf: h1 -> h2 (1 hop apart) ---\n")
    net.iperf((h1, h2), seconds=5)

    info("\n--- iperf: h2 -> h3 (1 hop apart) ---\n")
    net.iperf((h2, h3), seconds=5)

    info("\n--- iperf: h1 -> h3 (BLOCKED by firewall) ---\n")
    result = h1.cmd('iperf -c', h3.IP(), '-t 3 -P 1 2>&1')
    info(result + "\n")

    # ------------------------------------------------------------------
    # TEST SCENARIO 3: Latency (ping)
    # ------------------------------------------------------------------
    info("\n" + "="*60 + "\n")
    info("TEST SCENARIO 3: Latency Measurement (ping)\n")
    info("="*60 + "\n")

    info("\n--- ping h1 -> h2 (10 packets, 1 hop) ---\n")
    info(h1.cmd('ping -c 10', h2.IP()) + "\n")

    info("\n--- ping h1 -> h3 (10 packets – expect no reply, blocked) ---\n")
    info(h1.cmd('ping -c 5 -W 1', h3.IP()) + "\n")

    info("\n--- ping h2 -> h3 (10 packets, 1 hop) ---\n")
    info(h2.cmd('ping -c 10', h3.IP()) + "\n")

    # ------------------------------------------------------------------
    # Flow table dump (all switches)
    # ------------------------------------------------------------------
    info("\n" + "="*60 + "\n")
    info("FLOW TABLE DUMP (all switches)\n")
    info("="*60 + "\n")
    for sw_name in ['s1', 's2', 's3']:
        sw = net.get(sw_name)
        info(f"\n--- {sw_name} ---\n")
        info(sw.cmd(f'ovs-ofctl dump-flows {sw_name}') + "\n")

    info("\n*** Entering CLI – type 'exit' to quit\n")
    CLI(net)

    net.stop()
    info("*** Network stopped\n")


if __name__ == '__main__':
    run_linear_topology()
