# distributed-docking

Runs [molecular docking](https://en.wikipedia.org/wiki/Docking_(molecular)) programs in parallel on an MPI cluster. Currently supports [idock](https://github.com/HongjianLi/idock). Smina support is coming soon. This program is currently being used on Cal Poly's Massively Parallel Accelerated Computing (MPAC) lab and [DIRAC](https://github.com/ellisonbg/dirac-cluster/wiki) cluster.


# Requirements
- A cluster with an MPI implementation installed. This has been developed with OpenMPI.
    + This program was rewritten to use local storage on each node in the MPI cluster for faster io speeds. A nfs could likely be used without issue.
- python3. However, this has been developed with python3.4, solely because that was the newest version of python available across every machine in the MPAC lab. It should work on newer version of python3.
- python packages: `mpi4py PyYAML`. See `requirements.txt`


# Usage

`python3.4 launcher.py --cfg config.yaml`


# What exactly does it do?

`launcher.py` finds hosts from the supplied hosts that are reachable over ssh and constructs and launches an mpiexec process with the supplied arguments and hosts.

The first reachable host supplied in the configuration file becomes the master node. Each node sets up a workspace directory in the `local_workspace` directory specified in the configuration file.

Each worker node downloads the configuration folder specified by `config_folder_dir` in the configuration file.

The master node then begins running batches (in the order specified by `batches` in the configuration file) that do not yet have summary and archive files in the `processed` directory.

For each a batch, the master node checks to see if the batch has already been downloaded and unarchived in the workspace directory. If it has not, the master downloads and unarchives the batch. The master node then finds ligands that have not yet been run (by comparing the ligands in the unarchived batch directory and ligands in the local results directory). These ligands are then distributed to available workers.

When all ligands have been distributed, a summary file is created by combining all partial summary files from each individual worker and then sorting in order of increasing energy. An archive file containing the output files from the docking program and the combined summary file is created. The archive and summary files are then sent to the `processed` location specified in the configuration file.

# Options

All options are supplied via the configuration file. All options listed below are required. See `example_config.yaml` for a full example.

`library:` Directory containing archive files of the ligand library to run. Can be a remote directory. The ligand directory should have the following structure:
```
library_dir/
    p01.tar.gz
    p02.tar.gz
    ...
```
Each archive file should have the structure:
```
p01/
    ligand_somenumber.pdbqt
    ...
```

`processed:` Directory to put archive and summary files of processed batches in. Can be a remote directory.

`archive_prefix:` Prefix of processed ligand archive filenames (not a directory, simply for naming files meaningfully).

`summary_prefix:` Prefix of processed summary filenames.

`docking:` Type of docking to run. Options are: `idock`. Smina support is in progress.

`config_folder_path:` Directory containing the docking program executable, docking program configuration file, and receptor pdbqt file. Can be a remote directory.

`receptor:`: name of the receptor pdbqt file inside the directory at `config_folder_path`

`batches:` A list of batches to be run (['p01', 'p02', ...]). Order matters.

`chunk_size:` The number of ligands distributed to a worker at one time.

`python:` Path to python executable

`mpiexec_path:` Path to `mpiexec` executable

`mpi_args:` List of command line arguments for `mpiexec` executable. For example:
```
mpi_args:
    - --mca plm_rsh_no_tree_spawn 1
```

`local_workspace:` Directory used by each worker process to store data related to the run. Can be a local or shared directory.

`hosts:` A list of hosts to run workers on. Each entry in the list has a hostname and number of slots. The number of slots corresponds to the number of processes that will be launched on the machine. The first node listed will always be made the master node. This is important if you want to be able to resume runs if they are stopped for some reason. For example:
```
hosts:
    -
        hostname: 127x05.csc.calpoly.edu
        slots: 2 # one master process, one worker process
    -
        hostname: 127x03.csc.calpoly.edu
        slots: 3 # three worker processes
```


# Troubleshooting


## The program got interrupted

If the program gets interrupted when it is screening ligands, just restart the program. It will pick up mostly where it left off, but it will have to rerun ligands that the workers were currently working on when they got interrupted.

If the program gets interrupted when it is creating an archive file, just restart the program.

If the program gets interrupted when unarchiving a new batch from the library, you will have to remove the partially unarchived directory and restart the process. This means deleting the `<local_workspace>/distributed-docking/ligands`. If you do not remove the partially unarchive ligands directory, the next time the program runs it will use the partially unarchive directory, instead of the full batch you wanted it to run.


## The program hangs after launching the mpi process

One of the hosts may not be responsive to MPI. This can happen a lot on the MPAC lab. You may have to comment out all the hosts in the configuration file and start adding them one by one, making sure the process runs with the addition of each new host.