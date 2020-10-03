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
        self.model1_re = re.compile("MODEL\s+1")
        self.zinc_re = re.compile("REMARK\s+Name\s*=\s*(ZINC\d+)")
        self.energy_re = re.compile("REMARK\s+minimizedAffinity\s+([-+]?[0-9]*\.?[0-9]?[0-9]?[0-9])")
        self.ter_re = re.compile("TER")
        self.user_re = re.compile("USER")
    
    def run_file(self, path):
        self.preprocess_file(path)
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

        try:
            output = subprocess.check_output(cmd)
            zincid, energy = self.extract_zincid_energy(str(output_file))
            #self.convert_to_pdb(str(output_file), str(self.output_path / output_file.stem) + ".pdb")
            return zincid, energy
        except subprocess.CalledProcessError:
            print("smina error running {}".format(path.name))

    def preprocess_file(self, filename):
        os.system("sed -i '/USER/d' {}".format(filename))
        os.system("sed -i '/TER/d' {}".format(filename))

    def extract_zincid_energy(self, filename):
        model1 = False
        zincid = None
        energy = None
        with open(filename) as f:
            for line in f:
                m = self.model1_re.search(line)
                if m:
                    model1 = True
                if model1 and not energy:
                    e = self.energy_re.search(line)
                    if e:
                        energy = e.group(1)
                elif model1 and not zincid:
                    z = self.zinc_re.search(line)
                    if z:
                        zincid = z.group(1)
                elif energy and zincid:
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
                to_write = "{}.pdb\t{}\t{}".format(path.stem, zincid, energy) 
                print(to_write)
                sf.write(to_write + "\n")
            else:
                print("Couldn't run {}".format(path.name))
        sf.close()
        print("summary {} written".format(summary_filename.name))
        return summary_filename
