from mpi4py import MPI
import numpy as np
import os
import shutil
import sys
from socket import gethostname
import time
import yaml
from argparse import ArgumentParser
from pathlib import Path
import random
import subprocess
import signal
import socket
from subprocess import check_output
import re

from worker import Worker
from master import Master

def main():
    parser = ArgumentParser()
    parser.add_argument('--cfg', type=str, required=True, help="big daddy config file")
    args = parser.parse_args()

    with open(args.cfg) as f:
        cfg = yaml.safe_load(f)

    # print(rank, socket.gethostname())
    rank = MPI.COMM_WORLD.Get_rank()

    if rank == 0:
        m = Master(cfg)
        m.main()
    else:
        w = Worker(cfg)
        w.main()

if __name__ == '__main__':
    main()