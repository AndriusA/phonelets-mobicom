#!/usr/bin/env python

import sys
from traceback import print_exc
from smartcard.util import toHexString
import numpy as np

import zmq
import zmq.auth
import sys
import logging
import os
from zmq.auth.thread import ThreadAuthenticator

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


def run():
    ''' Run Ironhouse example '''

    # These direcotries are generated by the generate_certificates script
    base_dir = os.path.dirname(__file__)
    keys_dir = os.path.join(base_dir, 'certificates')
    public_keys_dir = os.path.join(base_dir, 'public_keys')
    secret_keys_dir = os.path.join(base_dir, 'private_keys')

    if not (os.path.exists(keys_dir) and os.path.exists(keys_dir) and os.path.exists(keys_dir)):
        logging.critical("Certificates are missing - run generate_certificates.py script first")
        sys.exit(1)

    ctx = zmq.Context().instance()

    # Start an authenticator for this context.
    auth = ThreadAuthenticator(ctx)
    auth.start()
    # auth.allow('127.0.0.1')
    # Tell authenticator to use the certificate in a directory
    auth.configure_curve(domain='*', location=public_keys_dir)

    client = ctx.socket(zmq.REQ)

    # We need two certificates, one for the client and one for
    # the server. The client must know the server's public key
    # to make a CURVE connection.
    client_secret_file = os.path.join(secret_keys_dir, "client.key_secret")
    client_public, client_secret = zmq.auth.load_certificate(client_secret_file)
    client.curve_secretkey = client_secret
    client.curve_publickey = client_public

    server_public_file = os.path.join(public_keys_dir, "server.key")
    server_public, _ = zmq.auth.load_certificate(server_public_file)
    # The client must know the server's public key to make a CURVE connection.
    client.curve_serverkey = server_public
    client.connect('tcp://192.168.0.20:9000')

    for command in commands:
        print "<", toHexString(command)
        client.send_json(command)
        apduResponse = client.recv_json()
        bArrResp = list(bytearray(apduResponse))
        print ">", toHexString(bArrResp)
        # print ">", toHexString(apduResponse)
    
    # stop auth thread
    auth.stop()

if __name__ == '__main__':
    if zmq.zmq_version_info() < (4,0):
        raise RuntimeError("Security is not supported in libzmq version < 4.0. libzmq version {0}".format(zmq.zmq_version()))

    if '-v' in sys.argv:
        level = logging.DEBUG
    else:
        level = logging.INFO

    logging.basicConfig(level=level, format="[%(levelname)s] %(message)s")

    run()
