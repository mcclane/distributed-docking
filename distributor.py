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

def main():
    parser = ArgumentParser()
    parser.add_argument('--cfg', type=str, required=True, help="big daddy config file")
    args = parser.parse_args()

    with open(args.cfg) as f:
        cfg = yaml.safe_load(f)

    rank = MPI.COMM_WORLD.Get_rank()
    # print(rank, socket.gethostname())

    if rank == 0:
        master(cfg)
    else:
        worker(cfg)


def master(cfg):
    MPI.COMM_WORLD.Barrier()
    local_workspace, ligand_dir, results_dir, temp_dir = create_master_workspace(cfg)
    not_run = get_unrun_batches(cfg)
    print("Batches to be run:", not_run)
    for batch in not_run:
        print("Running batch", batch)
        if not is_downloaded(batch, ligand_dir):
            print("downloading batch from remote...", end='', flush=True)
            if download_batch(batch, cfg['library'], ligand_dir):
                print("Couldn't rsync remote directory for batch", batch)
                break
            print("done")
            print("unzipping batch...", end='', flush=True)
            unzip_batch(batch, ligand_dir)
            print("done")
        
        print("diffing ligands and results...", end='', flush=True)
        to_run = diff_ligands_results(ligand_dir / batch, results_dir)
        print("done")
        print(len(to_run), "ligands to be run")

        # start distributing these ligands
        print("distributing ligands")
        distribute_ligands(cfg['chunk_size'], to_run)

        # re-diff on ligands and results
        # aggregate summary files
        # create archive
        # move summary and archive to storage (use rsync --remove-source option)
        # clear ligands and results folders

    send_stop_signals()


def worker(cfg):
    rank = MPI.COMM_WORLD.Get_rank()
    hostname = gethostname()

    # create workspace directory on local machine
    # distributed-docking
    #   worker-{rank}
    #       ligands
    #       results

    local_workspace, ligand_dir, results_dir, temp_dir = create_worker_workspace(cfg, rank)

    # copy over config folder (executable, config file, receptor)
    os.system("rsync -a {} {}".format(cfg['config_folder_path'], str(local_workspace / "config")))


    MPI.COMM_WORLD.Barrier()
    MPI.COMM_WORLD.send({'ready'}, dest=0)


    while True:
        received = MPI.COMM_WORLD.recv(source=0)
        if 'ligands' in received:
            print("worker {} received {} ligands".format(rank, len(received['ligands'])))

            # copy over ligand files to local machine
            # idock or smina?

            MPI.COMM_WORLD.send({'ready'}, dest=0)
        else:
            break



def distribute_ligands(chunk_size, to_run):
    status = MPI.Status()
    i = 0
    while i < len(to_run):
        received = MPI.COMM_WORLD.recv(status=status)
        ligands_to_send = to_run[i:i + chunk_size]
        i += len(ligands_to_send)
        print("sending {} ligands to worker {}".format(len(ligands_to_send), status.Get_source()))
        # TODO: send path to ligands (<hostname>:/<full path>), path to receptor
        MPI.COMM_WORLD.send({'ligands': ligands_to_send}, dest=status.Get_source())

def send_stop_signals():
    status = MPI.Status()
    print("Waiting for workers to finish")
    for i in range(MPI.COMM_WORLD.Get_size() - 1):
        received = MPI.COMM_WORLD.recv(status=status)
        MPI.COMM_WORLD.send({
                'stop'
            },
            dest=status.Get_source())

def diff_ligands_results(ligand_dir, results_dir):
    # cmd = 'rsync -avun --delete {}/ {}/p{}/ | grep -oP "deleting \K(\S+)" > {}/ligandsToRun.txt'.format(cfg['results_dir'], cfg['all_ligand_dir'], batch, cfg['temp_dir'])
    not_run = set()
    for fn in os.listdir(str(ligand_dir)):
        if fn.startswith("ligand"):
            not_run.add(fn.split(".")[0])
    for fn in os.listdir(str(results_dir)):
        if fn.startswith("ligand"):
            not_run.remove(fn.split(".")[0])
    return list(not_run)

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

def create_master_workspace(cfg):
    local_workspace = Path(cfg['local_workspace']) / 'distributed-docking'
    if not local_workspace.exists():
        print("Creating local workspace directory...", end='', flush=True)
        local_workspace.mkdir()
        print("done")
    
    ligand_dir = local_workspace / "ligands"
    if not ligand_dir.exists():
        print("Creating ligand directory...", end='', flush=True)
        ligand_dir.mkdir()
        print("done")
    
    results_dir = local_workspace / "results"
    if not results_dir.exists():
        print("Creating results directory...", end='', flush=True)
        results_dir.mkdir()
        print("done")

    temp_dir = local_workspace / "temp"
    if not temp_dir.exists():
        print("Creating temp directory...", end='', flush=True)
        temp_dir.mkdir()
        print("done")

    return local_workspace, ligand_dir, results_dir, temp_dir

def create_worker_workspace(cfg, rank):
    parent_dir = Path(cfg['local_workspace']) / 'distributed-docking'
    if not parent_dir.exists():
        print("Creating local workspace parent directory...", end='', flush=True)
        parent_dir.mkdir()
        print("done")
    
    local_workspace = parent_dir / "worker-{}".format(rank)
    if local_workspace.exists():
        print("Removing existing local workspace")
        os.system("rm -rf {0} && mkdir {0}".format(str(local_workspace)))
    else:
        print("Creating local workspace directory...", end='', flush=True)
        local_workspace.mkdir()
        print("done")
    
    ligand_dir = local_workspace / "ligands"
    if not ligand_dir.exists():
        print("Creating ligand directory...", end='', flush=True)
        ligand_dir.mkdir()
        print("done")
    
    results_dir = local_workspace / "results"
    if not results_dir.exists():
        print("Creating results directory...", end='', flush=True)
        results_dir.mkdir()
        print("done")

    temp_dir = local_workspace / "temp"
    if not temp_dir.exists():
        print("Creating temp directory...", end='', flush=True)
        temp_dir.mkdir()
        print("done")

    return local_workspace, ligand_dir, results_dir, temp_dir
    


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

if __name__ == '__main__':
    main()