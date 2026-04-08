"""
validate.py
===========
Automated validation and regression test suite for the SDN project.

Runs both topologies and checks:
  - h1 can ping h2        (MUST PASS)
  - h2 can ping h3        (MUST PASS)
  - h1 CANNOT ping h3     (MUST FAIL – firewall)
  - iperf h1->h2 > 1 Gbps (MUST PASS)
  - iperf h2->h3 > 1 Gbps (MUST PASS)

Prints a PASS/FAIL summary for each check.

Usage:
    sudo python tests/validate.py
"""

from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.topo import SingleSwitchTopo, LinearTopo
from mininet.log import setLogLevel
import time
import re


# ANSI colours for terminal output
GREEN = "\033[92m"
RED   = "\033[91m"
RESET = "\033[0m"
BOLD  = "\033[1m"


def passed(msg):
    print(f"  {GREEN}[PASS]{RESET} {msg}")


def failed(msg):
    print(f"  {RED}[FAIL]{RESET} {msg}")


def run_checks(net, topo_name):
    """Run all validation checks on a live Mininet network."""
    print(f"\n{BOLD}{'='*55}{RESET}")
    print(f"{BOLD}  Validation: {topo_name}{RESET}")
    print(f"{BOLD}{'='*55}{RESET}")

    h1, h2, h3 = net.get('h1', 'h2', 'h3')
    results = []

    # ------------------------------------------------------------------
    # Check 1: h1 <-> h2 connectivity (should be allowed)
    # ------------------------------------------------------------------
    loss = net.ping([h1, h2], timeout=2)
    if loss == 0.0:
        passed("h1 <-> h2 connectivity: ALLOWED (0% packet loss)")
        results.append(True)
    else:
        failed(f"h1 <-> h2 connectivity: expected 0% loss, got {loss}%")
        results.append(False)

    # ------------------------------------------------------------------
    # Check 2: h2 <-> h3 connectivity (should be allowed)
    # ------------------------------------------------------------------
    loss = net.ping([h2, h3], timeout=2)
    if loss == 0.0:
        passed("h2 <-> h3 connectivity: ALLOWED (0% packet loss)")
        results.append(True)
    else:
        failed(f"h2 <-> h3 connectivity: expected 0% loss, got {loss}%")
        results.append(False)

    # ------------------------------------------------------------------
    # Check 3: h1 -> h3 BLOCKED by firewall (should NOT reach)
    # ------------------------------------------------------------------
    result = h1.cmd('ping -c 3 -W 1 ' + h3.IP())
    # If blocked, 100% packet loss
    if '3 received' in result or '2 received' in result or '1 received' in result:
        failed("h1 -> h3 firewall: packets reached h3 (firewall NOT working!)")
        results.append(False)
    else:
        passed("h1 -> h3 firewall: traffic BLOCKED (100% packet loss as expected)")
        results.append(True)

    # ------------------------------------------------------------------
    # Check 4: iperf h1 -> h2 throughput > 1 Gbps
    # ------------------------------------------------------------------
    h3.cmd('iperf -s -D')   # start iperf server on h2 (using h3 var for clarity)
    h2.cmd('iperf -s -D')
    time.sleep(0.5)
    iperf_out = h1.cmd('iperf -c ' + h2.IP() + ' -t 5 -f g')
    h2.cmd('kill %iperf 2>/dev/null; pkill iperf 2>/dev/null')
    # Parse Gbits/sec value
    match = re.search(r'([\d.]+)\s+Gbits/sec', iperf_out)
    if match:
        gbps = float(match.group(1))
        if gbps > 1.0:
            passed(f"iperf h1->h2 throughput: {gbps:.1f} Gbps (> 1 Gbps threshold)")
            results.append(True)
        else:
            failed(f"iperf h1->h2 throughput: {gbps:.1f} Gbps (below 1 Gbps threshold)")
            results.append(False)
    else:
        failed("iperf h1->h2: could not parse throughput output")
        print(f"    Raw output: {iperf_out[:200]}")
        results.append(False)

    # ------------------------------------------------------------------
    # Check 5: iperf h2 -> h3 throughput > 1 Gbps
    # ------------------------------------------------------------------
    h3.cmd('iperf -s -D')
    time.sleep(0.5)
    iperf_out = h2.cmd('iperf -c ' + h3.IP() + ' -t 5 -f g')
    h3.cmd('kill %iperf 2>/dev/null; pkill iperf 2>/dev/null')
    match = re.search(r'([\d.]+)\s+Gbits/sec', iperf_out)
    if match:
        gbps = float(match.group(1))
        if gbps > 1.0:
            passed(f"iperf h2->h3 throughput: {gbps:.1f} Gbps (> 1 Gbps threshold)")
            results.append(True)
        else:
            failed(f"iperf h2->h3 throughput: {gbps:.1f} Gbps (below 1 Gbps threshold)")
            results.append(False)
    else:
        failed("iperf h2->h3: could not parse throughput output")
        results.append(False)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    total  = len(results)
    passed_n = sum(results)
    print(f"\n  {BOLD}Result: {passed_n}/{total} checks passed{RESET}")
    return passed_n, total


def main():
    setLogLevel('warning')   # suppress Mininet noise during validation

    grand_pass = 0
    grand_total = 0

    for topo_cls, name in [(SingleSwitchTopo, "Single Switch (single,3)"),
                           (LinearTopo,       "Linear Topology  (linear,3)")]:
        topo = topo_cls(3)
        net = Mininet(
            topo=topo,
            controller=RemoteController('c0', ip='127.0.0.1', port=6633),
            switch=OVSSwitch,
            autoSetMacs=True
        )
        net.start()
        time.sleep(2)

        p, t = run_checks(net, name)
        grand_pass  += p
        grand_total += t

        net.stop()
        time.sleep(1)

    print(f"\n{BOLD}{'='*55}")
    print(f"  OVERALL: {grand_pass}/{grand_total} checks passed")
    print(f"{'='*55}{RESET}\n")


if __name__ == '__main__':
    main()
