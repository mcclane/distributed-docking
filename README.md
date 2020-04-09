# distributed-docking
Two components: mpi launcher and the actual mpi script. The mpi launcher should only actually launch the mpi process. The mpi head node will then take care of downloading and uploading ligand batches. This is in contrast to the previous architecture, in which mpi processes were launched willy nilly and responsibilities were not clearly delegated.

# OpenMPI launcher:
- constructs the mpiexec command
- makes sure the head node stays the same
    + read in the hostfile and make the first line the host.
    + ordering of hosts on command line determines who is made the master process
    + maybe process the hostfile, and use the command line arguments instead
- configuration file:
    + hosts (first of which is made the master node
    + mpiexec path
    + any command line arguments for mpiexec
    + path to configuration file for the actual master and worker processes

# OpenMPI process:
- master process rsyncs next ligand batch over, unzips ligands, diffs results and ligand directories on master local directory - need to make sure master node can be specified (so is kept the same all the time)
- while there are still ligands to be run, master process distributes lists of ligand filenames to run to the workers
- when a worker receives a list of ligands to be run:
    + worker rsyncs ligands to a local directory
    + worker runs ligands:
        - idock
            + construct idock command to run ligands
        - smina
            + preprocess ligand files
            + construct smina command to run ligands
        + idock or smina or vina or whatever else is configured
    + worker generates a summary file of the ligands (doing any necessary processing on the results files)
        - having ligands and results files in the local directory will speed up the summary generation and processing of results files
    + worker rsyncs finished ligands and summary file to the results directory on the nfs
    + worker removes files and requests another chunk of work
- when all ligands are finished, master process concatenates the individual summary files, sorts, and creates an archive file
