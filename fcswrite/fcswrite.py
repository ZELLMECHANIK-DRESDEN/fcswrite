#!/usr/bin/python
# -*- coding: utf-8 -*-
"""Write .fcs files for flow cytometry"""
from __future__ import print_function, unicode_literals, division

import struct
import warnings

import numpy as np


def write_fcs(filename, chn_names, data,
              endianness="big",
              compat_chn_names=True,
              compat_percent=True,
              compat_negative=True,
              compat_copy=True,
              compat_fixed_range_for_fl=True):
    """Write numpy data to an .fcs file (FCS3.0 file format)


    Parameters
    ----------
    filename: str
        Path to the output .fcs file
    ch_names: list of str, length C
        Names of the output channels
    data: 2d ndarray of shape (N,C)
        The numpy array data to store as .fcs file format.
    endianness: str
        Set to "little" or "big" to define the byte order used.
    compat_chn_names: bool
        Compatibility mode for 3rd party flow analysis software:
        The characters " ", "?", and "_" are removed in the output
        channel names.
    compat_percent: bool
        Compatibliity mode for 3rd party flow analysis software:
        If a column in `data` contains values only between 0 and 1,
        they are multiplied by 100.
    compat_negative: bool
        Compatibliity mode for 3rd party flow analysis software:
        Flip the sign of `data` if its mean is smaller than zero.
    compat_copy: bool
        Do not override the input array `data` when modified in
        compatibility mode.

    Notes
    -----

    - These commonly used unicode characters are replaced: "µ", "²"
    - If the input data contain NaN values, the corresponding rows
      are excluded due to incompatibility with the FCS file format.

    """
    if not isinstance(data, np.ndarray):
        data = np.array(data)
    # remove rows with nan values
    nanrows = np.isnan(data).any(axis=1)
    if np.sum(nanrows):
        msg = "Rows containing NaNs are not written to {}!".format(filename)
        warnings.warn(msg)
        data = data[~nanrows]
    if endianness not in ["little", "big"]:
        raise ValueError("`endianness` must be 'little' or 'big'!")

    msg = "length of `chn_names` must match length of 2nd axis of `data`"
    assert len(chn_names) == data.shape[1], msg

    rpl = [["µ", "u"],
           ["²", "2"],
           ]

    if compat_chn_names:
        # Compatibility mode: Clean up headers.
        rpl += [[" ", ""],
                ["?", ""],
                ["_", ""],
                ]

    for i in range(len(chn_names)):
        for (a, b) in rpl:
            chn_names[i] = chn_names[i].replace(a, b)

    if compat_percent:
        # Compatibility mode: Scale values b/w 0 and 1 to percent
        toscale = []
        for ch in range(data.shape[1]):
            if data[:, ch].min() > 0 and data[:, ch].max() < 1:
                toscale.append(ch)
        if len(toscale):
            if compat_copy:
                # copy if requested
                data = data.copy()
            for ch in toscale:
                data[:, ch] *= 100

    if compat_negative:
        toflip = []
        for ch in range(data.shape[1]):
            if np.mean(data[:, ch]) < 0:
                toflip.append(ch)
        if len(toflip):
            if compat_copy:
                # copy if requested
                data = data.copy()
            for ch in toflip:
                data[:, ch] *= -1

    # DATA segment
    data1 = data.flatten().tolist()
    DATA = struct.pack('>%sf' % len(data1), *data1)

    # TEXT segment
    # fix length of TEXT to 4 kilo bytes
    ltxt = 4096
    ver = 'FCS3.0'
    textfirst = '{0: >8}'.format(256)
    datafirst = '{0: >8}'.format(256+ltxt)
    datalast = '{0: >8}'.format(256+ltxt+len(DATA)-1)
    anafirst = '{0: >8}'.format(0)
    analast = '{0: >8}'.format(0)
    if endianness == "little":
        # use little endian
        byteord = '1,2,3,4'
    else:
        # use big endian
        byteord = '4,3,2,1'
    TEXT = '/$BEGINANALYSIS/0/$ENDANALYSIS/0'
    TEXT += '/$BEGINSTEXT/0/$ENDSTEXT/0'
    TEXT += '/$BEGINDATA/{0}/$ENDDATA/{1}'.format(
        256+ltxt, 256+ltxt+len(DATA)-1)
    TEXT += '/$BYTEORD/{0}/$DATATYPE/F'.format(byteord)
    TEXT += '/$MODE/L/$NEXTDATA/0/$TOT/{0}'.format(data.shape[0])
    TEXT += '/$PAR/{0}'.format(data.shape[1])

    # Check for content of data columns and set range
    for i in range(data.shape[1]):
        # Check if this is fluorescence data, set range to 2**15
        if (chn_names[i].endswith("maximum[a.u.]") and
                compat_fixed_range_for_fl):
            pnrange = int(2**15)
        # If this is deformation, range shall be 100 (percent) or 1
        elif chn_names[i] == "Deformation" or chn_names[i] == "Circularity":
            # if column contains scaled data, set range to 100
            if i in toscale:
                pnrange = 100
            # if not, to 1
            else:
                pnrange = 1
        # default: set range to maxium value found in column
        else:
            pnrange = int(abs(np.max(data[:, i])))
        # TODO:
        # - Set log/lin
        fmt_str = '/$P{0}B/32/$P{0}E/0,0/$P{0}N/{1}/$P{0}R/{2}/$P{0}D/Linear'
        TEXT += fmt_str.format(i+1, chn_names[i], pnrange)
    TEXT += '/'
    textlast = '{0: >8}'.format(len(TEXT)+256-1)
    TEXT = TEXT.ljust(ltxt, ' ')

    # HEADER segment
    HEADER = '{0: <256}'.format(ver+'    ' +
                                textfirst +
                                textlast +
                                datafirst +
                                datalast +
                                anafirst +
                                analast)

    # Write data
    with open(filename, "wb") as fd:
        fd.write(HEADER.encode("ascii", "replace"))
        fd.write(TEXT.encode("ascii", "replace"))
        fd.write(DATA)
        fd.write(b'00000000')
