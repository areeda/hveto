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

"""Run the safety analysis of a single channel for debugging """

import time

start_time = time.time()

__author__ = 'joseph areeda'
__email__ = 'joseph.areeda@ligo.org'
__version__ = '0.0.1'
__process_name__ = 'safety single'

import argparse
import glob
import h5py
import logging
import os
import re
from gwpy.plot import Plot

from hveto.safety_reader import safety_h5_read
from hveto.core import find_coincidences


def abs_path(p):
    return os.path.abspath(os.path.expanduser(p))


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
    parser.add_argument('-f', '--config-file', action='append', default=[],
                        type=abs_path,
                        help='path to hveto configuration file, can be given '
                             'multiple times (files read in order)')
    parser.add_argument('-p', '--primary', default=None, type=abs_path,
                        help='path to primary channel in an hdf5 file')
    parser.add_argument('-a', '--auxiliary', default=None, type=abs_path,
                        help='path to hdf5 file containing all '
                             'auxiliary channel triggers. ')
    parser.add_argument('-o', '--output-directory',
                      default=os.path.abspath(os.curdir),
                      help='path of output directory, default: %(default)s')
    parser.add_argument('-c', '--chan', help='Cha nel to analyze')
    parser.add_argument('-w', '--win', type=float, help='Time window')
    parser.add_argument('-s', '--save', type=abs_path,
                        help='Filename to save aux channel as hdf5')
    args = parser.parse_args()

    verbosity = args.verbose

    if verbosity < 1:
        logger.setLevel(logging.CRITICAL)
    elif verbosity < 2:
        logger.setLevel(logging.INFO)
    else:
        logger.setLevel(logging.DEBUG)

    chan = args.chan
    freq_lim = [10, 2048]
    ifo = chan[0:2]
    win = args.win
    # event table column names
    t = 'time'
    f = 'frequency'
    s = 'snr'

    prim_dict = safety_h5_read(args.primary, freq_lim)
    prim_evts = prim_dict[ifo + ':hwinjs']
    tlim = [prim_evts[t].min() - 5, prim_evts[t].max() + 5]
    tmin = int(tlim[0])
    tmax = int(tlim[1])

    aux_dict = safety_h5_read(args.auxiliary, freq_lim)
    trigs = aux_dict[chan]
    if args.save:
        trigs.write(args.save, path='/'+chan)
        logger.info('Wrote {:s}', args.save)

    t2 = trigs[(trigs[t] >= tmin) & (trigs[t] <= tmax)]

    c1 = find_coincidences(prim_evts[t], trigs[t], win)
    c1a = find_coincidences(prim_evts[t], t2[t], win)
    c2 = find_coincidences(trigs[t], prim_evts[t], win)
    c2a = find_coincidences(t2[t], prim_evts[t], win)

    print('all inj vs all trig: {:d}'.format(len(c1)))
    print('all inj vs win trig: {:d}'.format(len(c1a)))
    print('all trig vs all inj: {:d}'.format(len(c2)))
    print('win trig vs all inj: {:d}'.format(len(c2a)))

    elap = time.time() - start_time
    logger.info('run time {:.1f} s'.format(elap))
