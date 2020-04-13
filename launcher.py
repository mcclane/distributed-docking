import time
import subprocess
import argparse
from pathlib import Path
import yaml
import platform
import os
from os import system, makedirs, chdir, path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cfg', '--c', type=str, required=True, help="configuration file containing hosts, etc")

    args = parser.parse_args()
    with open(args.cfg) as f:
        cfg = yaml.safe_load(f)

    cmd = [
        cfg['mpiexec_path'],
    ]
    for a in cfg['mpi_args']:
        cmd.extend(a.split())

    cmd.append('--host')
    reachable_hosts = find_reachable_hosts(cfg['hosts'], cfg['local_workspace'])
    hosts = []
    for h in reachable_hosts:
        hosts.extend([h['hostname']] * h['slots'])
    cmd.append(",".join(hosts))

    my_path = Path(__file__).parent.absolute()
    cmd.extend([
        cfg['python'], str(my_path / 'distributor.py'), '--cfg', args.cfg
    ])

    print("Launching mpi process")
    child = subprocess.Popen(cmd)
    child.wait()

def find_reachable_hosts(possible_hosts, local_workspace):
    reachable_hosts = []
    for h in possible_hosts:
        print("{}...".format(h['hostname']), end='', flush=True)
        if not os.system("ssh {0} touch {1}/asdfgh.txt && ssh {0} rm {1}/asdfgh.txt".format(h['hostname'], local_workspace)):
            print("OK")
            reachable_hosts.append(h)
        else:
            print("UNREACHABLE")
    return reachable_hosts


if __name__ == '__main__':
    main()