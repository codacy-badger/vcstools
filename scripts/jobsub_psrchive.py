#!/usr/bin/env python3

import logging
import argparse
import subprocess

from config_vcs import load_config_file
from job_submit import submit_slurm

comp_config = load_config_file()
logger = logging.getLogger(__name__)


def make_batch(kwargs):
    SLURM_TMPL = """{shebag}
    #SBATCH --export={export}
    #SBATCH --output={outfile}
    {account}
    #SBATCH --clusters={cluster}
    #SBATCH --partition={partition}
    #SBATCH --mem-per-cpu={mem}MB

    module use {module_dir}
    module load dspsr
    module load psrchive
    cd {workdir}
    {script}
    """
    shebag = '#!/bin/bash -l'
    export = "NONE"
    cluster = comp_config["cpuq_cluster"]
    partition = comp_config["cpuq_partition"]
    module_dir = comp_config["moduile_dir"]
    mem = kwargs["memory"]
    account=comp_config['group_account']["cpuq"]
    outfile = kwargs["out_name"]
    workdir = kwargs["workdir"]
    script = kwargs["cmd"] + " " + kwargs["ops"]
    tmpl = SLURM_TMPL.format(shebag=shebag, script=commands, outfile=outfile,
                       cluster=cluster, partition=partition,
                       export=export, account=account,
                       module_dir=module_dir, mem=mem)
    with open(kwags["batch_file"], "w") as f:
        f.write(tmpl)


def submit_job(batch_file):
    subprocess.run([f"sbatch {batch_file}"])


def jobsub_main(kwargs):
    make_batch(kwargs)
    if kwargs["submit"]:
        submit_job(kwargs["batch_name"])


if __name__ ==  "__main__":
    loglevels = dict(DEBUG=logging.DEBUG,
                     INFO=logging.INFO,
                     WARNING=logging.WARNING,
                     ERROR=logging.ERROR)
    parser = argparse.ArgumentParser(description="""Creates a batch script/submits the specified PSRCHIVE functions""",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    cmdops = parser.add_argument_group("Command Options")
    cmdops.add_argument("--cmd", type=str, choices=["dspsr", "pdv", "pam", "psrmodel", "rmfit", "psradd"], required=True, help="The PSRCHIVE command to execute")
    cmdops.add_argument("--ops", type=str, required=True, help="Provide as a string in quotes any options you would like to use with the selected command. eg. '-D 50.0 -c 0.50625'")

    subops = parser.add_argument_group("Job Options")
    subops.add_argument("--submit", type=bool, default=False, help="If True, will submit the job after creating the batch script")
    subops.add_argument("--time", type=float, default=2.0, help="The time allocation for the job in hours")
    subops.add_argument("--job_name", type=str, default=None, help="The name of the job on the slurm queue")
    subops.add_argument("--memory", type=int, default=2048, help="The memory allocation for the job in MB.")

    writeops = parser.add_argument_group("Write Options")
    writeops.add_argument("--batch_name", type=str, default="batch_file.batch", help="The name of the resulting batch file")
    writeops.add_argument("--out_name", type=str, default=None, help="The name of the slurm output file")
    writeops.add_argument("--workdir", type=str, default=".", help="The directory to run the job if necessary")

    parser.add_argument("--loglvl", type=str, default="INFO", help="Logger verbosity level", choices=loglevels.keys())

    args = parser.parse_args()
    logger = logging.getLogger()
    logger.setLevel(loglevels[args.loglvl])
    ch = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)s  %(filename)s  %(name)s  %(lineno)-4d  %(levelname)-9s :: %(message)s')
    ch.setFormatter(formatter)
    kawrgs=vars(args)
    jobsub_main(kwargs)