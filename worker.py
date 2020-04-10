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

from idock import idock

class Worker:
    def __init__(self, cfg):
        self.cfg = cfg
        self.rank = MPI.COMM_WORLD.Get_rank()
    
    def create_workspace(self):
        self.parent_dir = Path(self.cfg['local_workspace']) / 'distributed-docking'
        if not self.parent_dir.exists():
            self.parent_dir.mkdir()
        
        self.local_workspace = self.parent_dir / "worker-{}".format(self.rank)
        if self.local_workspace.exists():
            os.system("rm -rf {0} && mkdir {0}".format(str(self.local_workspace)))
        else:
            self.local_workspace.mkdir()
        
        self.ligand_dir = self.local_workspace / "ligands"
        if not self.ligand_dir.exists():
            self.ligand_dir.mkdir()
        
        self.results_dir = self.local_workspace / "results"
        if not self.results_dir.exists():
            self.results_dir.mkdir()

    def retrieve_config(self):
        # copy over config folder (which has executable, config file, receptor)
        self.config_dir = self.local_workspace / "config"
        return os.system("rsync -a {} {}".format(self.cfg['config_folder_path'], str(self.config_dir)))

    def retrieve_ligands(self, ligands, path):
        ligands_file = str(self.local_workspace / "ligands.txt")
        with open(ligands_file, 'w') as f:
            f.write(ligands)
        return os.system("rsync -az --files-from={} {} {}".format(ligands_file, path, str(self.ligand_dir)))
    
    def main(self):
        hostname = gethostname()

        self.create_workspace()
        # distributed-docking/
        #   worker-{rank}/
        #       ligands/
        #       results/

        self.retrieve_config()

        MPI.COMM_WORLD.Barrier()
        MPI.COMM_WORLD.send({'ready'}, dest=0)

        while True:
            received = MPI.COMM_WORLD.recv(source=0)
            if 'ligands' in received:
                # clear the ligands directory
                os.system("rm -rf {0} && mkdir {0}".format(self.ligand_dir))

                # print("worker {} received {} ligands".format(rank, len(received['ligands'])))
                self.retrieve_ligands(received['ligands'], received['path'])

                if self.cfg['docking'] == 'idock':
                    docker = idock(self.config_dir / "idock", 
                                   self.ligand_dir, 
                                   config=self.config_dir / "idock.conf",
                                   output_path=self.results_dir,
                                   receptor=self.config_dir / self.cfg['receptor'],
                                   rank=self.rank)
                    docker.run_job()
                
                # sync the results back to the master node
                os.system("rsync -azv --remove-source-files --exclude=log.csv {}/ {}".format(self.results_dir, received['send_back_to']))
                # clean up
                os.system("rm -rf {0} && mkdir {0}".format(self.ligand_dir))

                MPI.COMM_WORLD.send({'ready'}, dest=0)
            else:
                break
