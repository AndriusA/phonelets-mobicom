#!/usr/bin/env python

import sys
from traceback import print_exc
from smartcard.util import toHexString
import numpy as np

import dbus

HWHEADER = [0x05, 0x01, 0x00, 0x00, 0x04, 0x00, 0x00]
commands = [
    [00, 01, 00, 00, 00, 00, 00, 02, 01, 0x2C, 00, 00],
    [07, 00, 00, 00],
    HWHEADER+[7]+[0x00, 0xA4, 0x00, 0x04, 0x02, 0x3F, 0x00]+[0],
    HWHEADER+[7]+[0x00, 0xA4,],
    [0x08, 0x04, 0x02, 0x2F, 0xE2]+[0],
    HWHEADER+[5]+[0x00, 0xB0, 0x00, 0x00, 0x0A, 0, 0]+[0],
    HWHEADER+[25]+[0x80, 0x10, 0x00, 0x00, 0x14, 0xFF, 0x9F,],
    [0xFF, 0xFF, 0x7F, 0x9F, 0x00, 0xDF, 0xFF, 0x03, 0x07, 0x1F, 0x00, 0x08, 0x0C, 0x06, 0x00, 0xEB, 0x0E, 0x03]+[0, 0, 0],
    # [0x80, 0x12, 0x00, 0x00, 0x0F],
    # [0x00, 0xA4, 0x08, 0x04, 0x02, 0x2F, 0x00,],
    # [0x80, 0x14, 0x00, 0x00, 0x0C, 0x81, 0x03, 0x01, 0x05, 0x00, 0x02, 0x02, 0x82, 0x81, 0x03, 0x01, 0x00,],
    # [0x00, 0xA4, 0x08, 0x04, 0x02, 0x2F, 0x06,],
    # [0x00, 0xB2, 0x03, 0x04, 0xC3,],
    # [0x00, 0xA4, 0x08, 0x0C, 0x02, 0x2F, 0x00,],
    # [0x00, 0xB2, 0x01, 0x04, 0x26,],
    # [0x00, 0xA4, 0x00, 0x0C, 0x02, 0x3F, 0x00,],
    # [0x00, 0xA4, 0x04, 0x0C, 0x10, 0xA0, 0x00, 0x00, 0x00, 0x87, 0x10, 0x02, 0xFF, 0xFF, 0xFF, 0xFF, 0x89, 0x03, 0x02, 0x00, 0x00,],
    # [0x00, 0xA4, 0x00, 0x04, 0x02, 0x6F, 0xB7,],
    # [0x00, 0xA4, 0x00, 0x04, 0x02, 0x6F, 0x06,],
    # [0x00, 0xB2, 0x06, 0x04, 0xC3,],
    # [0x00, 0xA4, 0x00, 0x0C, 0x02, 0x6F, 0xB7,],
    # [0x00, 0xB2, 0x01, 0x04, 0x15,],
    # [0x00, 0xB2, 0x02, 0x04, 0x15,],
    # [0x00, 0xB2, 0x03, 0x04, 0x15,],
    # [0x00, 0xB2, 0x04, 0x04, 0x15,],
    # [0x00, 0xB2, 0x05, 0x04, 0x15,],
    # [0x00, 0xA4, 0x00, 0x04, 0x02, 0x6F, 0x05,],
    # [0x00, 0xB0, 0x00, 0x00, 0x0A,],
    # [0x00, 0xA4, 0x08, 0x04, 0x02, 0x2F, 0x05,],
    # [0x00, 0xB0, 0x00, 0x00, 0x0A,],
    # [0x00, 0xA4, 0x00, 0x04, 0x02, 0x7F, 0xFF,],
    # [0x00, 0x2C, 0x00, 0x01, 0x00,],
    # [0x00, 0x20, 0x00, 0x01, 0x00,],
    # [0x00, 0x2C, 0x00, 0x81, 0x00,],
    # [0x00, 0x20, 0x00, 0x81, 0x00,],
    # [0x00, 0xA4, 0x00, 0x04, 0x02, 0x6F, 0x3E,],
    # [0x00, 0xB0, 0x00, 0x00, 0x02,],
    # [0x00, 0xA4, 0x00, 0x04, 0x02, 0x6F, 0x3F,],
    # [0x00, 0xA4, 0x00, 0x0C, 0x02, 0x3F, 0x00,],
    # [0x00, 0xA4, 0x08, 0x04, 0x04, 0x7F, 0xFF, 0x6F, 0x3F,],
    # [0x00, 0xA4, 0x00, 0x0C, 0x02, 0x3F, 0x00, 0x00,],
]

def main():
    bus = dbus.SystemBus()

    try:
        remote_object = bus.get_object("org.smart_e.RSAP", "/RSAPServer")
    except dbus.DBusException:
        print_exc()
        sys.exit(1)

    # ... or create an Interface wrapper for the remote object
    iface = dbus.Interface(remote_object, "org.smart_e.RSAPServer")
    iface.InitCard()

    for command in commands:
        toSend = command #HWHEADER+[len(command)]+command+[0x00]
        print "<", toHexString(toSend)
        apduResponse = iface.processAPDU(toSend)
        bArrResp = list(bytearray(apduResponse))
        print ">", toHexString(bArrResp)
        # print ">", toHexString(apduResponse)

    if sys.argv[1:] == ['--exit-service']:
        iface.Exit()

if __name__ == '__main__':
    main()
