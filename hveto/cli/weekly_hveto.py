#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: nu:ai:ts=4:sw=4

#
#  Copyright (C) 2025 Joseph Areeda <joseph.areeda@ligo.org>
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

""""""
import os
import textwrap
import time
from datetime import datetime, timedelta, timezone
import socket

start_time = time.time()

import argparse
import logging
from pathlib import Path
import re
import sys
import traceback
from gwpy.time import to_gps, from_gps

try:
    from ._version import __version__
except ImportError:
    __version__ = '0.0.0'

__author__ = 'joseph areeda'
__email__ = 'joseph.areeda@ligo.org'
__process_name__ = Path(__file__).name

logger = None

hveto_run_sh = textwrap.dedent('''\
    #!/bin/bash
    # script used by %program_name% condor DAG to run one analysis
    # Created by %program_name% version %program_version% on %date%

    configuration="%configuration%"
    nproc=%nproc%
    ifo=%ifo%
    gpsstart="%gpsstart%"
    gpsend="%gpsend%"
    outer_dir="%outer_dir%"
    prefix="%prefix%"

    condaRun="/cvmfs/software.igwn.org/conda/condabin/conda run --prefix $%prefix% --no-capture-output --no-capture-error "


    cmd="python -m hveto ${gpsstart} ${gpsend} --ifo ${ifo} --config-file ${configuration} --nproc ${nproc} \
        --output-directory ${outer_dir}"

    ${condaRun} ${cmd}

    ''')

hveto_job_submit_sh = textwrap.dedent('''
#!/usr/bin/env condor_submit
#
# Condor submit file for %program_name% processing
# Created by %program_name% version %program_version% on %date%
#

universe = vanilla
executable = %exec%

accounting_group = ligo.dev.o4.detchar.dqtriggers.hveto
accounting_group_user = joseph.areeda

request_memory = %request_memory%M
request_disk = 10GB

output = %condor_dir%/hveto.out
error = %condor_dir%/hveto.err
log = %condor_dir%/hveto.log

batch_name = "hveto %end_day% %out_of% ID: $(ClusterId)"

use_oauth_services = scitokens
environment = BEARER_TOKEN_FILE=$$(CondorScratchDir)/.condor_creds/scitokens.use


queue
''')


def to_day(in_str):
    in_gps = to_gps(in_str)
    in_date = from_gps(in_gps)
    ret = in_date.strftime('%Y-%m-%d')
    return ret


def get_default_ifo():
    # if at a site we have a default ifo
    host = socket.getfqdn()
    if 'ligo-la' in host:
        ifo = 'L1'
    elif 'ligo-wa' in host:
        ifo = 'H1'
    else:
        ifo = os.getenv('IFO')
    if ifo is None:
        ifo = 'UK'
    return ifo, host


def parser_add_args(parser):
    """
    Set up command parser
    :param argparse.ArgumentParser parser:
    :return: None but parser object is updated
    """
    parser.add_argument('-v', '--verbose', action='count', default=1,
                        help='increase verbose output')
    parser.add_argument('-V', '--version', action='version',
                        version=__version__)
    parser.add_argument('-q', '--quiet', default=False, action='store_true',
                        help='show only fatal errors')

    this_script = Path(__file__)
    user = os.getenv('USER')
    config_possibles = [
        this_script.parent.parent / 'configurations' / 'hveto' / 'h1l1-hveto-daily-o4b.ini',
        Path(f'/home/{user}/etc/ligo-monitors/configurations/hveto/h1l1-hveto-daily-o4b.ini'),
        Path('/home/detchar/etc/ligo-monitors/configurations/hveto/h1l1-hveto-daily-o4b.ini'),
    ]
    default_config_file = None
    for config in config_possibles:
        if config.exists():
            default_config_file = config
            break

    parser.add_argument('-c', '--config-file', default=default_config_file, help='path to hveto configuration file')

    now_utc = datetime.now(timezone.utc)
    default_end_date = now_utc.strftime('%Y-%m-%d')

    parser.add_argument('-e', '--end', type=to_day, default=default_end_date,
                        help='Processng looks back duration days up to but not including this date. (default: %(default)s).')
    parser.add_argument('-s', '--start', type=to_day, default=default_end_date,
                        help='We process one day at a time from end daste back to star date each '
                             'run is duration days long (default: %(default)s).')
    parser.add_argument('-d', '--duration', type=int, default=7,
                        help='Number of days analyze for each day (default: %(default)s).')
    parser.add_argument('--stride', type=int, default=1,
                        help='Number of days between each hveto run. '
                             'For example start=7/1, end=7/29, stride=7, duration=7'
                             'will create 4 hveto reports ending on 7/28, 7/21, 7/14, 7/1 each covering 7 days')
    parser.add_argument('--no-submit', action='store_true',
                        help='Create directory, script and submit file but do not submit to Condor')
    parser.add_argument('-o', '--output-directory', default='/home/detchar/public_html/hveto-weekly',
                        help='Parent directory for what may be multiple hveto runs')

    prefix = os.getenv('CONDA_PREFIX', '/home/detchar/.conda/envs/ligo-summary-3.10')
    parser.add_argument('-p', '--prefix', default=prefix, help='Path to conda environment to run hveto in')

    ifo, host = get_default_ifo()
    parser.add_argument('-i', '--ifo', default=ifo, help='IFO for hveto analysis')
    parser.add_argument('-n', '--nproc', default=4, type=int, help='Number of parallel tigger readers')


def apply_symbols(txt, symbols):
    """
    Search text for {<symbol>} entries use <symbol> as key to dicionary then substite its value
    :param str txt: input string with <symbol> entries
    :param dict symbols: symbol table
    :return str: text with substitutions applied
    """
    ret = ''
    for line in txt.splitlines():
        oline = line
        while re.match('.*%.+%', oline):
            for symbol, value in symbols.items():
                pattern = '%' + rf'{symbol}' + '%'
                oline = re.sub(pattern, str(value), oline)
            if oline != line:
                logger.debug(f'  {line} -> {oline}')
            else:
                logger.critical(f'Undefined symbol in {line}')
            break
        ret += oline + '\n'
    return ret


def make_job(job_name, job_args):
    """
    Creates and prepares the directory and condor files for a single hveto job.

    :param str job_name: The name of the job to create
    :param Path job_dir: The directory where the job will be generated or executed
    :param dict job_args: The arguments to use for the job
    :return Path: Path to the submit file
    """
    job_dir = job_args['outer_dir']
    logger.debug(f'Creating condor file needed for job {job_name} in {job_dir}')
    job_dir.mkdir(parents=True, exist_ok=True)
    job_condadir = job_dir / 'condor'
    job_condadir.mkdir(parents=True, exist_ok=True)

    job_submit_file = job_dir / 'condor' / f'{job_name}.submit'
    job_run_sh = job_condadir / f'{job_name}.sh'
    job_script = apply_symbols(hveto_run_sh, job_args)
    job_run_sh.write_text(job_script)
    job_run_sh.chmod(0o755)
    job_args['exec'] = job_run_sh

    job_submit = apply_symbols(hveto_job_submit_sh, job_args)
    job_submit_file.write_text(job_submit)

    return job_submit_file


def main():
    global logger

    log_file_format = "%(asctime)s - %(levelname)s - %(funcName)s %(lineno)d: %(message)s"
    log_file_date_format = '%m-%d %H:%M:%S'
    logging.basicConfig(format=log_file_format, datefmt=log_file_date_format)
    logger = logging.getLogger(__process_name__)
    logger.setLevel(logging.DEBUG)

    description = textwrap.dedent("""
    Create a bash script and condor_submit for a multi-day run of hveto, then submit to vanilla universe
    By default:
    - We process 7 days of data ending at 00:00 UTC today, expecting it to run around 02:00Z
    - Output goes to ~/public_html/hveto/weekly/<YYYYMM>/<YYYYMMDD>/
    - Uses the configuration file "h1l1-hveto-daily-o4b.ini" found at
      <path to this script>/../configurations/hveto/ or
      ~/etc/ligo-monitors/configurations/hveto/ or
      /home/detchar/etc/ligo-monitors/configurations/hveto/
    """)

    epilog = textwrap.dedent("""
    Running with default (no) arguments  will run hveto over 7 days of data ending at 00:00 UTC this morning.

    To run hveto for every day for the month of July, each run covering 7 days:

        python -m weekly_hveto --start 7/1 --end 7/31 --duration 7 --stride 1

    """)
    parser = argparse.ArgumentParser(description=description, epilog=epilog, prog=__process_name__,
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser_add_args(parser)
    args = parser.parse_args()
    verbosity = 0 if args.quiet else args.verbose

    if verbosity < 1:
        logger.setLevel(logging.CRITICAL)
    elif verbosity < 2:
        logger.setLevel(logging.INFO)
    else:
        logger.setLevel(logging.DEBUG)

    # debugging?
    logger.debug(f'{__process_name__} version: {__version__} called with arguments:')
    for k, v in args.__dict__.items():
        logger.debug('    {} = {}'.format(k, v))

    config = args.config_file
    if config is None:
        logger.critical('Configuration file not specified')
        raise ValueError('Configuration file not specified')

    start_day = args.start
    start_gps = to_gps(start_day)
    start_dt = from_gps(start_gps)

    end_day = args.end
    end_gps = to_gps(end_day)
    end_dt = from_gps(end_gps)
    next_dt = end_dt

    duration = args.duration
    duration_dt = timedelta(days=duration)

    stride = args.stride
    stride_dt = timedelta(days=stride)

    output_directory = Path(args.output_directory)
    now_time = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    dag_file = output_directory / f'DAG-{now_time}' / 'hveto.dag'
    logger.info(f'DAG file  will be written to {dag_file}')
    dag_file.parent.mkdir(parents=True, exist_ok=True)

    with dag_file.open('w') as dag_fh:
        print(f'# process long duration hveto for {start_day} to {end_day} each {duration} days', file=dag_fh)
        print(f'# stride = {stride} days', file=dag_fh)
        print(f'# Created by {__process_name__}, version {__version__}\\n', file=dag_fh)
        print('max_jobs = 3', file=dag_fh)

        njobs = int((end_dt - start_dt).days / stride)
        current_job = 1

        while start_dt <= next_dt:
            begin_dt = to_day(next_dt - duration_dt)
            begin_day = to_day(begin_dt)
            next_day = to_day(next_dt)
            job_name = f'hveto_{current_job:02d}_of_{njobs:02d}'
            logger.debug(f'Process hveto {begin_day} to {next_day}')
            job_month = next_dt.strftime('%Y%m')
            job_day = next_dt.strftime('%Y%m%d')

            #  create the results directory and add the condor submit file and bash script
            job_dir = output_directory / job_month / job_day

            # rutiime args are sed to create the obs bash script
            job_args = {
                "configuration": config,
                "nproc": args.nproc,
                "ifo": args.ifo,
                "gpsstart": begin_day,
                "gpsend": next_day,
                "outer_dir": job_dir,
                "prefix": args.prefix,
                "program_name": __process_name__,
                "program_version": __version__,
                "date": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "condor_dir": job_dir / 'condor',
                "request_memory": 32768,
                "end_day": next_day,
                "out_of": f'{current_job:02d}_of_{njobs:02d}',

            }
            job_submit_file = make_job(job_name, job_args)

            # add this job to the DAG
            print(f'JOB {job_name} {job_submit_file}', file=dag_fh)
            current_job += 1

            next_dt -= stride_dt

    logger.info(f'DAG file with {njobs} jobs written to {dag_file}')


if __name__ == "__main__":
    try:
        main()
    except (ValueError, TypeError, OSError, NameError, ArithmeticError, RuntimeError) as ex:
        print(ex, file=sys.stderr)
        traceback.print_exc(file=sys.stderr)

    if logger is None:
        logging.basicConfig()
        logger = logging.getLogger(__process_name__)
        logger.setLevel(logging.DEBUG)
    # report our run time
    logger.info(f'Elapsed time: {time.time() - start_time:.1f}s')
