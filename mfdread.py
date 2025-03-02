#!/usr/bin/env python
# -*- coding: utf-8 -*-

#  mfdread.py - Mifare dumps parser in human readable format
#  Pavel Zhovner <pavel@zhovner.com>
#  https://github.com/zhovner/mfdread


import codecs
import copy
import sys
from datetime import datetime, timedelta
from collections import defaultdict

from bitstring import BitArray


class Options:
    FORCE_1K = False
    UID_LENGTH = 4

if len(sys.argv) == 1:
    sys.exit('''
------------------
Usage: mfdread.py ./dump.mfd
Mifare dumps reader.
''')


def decode(bytes):
    decoded = codecs.decode(bytes, "hex")
    try:
        return str(decoded, "utf-8").rstrip(b'\0')
    except:
        return ""


class bashcolors:
    BLUE = '\033[34m'
    RED = '\033[91m'
    GREEN = '\033[32m'
    WARNING = '\033[93m'
    ENDC = '\033[0m'


def accbits_for_blocknum(accbits_str, blocknum):
    '''
    Decodes the access bit string for block "blocknum".
    Returns the three access bits for the block or False if the
    inverted bits do not match the access bits.
    '''
    bits = BitArray([0])
    inverted = BitArray([0])

    # Block 0 access bits
    if blocknum == 0:
        bits = BitArray([accbits_str[11], accbits_str[23], accbits_str[19]])
        inverted = BitArray([accbits_str[7], accbits_str[3], accbits_str[15]])

    # Block 0 access bits
    elif blocknum == 1:
        bits = BitArray([accbits_str[10], accbits_str[22], accbits_str[18]])
        inverted = BitArray([accbits_str[6], accbits_str[2], accbits_str[14]])
    # Block 0 access bits
    elif blocknum == 2:
        bits = BitArray([accbits_str[9], accbits_str[21], accbits_str[17]])
        inverted = BitArray([accbits_str[5], accbits_str[1], accbits_str[13]])
    # Sector trailer / Block 3 access bits
    elif blocknum in (3, 15):
        bits = BitArray([accbits_str[8], accbits_str[20], accbits_str[16]])
        inverted = BitArray([accbits_str[4], accbits_str[0], accbits_str[12]])

    # Check the decoded bits
    inverted.invert()
    if bits.bin == inverted.bin:
        return bits
    else:
        return False


def accbits_to_permission_sector(accbits):
    permissions = {
        '000': "- A | A   - | A A [read B]",
        '010': "- - | A   - | A - [read B]",
        '100': "- B | A/B - | - B",
        '110': "- - | A/B - | - -",
        '001': "- A | A   A | A A [transport]",
        '011': "- B | A/B B | - B",
        '101': "- - | A/B B | - -",
        '111': "- - | A/B - | - -",
    }
    if isinstance(accbits, BitArray):
        return permissions.get(accbits.bin, "unknown")
    else:
        return ""


def accbits_to_permission_data(accbits):
    permissions = {
        '000': "A/B | A/B   | A/B | A/B [transport]",
        '010': "A/B |  -    |  -  |  -  [r/w]",
        '100': "A/B |   B   |  -  |  -  [r/w]",
        '110': "A/B |   B   |   B | A/B [value]",
        '001': "A/B |  -    |  -  | A/B [value]",
        '011': "  B |   B   |  -  |  -  [r/w]",
        '101': "  B |  -    |  -  |  -  [r/w]",
        '111': " -  |  -    |  -  |  -  [r/w]",
    }
    if isinstance(accbits, BitArray):
        return permissions.get(accbits.bin, "unknown")
    else:
        return ""


def accbit_info(accbits, sector_size):
    '''
    Returns  a dictionary of a access bits for all three blocks in a sector.
    If the access bits for block could not be decoded properly, the value is set to False.
    '''
    access_bits = defaultdict(lambda: False)

    if sector_size == 15:
        access_bits[sector_size] = accbits_for_blocknum(accbits, sector_size)
        return access_bits

    # Decode access bits for all 4 blocks of the sector
    for i in range(0, 4):
        access_bits[i] = accbits_for_blocknum(accbits, i)
    return access_bits

def is_value_block(block):
    b = bytes.fromhex(block)
    return  (b[0] == b[8] and (b[0] ^ 0xFF) == b[4]) and \
            (b[1] == b[9] and (b[1] ^ 0xFF) == b[5]) and \
            (b[2] == b[10] and (b[2] ^ 0xFF) == b[6]) and \
            (b[3] == b[11] and (b[3] ^ 0xFF) == b[7]) and \
            (b[12] == b[14] and b[13] == b[15] and \
            (b[12] ^ 0xFF) == b[13])

def print_info(data):
    blocksmatrix = []
    blockrights = {}
    block_number = 0

    data_size = len(data)

    if data_size not in {4096, 1024, 320}:
        sys.exit("Wrong file size: %d bytes.\nOnly 320, 1024 or 4096 bytes allowed." % len(data))

    if Options.FORCE_1K:
        data_size = 1024

    # read all sectors
    sector_number = 0
    start = 0
    end = 64
    while True:
        sector = data[start:end]
        sector = codecs.encode(sector, 'hex')
        if not isinstance(sector, str):
            sector = str(sector, 'ascii')
        sectors = [sector[x:x + 32] for x in range(0, len(sector), 32)]

        blocksmatrix.append(sectors)

        # after 32 sectors each sector has 16 blocks instead of 4
        sector_number += 1
        if sector_number < 32:
            start += 64
            end += 64
        elif sector_number == 32:
            start += 64
            end += 256
        else:
            start += 256
            end += 256

        if start == data_size:
            break

    blocksmatrix_clear = copy.deepcopy(blocksmatrix)

    # add colors for each keyA, access bits, KeyB
    for c in range(0, len(blocksmatrix)):
        sector_size = len(blocksmatrix[c]) - 1

        # Fill in the access bits
        blockrights[c] = accbit_info(BitArray('0x' + blocksmatrix[c][sector_size][12:20]), sector_size)

        # Prepare colored output of the sector trailor
        keyA = bashcolors.RED + blocksmatrix[c][sector_size][0:12] + bashcolors.ENDC
        accbits = bashcolors.GREEN + blocksmatrix[c][sector_size][12:20] + bashcolors.ENDC
        keyB = bashcolors.BLUE + blocksmatrix[c][sector_size][20:32] + bashcolors.ENDC

        blocksmatrix[c][sector_size] = keyA + accbits + keyB

    if Options.UID_LENGTH == 4:
        sakStart = Options.UID_LENGTH * 2 + 2
    else:
        sakStart = Options.UID_LENGTH * 2

    print("File size: %d bytes. Expected %d sectors" % (len(data), sector_number))
    if Options.UID_LENGTH == 4:
        print("\n\tUID:  " + blocksmatrix[0][0][0:8])
    else:
        print("\n\tUID:  " + blocksmatrix[0][0][0:14])
    print("\tBCC:  " + blocksmatrix[0][0][8:10])
    print("\tSAK:  " + blocksmatrix[0][0][sakStart:sakStart + 2])
    print("\tATQA: " + blocksmatrix[0][0][sakStart + 2:sakStart + 6])
    # Code taken from https://github.com/ikarus23/MifareClassicTool
    try:
        year = int(blocksmatrix_clear[0][0][30:32])
        week = int(blocksmatrix_clear[0][0][28:30])
        now = datetime.now().year - 2000
        if year >= 0 and year <= now and week >= 1 and week <= 53:
            # "fromisocalendar" available only in >= Python 3.8
            try:
                calendar = datetime.fromisocalendar(year + 2000, week, 1)
                startDate = calendar.strftime("%d.%m.%Y")
                endDate = (calendar + timedelta(days=6)).strftime("%d.%m.%Y")
                print("\tYear of manufacture: Between {} and {}".format(startDate, endDate))
            except:
                pass
    except:
        pass

    print("                   %sKey A%s    %sAccess Bits%s    %sKey B%s" % (
        bashcolors.RED, bashcolors.ENDC, bashcolors.GREEN, bashcolors.ENDC, bashcolors.BLUE, bashcolors.ENDC))
    print("╔═════════╦═══════╦══════════════════════════════════╦════════╦═════════════════════════════════════╗")
    print("║  Sector ║ Block ║            Data                  ║ Access ║   A | Acc.  | B                     ║")
    print("║         ║       ║                                  ║        ║ r w | r   w | r w [info]            ║")
    print("║         ║       ║                                  ║        ║  r  |  w    |  i  | d/t/r           ║")

    for q in range(0, len(blocksmatrix)):
        print("╠═════════╬═══════╬══════════════════════════════════╬════════╬═════════════════════════════════════╣")
        n_blocks = len(blocksmatrix[q])

        # z is the block in each sector
        for z in range(0, len(blocksmatrix[q])):

            # Format the access bits. Print ERR in case of an error
            if isinstance(blockrights[q][z], BitArray):
                accbits = bashcolors.GREEN + blockrights[q][z].bin + bashcolors.ENDC
            else:
                accbits = bashcolors.WARNING + "ERR" + bashcolors.ENDC

            if q == 0 and z == 0:
                permissions = "-"

            elif z == n_blocks - 1:
                permissions = accbits_to_permission_sector(blockrights[q][z])
            else:
                permissions = accbits_to_permission_data(blockrights[q][z])

            # Print the sector number in the second third row
            if z == 2:
                qn = q
            else:
                qn = ""

            if is_value_block(blocksmatrix_clear[q][z]):
                blocksmatrix[q][z] = bashcolors.WARNING + blocksmatrix_clear[q][z] + bashcolors.ENDC

            print("║    %-5s║  %-3d  ║ %s ║  %s   ║ %-35s ║ %s" % (qn, block_number, blocksmatrix[q][z],
                                                                   accbits, permissions,
                                                                   decode(blocksmatrix_clear[q][z])))

            block_number += 1

    print("╚═════════╩═══════╩══════════════════════════════════╩════════╩═════════════════════════════════════╝")


def main(args):
    if args[0] == '-n':
        args.pop(0)
        bashcolors.BLUE = ""
        bashcolors.RED = ""
        bashcolors.GREEN = ""
        bashcolors.WARNING = ""
        bashcolors.ENDC = ""

    if args[0] == '-1':
        args.pop(0)
        Options.FORCE_1K = True

    if args[0] == "-7":
        args.pop(0)
        Options.UID_LENGTH = 7

    filename = args[0]
    with open(filename, "rb") as f:
        data = f.read()
        print_info(data)


if __name__ == "__main__":
    main(sys.argv[1:])
