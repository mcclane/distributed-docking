import re
import subprocess
import shutil
import os
from datetime import datetime

class idock:
    def __init__(self, executable_path, ligand_path, config=None, receptor=None, output_path=None, rank=None):
        self.executable_path = executable_path
        self.ligand_path = ligand_path
        self.output_path = output_path
        self.config = config
        self.receptor = receptor
        self.rank = rank
    
    def construct_command(self):
        cmd = [
            str(self.executable_path),
            '--ligand', str(self.ligand_path)
        ]
        if self.output_path:
            cmd.extend([
                '--out', str(self.output_path)
            ])
        if self.config:
            cmd.extend([
                '--config', str(self.config)
            ])
        if self.receptor:
            cmd.extend([
                '--receptor', str(self.receptor)
            ])
        return cmd

    def generate_summary(self):
        timestamp = datetime.now().strftime("%d-%m-%Y_%H-%M-%S")
        if self.rank:
            summary_filename = self.output_path / "summary_w{}_{}.tsv".format(self.rank, timestamp)
        else:
            summary_filename = self.output_path / "summary_{}.tsv".format(timestamp)

        energy_re = re.compile("NORMALIZED FREE ENERGY PREDICTED BY IDOCK:\s+([-+]?[0-9]*\.?[0-9]+) KCAL\/MOL")
        results = []
        sf = open(str(summary_filename), 'w')
        for ligand in self.ligand_path.glob("*.pdbqt"):
            zincid = get_zincid(str(ligand))
            if not zincid:
                print("Couldn't find zincid")
                continue
            
            already_converted = False
            result_file = self.output_path / ligand.name
            if not result_file.exists():
                result_file = self.output_path / (ligand.stem + ".pdb")
                already_converted = True
            if not result_file.exists():
                print("Couldn't find result file")
                continue

            energy = ""
            with open(str(result_file)) as f:
                for line in f:
                    m = energy_re.search(line)
                    if m:
                        energy = m.group(1)
                        break
            if energy == "":
                print("Couldn't find energy")
                continue

            if not already_converted:
                output_pdb = self.output_path / (ligand.stem + ".pdb")
                if os.system("cut -c-66 {0} > {1}".format(result_file, output_pdb)):
                    print("Couldn't convert pdb to pdbqt")
                    continue
                os.remove(str(result_file))

            sf.write("{}\t{}\t{}\n".format(ligand.name, zincid, energy))
        sf.close()
        return summary_filename
    
    def run_job(self):
        cmd = self.construct_command()

        child = subprocess.Popen(cmd)
        child.wait()

        summary_filename = self.generate_summary()

        return summary_filename


zinc_re = re.compile("REMARK\s+Name\s*=\s*(ZINC\d+)")
def get_zincid(pdbqt_file):
    with open(pdbqt_file) as f:
        for line in f:
            m = zinc_re.search(line)
            if m:
                return m.group(1)