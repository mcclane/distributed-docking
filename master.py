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

class Master:
    def __init__(self, cfg):
        self.cfg = cfg
    
    def create_workspace(self):
        self.local_workspace = Path(self.cfg['local_workspace']) / 'distributed-docking'
        if not self.local_workspace.exists():
            self.local_workspace.mkdir()
        
        self.ligand_dir = self.local_workspace / "ligands"
        if not self.ligand_dir.exists():
            self.ligand_dir.mkdir()
        
        self.results_dir = self.local_workspace / "results"
        if not self.results_dir.exists():
            self.results_dir.mkdir()


    def main(self):
        MPI.COMM_WORLD.Barrier()
        self.create_workspace()
        not_run = get_unrun_batches(self.cfg)
        print("Batches to be run:", not_run)
        for batch in not_run:
            print("Running batch", batch)

            if not is_downloaded(batch, self.ligand_dir):
                print("downloading batch from remote...", end='', flush=True)
                if download_batch(batch, self.cfg['library'], self.ligand_dir):
                    print("Couldn't rsync remote directory for batch", batch)
                    break
                print("done")
                print("unzipping batch...", end='', flush=True)
                unzip_batch(batch, self.ligand_dir)
                print("done")
            
            print("diffing ligands and results...", end='', flush=True)
            to_run = diff_ligands_results(self.ligand_dir / batch, self.results_dir)
            print("done")
            print(len(to_run), "ligands to be run")

            # start distributing these ligands
            print("distributing ligands")
            self.distribute_ligands(self.cfg['chunk_size'], to_run, batch)

            # print("Checking again for stragglers")
            # to_run = diff_ligands_results(self.ligand_dir / batch, self.results_dir)
            # if len(to_run) > 0:
            #     self.distribute_ligands(self.cfg['chunk_size'], to_run, batch)

            print("Creating summary file")
            summary_filename = self.concatenate_and_sort_summary_files(batch)

            print("Creating archive file")
            archive_filename = self.create_archive(batch)

            print("storing results")
            if self.store_archive_summary(archive_filename, summary_filename):
                print("couldn't store results, exiting...")
                break
            
            print("cleaning up results and ligands directories")
            self.remove_ligands_results_dirs()


        print("sending stop signals...", end='', flush=True)
        self.send_stop_signals()
        print("done")

    def distribute_ligands(self, chunk_size, to_run, batch):
        status = MPI.Status()
        i = 0
        while i < len(to_run):
            received = MPI.COMM_WORLD.recv(status=status)

            if received['finished_chunk']:
                print("retrieving chunk from {}".format(received['results_dir']))
                self.retrieve_chunk_from_worker(received['results_dir'])

            ligands_to_send = to_run[i:i + chunk_size]
            i += len(ligands_to_send)
            print("rsyncing ligands to {}".format(received['ligand_dir']))
            self.rsync_ligand_batch(ligands_to_send, batch, received['ligand_dir'])

            MPI.COMM_WORLD.send({'chunk_sent'},
                                 dest=status.Get_source())


        print("Waiting for workers to finish")
        # wait for workers to finish
        for i in range(MPI.COMM_WORLD.Get_size() - 1):
            received = MPI.COMM_WORLD.recv(status=status)
            if received['finished_chunk']:
                print("retrieving chunk from {}".format(received['results_dir']))
                self.retrieve_chunk_from_worker(received['results_dir'])
            MPI.COMM_WORLD.send({'standby'}, dest=status.Get_source())


        print("done distributing")

    def rsync_ligand_batch(self, ligands, batch, destination):
        ligands =  "\n".join(ligands)
        ligands_file = str(self.local_workspace / "temp_send_ligands.txt") # only one at a time!
        with open(ligands_file, 'w') as f:
            f.write(ligands)
        return os.system("rsync -az --files-from={} {} {}".format(ligands_file, str(self.ligand_dir / batch), destination))
    
    def retrieve_chunk_from_worker(self, source):
        err = os.system("rsync -az --remove-source-files --exclude=log.csv {}/ {}".format(source, self.results_dir))
        return err
    
    def send_stop_signals(self):
        for i in range(1, MPI.COMM_WORLD.Get_size()):
            MPI.COMM_WORLD.send({'stop'}, dest=i)
    
    def concatenate_and_sort_summary_files(self, batch):
        out_filename = str(self.results_dir / (self.cfg['summary_prefix'] + batch + ".txt"))
        of = open(out_filename, 'w')
        for fname in self.results_dir.glob("summary*.tsv"):
            with open(str(fname)) as f:
                shutil.copyfileobj(f, of)
            os.remove(str(fname))
        of.close()
        os.system("sort -n -k3 {0} -o {0}".format(out_filename))
        return out_filename
    
    def create_archive(self, batch):
        archive_filename = str(self.local_workspace / (self.cfg['archive_prefix'] + batch))
        shutil.make_archive(archive_filename, "gztar", base_dir="results", root_dir=str(self.local_workspace))
        return archive_filename + ".tar.gz"
    
    def store_archive_summary(self, archive_filename, summary_filename):
        err = os.system("rsync --remove-source-files --chmod=666 "+archive_filename+" "+self.cfg['processed'])
        if err:
            return err
        err = os.system("rsync --remove-source-files --chmod=666 "+summary_filename+" "+self.cfg['processed'])
        if err:
            return err
    
    def remove_ligands_results_dirs(self):
        os.system("rm -rf {0} && mkdir {0}".format(self.ligand_dir))
        os.system("rm -rf {0} && mkdir {0}".format(self.results_dir))



def diff_ligands_results(ligand_dir, results_dir):
    # cmd = 'rsync -avun --delete {}/ {}/p{}/ | grep -oP "deleting \K(\S+)" > {}/ligandsToRun.txt'.format(cfg['results_dir'], cfg['all_ligand_dir'], batch, cfg['temp_dir'])
    not_run = set()
    for fn in os.listdir(str(ligand_dir)):
        if fn.startswith("ligand"):
            not_run.add(fn.split(".")[0])
    for fn in os.listdir(str(results_dir)):
        if fn.startswith("ligand"):
            not_run.remove(fn.split(".")[0])
    not_run = [l + ".pdbqt" for l in list(not_run)]
    return not_run

def unzip_batch(batch, ligand_dir):
    targz = str(ligand_dir / batch) + ".tar.gz"
    output_dir = str(ligand_dir)
    shutil.unpack_archive(targz, output_dir, format='gztar')

def download_batch(batch, library_path, ligand_dir):
    return os.system("rsync {}/{}.tar.gz {}".format(library_path, batch, str(ligand_dir)))

def is_downloaded(batch, ligand_dir):
    ligand_re = re.compile("^(p\d\d.?[0|1]?)$")
    for f in os.listdir(str(ligand_dir)):
        res = ligand_re.match(f)
        if res and batch == res.group(1):
            return True
    return False

def get_unrun_batches(cfg):
    # Find out the next batch to run
    not_run = cfg['batches']
    processed_file_re = re.compile(".*"+re.escape(cfg['archive_prefix']) + "(p\d\d.?[\d]?)\.tar\.gz.*")
    processed_files = check_output(['rsync', cfg['processed']])
    for line in processed_files.splitlines():
        line = line.decode("utf-8")
        res = processed_file_re.match(str(line))
        if res:
            try:
                not_run.remove(res.group(1))
            except ValueError:
                pass
    return not_run
