import time
import subprocess
import argparse
from pathlib import Path
import yaml
import platform
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
    hosts = []
    for h in cfg['hosts']:
        hosts.extend([h['hostname']] * h['slots'])
    cmd.append(",".join(hosts))

    my_path = Path(__file__).parent.absolute()
    cmd.extend([
        cfg['python'], str(my_path / 'distributor.py'), '--cfg', args.cfg
    ])

    print(" ".join(cmd))

    child = subprocess.Popen(cmd)
    child.wait()

if __name__ == '__main__':
    main()