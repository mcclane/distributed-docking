import re
import subprocess
import shutil
import os
from datetime import datetime

class Smina:
    def __init__(self, executable_path, ligand_path, config=None, receptor=None, output_path=None, rank=None):
        self.executable_path = executable_path
        self.ligand_path = ligand_path
        self.output_path = output_path
        self.config = config
        self.receptor = receptor
        self.rank = rank
        self.zinc_re = re.compile("REMARK\s+Name\s*=\s*(ZINC\d+)")
        self.energy_re = re.compile("REMARK\s+minimizedAffinity\s+([-+]?[0-9]*\.?[0-9]+)")\
    
    def run_file(self, path):
        output_file = self.output_path / path.name
        cmd = [
            str(self.executable_path),
        ]
        if self.config:
            cmd.extend([
                '--config', str(self.config)
            ])
        if self.receptor:
            cmd.extend([
                '--receptor', str(self.receptor)
            ])
        cmd.extend([
            '--ligand', str(path),
            '--out', str(output_file)
        ])

        output = subprocess.check_output(cmd)
        print(path.name)

        zincid, energy = self.extract_zincid_energy(str(output_file))
        self.convert_to_pdb(str(output_file), str(self.output_path / output_file.stem) + ".pdb")

        return zincid, energy

    def preprocess_file(self, filename):
        # for f in inh*.pdbqt; do sed -i '/USER/d' $f; sed -i '/TER/d' $f; done
        pass

    def extract_zincid_energy(self, filename):
        zincid = None
        energy = None
        with open(filename) as f:
            for line in f:
                e = self.energy_re.search(line)
                if not energy and e:
                    energy = e.group(1)
                elif not zincid:
                    z = self.zinc_re.search(line)
                    if z:
                        zincid = z.group(1)
                else:
                    return zincid, energy

    def convert_to_pdb(self, in_filename, out_filename):
        err = os.system("cut -c-66 {0} > {1}".format(in_filename, out_filename))
        if err:
            return err
        return os.remove(str(in_filename))

    def run_job(self):
        timestamp = datetime.now().strftime("%d-%m-%Y_%H-%M-%S")
        if self.rank:
            summary_filename = self.output_path / "summary_w{}_{}.tsv".format(self.rank, timestamp)
        else:
            summary_filename = self.output_path / "summary_{}.tsv".format(timestamp)

        sf = open(str(summary_filename), 'w')
        for path in self.ligand_path.glob("*.pdbqt"):
            res = self.run_file(path)
            if res:
                zincid, energy = res
                sf.write("{}.pdb\t{}\t{}\n".format(path.stem, zincid, energy))
            else:
                print("Couldn't run {}".format(path.name))
        sf.close()
        return summary_filename