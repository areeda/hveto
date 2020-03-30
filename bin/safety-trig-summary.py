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

"""Summarize trigger files from safety studies"""

import time

start_time = time.time()

__author__ = 'joseph areeda'
__email__ = 'joseph.areeda@ligo.org'
__version__ = '0.0.1'
__process_name__ = 'safety-trig-summary'

import argparse
import glob
import h5py
import logging
import os
import re
import subprocess

from gwpy.table import EventTable
from gwpy.time import to_gps
from gwpy.plot import Plot

from hveto.safety_reader import safety_h5_read
from hveto.core import find_coincidences


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
    parser.add_argument('-i', '--infile', help='input hdf5')
    parser.add_argument('-p', '--primary', help='Primary channel to compare')
    parser.add_argument('-o', '--odir', help='Output directory')
    parser.add_argument('-s', '--start', type=to_gps,
                        help='Start of injections')
    parser.add_argument('-e', '--end', type=to_gps,
                        help='End of injections or duration')

    args = parser.parse_args()
    start = args.start
    end = args.end
    if int(end) < 1e7:
        end += start

    verbosity = args.verbose

    if verbosity < 1:
        logger.setLevel(logging.CRITICAL)
    elif verbosity < 2:
        logger.setLevel(logging.INFO)
    else:
        logger.setLevel(logging.DEBUG)

    freq_lim = [10, 2048]
    ifo = 'L1'
    # event table column names
    t = 'time'
    f = 'frequency'
    s = 'snr'

    prim_dict = safety_h5_read(args.primary, freq_lim)
    prim_evts = prim_dict[ifo + ':hwinjs']
    tlim = [prim_evts[t].min() - 5, prim_evts[t].max() + 5]
    tmin = int(tlim[0])
    tmax = int(tlim[1])

    aux_dict = safety_h5_read(args.infile, freq_lim)


    print('{:d} channels in {:s}'.format(len(aux_dict.keys()), args.infile))
    print('\n\nChannel, N, N-inj, time min, time max, freq min, freq max, '
          'snr min, snr max')
    # init file wise limits
    tfmin = 1e12
    tfmax = 0
    ffmin = 1e10
    ffmax = 0
    sfmin = 1e10
    sfmax = 0
    N = 0
    Ni = 0
    for chan in aux_dict.keys():
        trigs = aux_dict[chan]
        t2 = trigs[(trigs[t]>=start) & (trigs[t]<=end)]

        N += len(trigs)
        Ni += len(t2)

        if t2 is not None and len(t2) == 0:
            continue

        tmin = trigs[t].min()
        tfmin = min(tfmin, tmin)
        tmax = trigs[t].max()
        tfmax = max(tfmax, tmax)

        fmin = trigs[f].min()
        ffmin = min(ffmin, fmin)
        fmax = trigs[f].max()
        ffmax = max(ffmax, fmax)

        smin = trigs[s].min()
        sfmin = min(sfmin, smin)
        smax = trigs[s].max()
        sfmax = max(sfmax, smax)

        print('{:s}, {:d}, {:d}, {:.2f}, {:.2f}, {:.2f}, {:.2f}, '
              '{:.2f}, {:.2f}'
              .format(chan, len(trigs), len(t2), tmin, tmax, fmin, fmax,
                      smin, smax))
        if len(trigs) > 0:
            idx = find_coincidences(prim_evts[t], trigs[t], 0.1)
            if idx is  None or len(idx) == 0:
                continue

            plot = Plot(figsize=[8, 12])
            plot3 = Plot(figsize=[8, 6])

            ax = plot.add_subplot(2, 1, 1, sharex=None)
            ax.scatter(prim_evts[t], prim_evts[f], c=prim_evts[s],
                       marker='o')
            plot.add_colorbar(clim=[1, 75], cmap='viridis', log=True,
                              label='Signal-to-noise ratio (SNR)', ax=ax)
            idx = find_coincidences(prim_evts[t], trigs[t], 0.1)
            if len(idx) == 0:
                continue
            ax.scatter(prim_evts[t][idx], prim_evts[f][idx],
                       color='k', marker='+')
            ax.set_title('Injections ({:d} coincs)'.format(len(idx)))
            ax.set_ylim(freq_lim)
            ax.set_yscale('log')
            ax.set_ylabel('Frequency [Hz]')
            ax.set_xscale('auto-gps')
            ax.set_xlim(int(start), int(end))

            inj_fname = os.path.join(args.odir, chan.replace(':', '-') +
                                     '--plan.png')
            plot2 = Plot(figsize=[8, 6])
            ax2 = plot2.gca()
            ax2.scatter(prim_evts[t], prim_evts[f], c=prim_evts[s],
                        marker='o')
            plot2.add_colorbar(clim=[1, 75], cmap='viridis', log=True,
                              label='Signal-to-noise ratio (SNR)')
            idx = find_coincidences(prim_evts[t], trigs[t], 0.1)
            ax2.scatter(prim_evts[t][idx], prim_evts[f][idx],
                        color='k', marker='+')
            ax2.set_title('Injections ({:d} coincs)'.format(len(idx)))
            ax2.set_ylim(freq_lim)
            ax2.set_yscale('log')
            ax2.set_ylabel('Frequency [Hz]')
            ax2.set_xscale('auto-gps')
            ax2.set_xlim(int(start), int(end))

            plot2.savefig(inj_fname, edgecolor='white', figsize=[8, 6],
                          dpi=100, bbox_inches='tight')
            plot2.close()
            logger.debug('Saved {:s}'.format(inj_fname))


            ax = plot.add_subplot(2, 1, 2, sharex=ax)
            ax.scatter(trigs[t], trigs[f], c=trigs[s], marker='o')
            plot.add_colorbar(clim=[1, 75], cmap='viridis', log=True,
                              label='Signal-to-noise ratio (SNR)', ax=ax)
            idx = find_coincidences(trigs[t], prim_evts[t], 0.1)
            if len(idx) > 0:
                ax.scatter(trigs[t][idx], trigs[f][idx],
                           color='r', marker='+')
            ax.set_ylim(freq_lim)
            ax.set_title('{:s} ({:d} coincs)'.format(chan, len(idx)))
            ax.set_yscale('log')
            ax.set_ylabel('Frequency [Hz]')
            ax.set_xscale('auto-gps')
            ax.set_xlim(int(start), int(end))

            ax3 = plot3.gca()
            ax3.scatter(trigs[t], trigs[f], c=trigs[s], marker='o')
            plot3.add_colorbar(clim=[1, 75], cmap='viridis', log=True,
                              label='Signal-to-noise ratio (SNR)')
            idx = find_coincidences(trigs[t], prim_evts[t], 0.1)
            if len(idx) > 0:
                ax3.scatter(trigs[t][idx], trigs[f][idx],
                           color='r', marker='+')
            ax3.set_ylim(freq_lim)
            ax3.set_title('{:s} ({:d} coincs)'.format(chan, len(idx)))
            ax3.set_yscale('log')
            ax3.set_ylabel('Frequency [Hz]')
            ax3.set_xscale('auto-gps')
            ax3.set_xlim(int(start), int(end))

            fname = os.path.join(args.odir, chan.replace(':', '-') + '.png')
            plot.savefig(fname, edgecolor='white', figsize=[8, 12],
                         dpi=100, bbox_inches='tight')
            plot.close()
            logger.debug('Saved {:s}'.format(fname))


            fname3 = os.path.join(args.odir, chan.replace(':', '-') +
                                  '--obs.png')
            plot3.savefig(fname3, edgecolor='white', figsize=[8, 6],
                         dpi=100, bbox_inches='tight')
            plot3.close()
            logger.debug('Saved {:s}'.format(fname3))

            gif_name= os.path.join(args.odir, chan.replace(':', '-') +
                                   '--anim.gif')
            st = subprocess.run(['convert', '-delay', '60', '-loop', '0',
                                inj_fname, fname3, gif_name])
            logger.debug('Saved {:s}'.format(gif_name))


    print('\nFILE TOTALS, {:d}, {:d}, {:.2f}, {:.2f}, {:.2f}, '
          '{:.2f}, {:.2f}, {:.2f}'
          .format(N, Ni, tfmin, tfmax, ffmin, ffmax, sfmin, sfmax))
    elap = time.time() - start_time
    logger.info('run time {:.1f} s'.format(elap))
