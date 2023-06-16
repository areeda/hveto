# -*- coding: utf-8 -*-
# Copyright (C) Joshua Smith (2016-)
#
# This file is part of the hveto python package.
#
# hveto is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# hveto is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with hveto.  If not, see <http://www.gnu.org/licenses/>.

"""Core of the HierarchichalVeto algorithm
"""

import itertools
import re
from math import (log, exp, log10)
from bisect import (bisect_left, bisect_right)

import numpy

from scipy.special import (gammainc, gammaln)

from astropy.table import vstack as vstack_tables

from gwpy.segments import (SegmentList, Segment)

__author__ = 'Duncan Macleod <duncan.macleod@ligo.org>'
__credits__ = 'Joshua Smith <joshua.smith@ligo.org>'

LOG_10 = log(10)
LOG_EXP_1 = log10(exp(1))


# -- define round structure --------------------------------------------------

class HvetoRound(object):
    __slots__ = (
        'n',
        'primary',
        'winner',
        'segments',
        'vetoes',
        'use_percentage',
        'efficiency',
        'cum_efficiency',
        'cum_deadtime',
        'plots',
        'files',
        'scans',
        'rank',
        # Used by safety
        'unsafe',
        'n_coincs',
        'n_vetoed',
    )

    def __init__(self, round, primary, segments=None, vetoes=None,
                 plots=[], files={}, rank=None):
        self.n = round
        self.primary = primary
        self.segments = segments
        self.vetoes = vetoes
        self.plots = []
        self.files = {}
        self.scans = None
        self.rank = rank
        self.unsafe = False # used in safety studies to flag already known
        self.n_coincs = 0    # used in safety studies for report
        self.n_vetoed = 0

    @property
    def livetime(self):
        return float(abs(self.segments))

    @property
    def deadtime(self):
        return (float(abs((self.vetoes & self.segments).coalesce())),
                float(abs(self.segments)))


# -- core methods ------------------------------------------------------------

def find_all_coincidences(triggers, channel, snrs, windows):
    """Find the number of coincs between each auxiliary channel and the primary

    Parameters
    ----------
    primary : `numpy.ndarray`
        an array of times for the primary channel
    auxiliary : `numpy.recarray`
        an array of triggers for a set of auxiliary channels
    snrs : `list` of `float`
        the SNR thresholds to use
    window : `list` of `float`
        the time windows to use
    """
    # FIXME need to work out having time column the same for each channel
    triggers.sort('time')
    windows = sorted(windows, reverse=True)
    snrs = sorted(snrs)
    coincs = dict((p, {}) for p in itertools.product(windows, snrs))
    ntrig = len(triggers)

    for i, x in enumerate(triggers):
        if x['channel'] != channel:
            continue
        t = x['time']
        channels = dict((key, set()) for key in coincs)
        j = i - 1
        segs = [Segment(t - dt / 2., t + dt / 2.) for dt in windows]

        # define coincidence test
        def add_if_coinc(event):
            if event['channel'] == channel:
                return
            in_seg = filter(lambda s: s[0] <= event['time'] <= s[1], segs)
            if not in_seg:  # no triggers in window
                return
            for k, w in enumerate(in_seg):
                for snr in filter(lambda s: event['snr'] >= s, snrs):
                    channels[(windows[k], snr)].add(event['channel'])
            return 1

        # search left half-window
        while j >= 0:
            if not add_if_coinc(triggers[j]):
                break
            j -= 1
        j = i + 1
        # search right half-window
        while j < ntrig:
            if not add_if_coinc(triggers[j]):
                break
            j += 1

        # count 'em up
        for p, cset in channels.items():
            for c in cset:
                try:
                    coincs[p][c] += 1
                except KeyError:
                    coincs[p][c] = 1

    return coincs


def find_max_significance(primary, auxiliary, channel, snrs, windows,
                          livetime):
    """Find the maximum Hveto significance for this primary-auxiliary pair

    Parameters
    ----------
    primary : `numpy.recarray`
        record array of data from the primary channel
    auxiliary : `numpy.recarray`
        record array from the auxiliary channel
    snrs : `list` of `float`
        the SNR thresholds to use
    window : `list` of `float`
        the time windows to use

    Returns
    -------
    winner : `HvetoWinner`
        the parameters and segments generated by the (snr, dt) with the
        highest significance
    """
    rec = vstack_tables([primary] + list(auxiliary.values()))
    coincs = find_all_coincidences(rec, channel, snrs, windows)
    winner = HvetoWinner(name='unknown', significance=-1)
    sigs = dict((c, 0) for c in auxiliary)
    for p, cdict in coincs.items():
        dt, snr = p
        for chan in cdict:
            mu = (len(primary) * (auxiliary[chan]['snr'] >= snr).sum() * dt / livetime)
            # NOTE: coincs[p][chan] counts the number of primary channel
            # triggers coincident with a 'chan' trigger
            try:
                sig = significance(coincs[p][chan], mu)
            except KeyError:
                sig == 0
            if sig > sigs[chan]:
                sigs[chan] = sig
            if sig > winner.significance:
                winner.name = chan
                winner.snr = snr
                winner.window = dt
                winner.significance = sig
                winner.mu = mu
    return winner, sigs


class HvetoWinner(object):
    __slots__ = ['name', 'significance', 'snr', 'window', 'segments',
                 'events', 'ncoinc', 'mu', 'n_vetoed']

    def __init__(self, name=None, significance=None, snr=None,
                 window=None, segments=None, events=None, ncoinc=0, mu=None):
        super(HvetoWinner, self).__init__()
        self.name = name
        self.significance = significance
        self.snr = snr
        self.window = window
        self.segments = segments
        self.events = events
        self.mu = mu

    def get_segments(self, times):
        return SegmentList([Segment(t - self.window / 2., t + self.window / 2.)
                            for t in times])


def coinc_significance(a, b, dt, livetime):
    """Calculate the significance of coincidences between two time arrays

    Parameters
    ----------
    a : `numpy.ndarray`
        first array
    b : `numpy.ndarray`
        second array
    dt : `float`
        coincidence window
    livetime : `float`
        the livetime of the analysis

    Returns
    -------
    coincs : `numpy.ndarray`
        the indices of array `a` that were coincident with an entry in `b`
    significance : `float`
        the Poisson significance of the number of coincidences found as
        compared to the number expected by random chance
    """
    # find coincidences
    coincs = find_coincidences(a, b, dt=dt)
    n = coincs.size
    if n == 0:
        return coincs, 0
    # calculate significance
    try:
        prob = a.size * dt / livetime
    except ZeroDivisionError:
        prob = 0
    mu = prob * b.size
    return coincs, significance(n, mu)


def significance(n, mu):
    """Calculate the significance of `n` coincidences, when `mu` were expected

    Parameters
    ----------
    n : `int`
        the number of coincidences found
    mu : `float`
        the number of coincidences expected from a Poisson process
    """
    g = gammainc(n, mu)
    if g == 0:
        sig = -n * log10(mu) + mu * LOG_EXP_1 + gammaln(n + 1) / LOG_10
    else:
        sig = -log10(g)
    return float(sig)


def find_coincidences(a, b, dt=1):
    """Find the coincidences between values in two numpy arrays

    Parameters
    ----------
    a : `numpy.ndarray`
        first array
    b : `numpy.ndarray`
        second array
    dt : `float`, optional
        coincidence window

    Returns
    -------
    coinc : `numpy.ndarray`
        the indices of all items in `a` within [-dt/2., +dt/2.) of an item
        in `b`
    """
    dx = dt / 2.

    def _is_coincident(t):
        x = bisect_left(b, t - dx)  # find b >= t-dx
        y = bisect_right(b, t + dx)  # find b <= t+dx
        if x != y:
            return True
        return False

    out = numpy.zeros(a.size)
    for i, t in enumerate(a):
        out[i] = _is_coincident(t)
    return out.nonzero()[0]


def veto(table, segmentlist):
    """Remove events from a table based on a segmentlist

    A time ``t`` will be vetoed if ``start <= t <= end`` for any veto
    segment in the list.

    Parameters
    ----------
    table : `numpy.recarray`
        the table of event triggers to veto
    segmentlist : `~ligo.segments.segmentlist`
        the list of veto segments to use

    Returns
    -------
    keep : `numpy.recarray`
        the reduced table of events that were not coincident with any
        segments
    removed: `numpy.recarray`
        Table of events removed by veto segments
    """
    table.sort('time')
    times = table['time']
    segmentlist = type(segmentlist)(segmentlist).coalesce()
    keep = numpy.ones(times.shape[0], dtype=bool)
    j = 0
    a, b = segmentlist[j]
    i = 0
    while i < times.size:
        t = times[i]
        # if before start, move to next trigger now
        if t < a:
            i += 1
            continue
        # if after end, find the next segment and check this trigger again
        if t > b:
            j += 1
            try:
                a, b = segmentlist[j]
                continue
            except IndexError:
                break
        # otherwise it must be in this segment, record and move to next
        keep[i] = False
        i += 1
    return table[keep], table[~keep]


def veto_all(auxiliary, segmentlist):
    """Remove events from all auxiliary channel tables based on a segmentlist

    Parameters
    ----------
    auxiliary : `dict` of `numpy.recarray`
        a `dict` of event arrays to veto
    segmentlist : `~ligo.segments.segmentlist`
        the list of veto segments to use

    Returns
    -------
    survivors : `dict` of `numpy.recarray`
        a dict of the reduced arrays of events for each input channel

    See Also
    --------
    core.veto
        for details on the veto algorithm itself
    """
    channels = auxiliary.keys()
    t = vstack_tables(list(auxiliary.values()))
    keep, _ = veto(t, segmentlist)
    return dict((c, keep[keep['channel'] == c]) for c in channels)
