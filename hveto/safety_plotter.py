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

"""New plots for safety studies"""

import time

import os
from gwpy.plot import Plot
from hveto.core import find_coincidences
import subprocess


def inj_comp_plot(chan, prim_evts, trigs, win, odir):
    """Compare the primary with the aux events in subplots"""

    # event table column names
    t = 'time'
    f = 'frequency'
    s = 'snr'

    tlim = [prim_evts[t].min() - 5, prim_evts[t].max() + 5]
    tmin = int(tlim[0])
    tmax = int(tlim[1])
    freq_lim = [1, 2048]
    idx_pri = find_coincidences(prim_evts[t], trigs[t], win)

    plot = Plot(figsize=[8, 14])

    ax = plot.add_subplot(2, 1, 1)
    plot.subplotpars.hspace = .3

    ax.scatter(prim_evts[t], prim_evts[f], c=prim_evts[s],
               marker='o')
    # plot.add_colorbar(clim=[1, 75], cmap='viridis', log=True,
    #                   label='Signal-to-noise ratio (SNR)', ax=ax)

    ax.scatter(prim_evts[t][idx_pri], prim_evts[f][idx_pri],
               color='k', marker='+')
    ax.set_title('Injections ({:d}/{:d} coincs)'.
                 format(len(idx_pri), len(prim_evts)))
    ax.set_ylim(freq_lim)
    ax.set_yscale('log')
    ax.set_ylabel('Frequency [Hz]')
    ax.set_xscale('auto-gps')
    ax.set_xlim(tlim)

    inj_fname = os.path.join(odir, chan.replace(':', '-') +
                             '--plan.png')
    plot2 = Plot(figsize=[8, 6])
    ax2 = plot2.gca()
    ax2.scatter(prim_evts[t], prim_evts[f], c=prim_evts[s],
                marker='o')
    # plot2.add_colorbar(clim=[1, 75], cmap='viridis', log=True,
    #                    label='Signal-to-noise ratio (SNR)')
    ax2.scatter(prim_evts[t][idx_pri], prim_evts[f][idx_pri],
                color='k', marker='+')
    ax2.set_title('Injections ({:d}/{:d} coincs)'.
                  format(len(idx_pri), len(prim_evts)))
    ax2.set_ylim(freq_lim)
    ax2.set_yscale('log')
    ax2.set_ylabel('Frequency [Hz]')
    ax2.set_xscale('auto-gps')
    ax2.set_xlim(tlim)

    plot2.savefig(inj_fname, edgecolor='white', bbox_inches='tight')
    plot2.close()

    ax = plot.add_subplot(2, 1, 2, sharex=ax)
    ax.scatter(trigs[t], trigs[f], c=trigs[s], marker='o')
    # plot.add_colorbar(clim=[1, 75], cmap='viridis', log=True,
    #                   label='Signal-to-noise ratio (SNR)', ax=ax)
    idx_pri = find_coincidences(trigs[t], prim_evts[t], win)
    if len(idx_pri) > 0:
        ax.scatter(trigs[t][idx_pri], trigs[f][idx_pri],
                   color='r', marker='+')
    ax.set_ylim(freq_lim)
    ax.set_title('{:s} ({:d}/{:d} coincs)'.
                 format(chan, len(idx_pri), len(trigs),
                        fontdict={'fontsize':9}))
    ax.set_yscale('log')
    ax.set_ylabel('Frequency [Hz]')
    ax.set_xscale('auto-gps')
    ax.set_xlim(tlim)

    plot3 = Plot(figsize=[8, 6])

    ax3 = plot3.gca()
    ax3.scatter(trigs[t], trigs[f], c=trigs[s], marker='o')
    # plot3.add_colorbar(clim=[1, 75], cmap='viridis', log=True,
    #                    label='Signal-to-noise ratio (SNR)')
    idx_aux = find_coincidences(trigs[t], prim_evts[t], win)
    if len(idx_aux) > 0:
        ax3.scatter(trigs[t][idx_aux], trigs[f][idx_aux],
                    color='r', marker='+')
    ax3.set_ylim(freq_lim)
    ax3.set_title('{:s} ({:d}/{:d} coincs)'.
                  format(chan, len(idx_aux), len(trigs)))
    ax3.set_yscale('log')
    ax3.set_ylabel('Frequency [Hz]')
    ax3.set_xscale('auto-gps')
    ax3.set_xlim(tlim)

    fname = os.path.join(odir, chan.replace(':', '-') + '-2subs.png')
    plot.savefig(fname, edgecolor='white', bbox_inches='tight')
    plot.close()

    fname3 = os.path.join(odir, chan.replace(':', '-') +
                          '--obs.png')
    plot3.savefig(fname3, edgecolor='white', bbox_inches='tight')
    plot3.close()

    gif_name = os.path.join(odir, chan.replace(':', '-') +
                            '--anim.gif')
    st = subprocess.run(['convert', '-delay', '60', '-loop', '0',
                         inj_fname, fname3, gif_name])
    os.remove(inj_fname)
    os.remove(fname3)

    return  fname, gif_name
