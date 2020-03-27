#!/usr/bin/env python
# vim: nu:ai:ts=4:sw=4

#
#  Copyright (C) 2020 Joseph Areeda <joseph.areeda@ligo.org>
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

"""Plot comparision of planned injection vs auxiliary channels"""

import time

start_time = time.time()

__author__ = 'joseph areeda'
__email__ = 'joseph.areeda@ligo.org'
__version__ = '0.0.1'
__process_name__ = 'hveto-safety-aux-plot'

import argparse
import glob
import h5py
import logging
import os
import re

from gwpy.table import EventTable
from hveto.safety_reader import safety_h5_read


if __name__ == "__main__":
    logging.basicConfig()
    logger = logging.getLogger(__process_name__)
    logger.setLevel(logging.DEBUG)

    start_time = time.time()
    parser = argparse.ArgumentParser(description=__doc__,
                                     prog=__process_name__)
    parser.add_argument('-v', '--verbose', action='count', default=1,
                        help='increase verbose output')
    parser.add_argument('-q', '--quiet', default=False, action='store_true',
                        help='show only fatal errors')
    parser.add_argument('-p', '--planned',
                        help='Path to planned events (HDF5)')
    parser.add_argument('-a', '--aux',
                        help='Path to auxiliary channel events (HDF5)')
    parser.add_argument('-o', '--outdir', help='Output directory')

    args = parser.parse_args()

    verbosity = args.verbose

    if verbosity < 1:
        logger.setLevel(logging.CRITICAL)
    elif verbosity < 2:
        logger.setLevel(logging.INFO)
    else:
        logger.setLevel(logging.DEBUG)

    # move to args
    freq_lim = [0, 2048]
    ifo = 'L1'

    # event table column names
    t = 'time'
    f = 'frequency'
    s = 'snr'

    plotdir = args.outdir
    os.makedirs(plotdir, exist_ok=True)

    prim_dict = safety_h5_read(args.planned, freq_lim)
    prim_evts = prim_dict[ifo+':hwinjs']
    tlim = [prim_evts[t].min()-5, prim_evts[t].max()+5]
    tmin = int(tlim[0])
    tmax = int(tlim[1])

    logger.info('{:d} planned events from {} to {}'.format(len(prim_evts),
                                                           tlim[0], tlim[1]))
    aux_dict = safety_h5_read(args.aux, freq_lim)
    aux_tot = 0
    for chan in aux_dict.keys():
        evts = aux_dict[chan]
        evts = evts[(evts[t] >= tmin) & (evts[t] <= tmax)]
        aux_tot += len(evts)

    logger.info('{:d} events in {:d} aux channels during injections'.
                format(aux_tot, len(aux_dict.keys())))


    elap = time.time() - start_time
    logger.info('run time {:.1f} s'.format(elap))
