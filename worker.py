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
        self.hostname = socket.gethostname()
    
    def create_workspace(self):
        self.parent_dir = Path(self.cfg['local_workspace']) / 'distributed-docking'
        if not self.parent_dir.exists():
            try:
                self.parent_dir.mkdir()
            except FileExistsError:
                pass
            except PermissionError:
                print("permission error on", self.hostname)
                raise
        
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
        for i in range(10):
            if os.system("rsync -a {} {}".format(self.cfg['config_folder_path'], str(self.config_dir))):
                time.sleep(1)
            else:
                return
        raise Exception("Couldn't retrieve config on {}".format(self.hostname))

    def retrieve_ligands(self, ligands, path):
        ligands_file = str(self.local_workspace / "ligands.txt")
        with open(ligands_file, 'w') as f:
            f.write(ligands)
        return os.system("rsync -az --files-from={} {} {}".format(ligands_file, path, str(self.ligand_dir)))
    
    def main(self):
        self.create_workspace()
        os.system("rm -rf {0} && mkdir {0}".format(self.ligand_dir))
        os.system("rm -rf {0} && mkdir {0}".format(self.results_dir))
        # distributed-docking/
        #   worker-{rank}/
        #       ligands/
        #       results/

        MPI.COMM_WORLD.Barrier()

        request_work = {
            'ready': '',
            'ligand_dir': "{}:{}".format(self.hostname, self.ligand_dir),
            'results_dir': "{}:{}".format(self.hostname, self.results_dir),
            'finished_chunk': False
        }

        have_config = False

        while True:
            MPI.COMM_WORLD.send(request_work, dest=0)
            received = MPI.COMM_WORLD.recv(source=0)
            if 'chunk_sent' in received:
                # print("worker {} received {} ligands".format(rank, len(received['ligands'])))
                # if self.retrieve_ligands(received['ligands'], received['path']):
                #     print("rsync error on", self.hostname)
                #     raise Exception("Couldn't rsync received ligands on {}".format(self.hostname))

                if not have_config:
                    self.retrieve_config()
                    have_config = True

                if self.cfg['docking'] == 'idock':
                    docker = idock(self.config_dir / "idock", 
                                   self.ligand_dir, 
                                   config=self.config_dir / "idock.conf",
                                   output_path=self.results_dir,
                                   receptor=self.config_dir / self.cfg['receptor'],
                                   rank=self.rank)
                    docker.run_job()
                

                # sync the results back to the master node
                # for i in range(10):
                #     if os.system("rsync -azv --remove-source-files --exclude=log.csv {}/ {}".format(self.results_dir, received['send_back_to'])):
                #         print("Try {}/10 Couldn't rsync results from host {}")

                os.system("rm -rf {0} && mkdir {0}".format(self.ligand_dir))
                request_work['finished_chunk'] = True
                # The master will retrieve the files and put more files into the directory
            elif 'standby' in received:
                continue
            else:
                break
