#!/usr/bin/env python

import threading
import Queue
import math

import gobject
import dbus
import dbus.service
import dbus.mainloop.glib

import zmq
import zmq.auth
import sys
import logging
import os
from zmq.auth.thread import ThreadAuthenticator
from smartcard.util import toHexString

class DemoException(dbus.DBusException):
    _dbus_error_name = 'org.smart_e.DemoException'

class Server(dbus.service.Object):
    def __init__(self):
        bus_name = dbus.service.BusName("org.smart_e.RSAP", bus=dbus.SystemBus())
        dbus.service.Object.__init__(self, bus_name, '/RSAPServer')
        self.buffer = []
        self.state = "CONNECT_REQ"
        self.reqQueue = Queue.Queue()
        self.respQueue = Queue.Queue()

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
        client.connect('tcp://192.168.0.10:9000')

        self.client = client

    @dbus.service.method("org.smart_e.RSAPServer",
                          in_signature='', out_signature='')
    def InitCard(self):
        return

    @dbus.service.method("org.smart_e.RSAPServer",
                         in_signature='ay', out_signature='ay')
    def processAPDU(self, inCommand):
        print 'INCOMING > ', toHexString(list(bytearray(inCommand)))
        relay = []
        for i in inCommand:
            num = i & 0xFF
            relay.append(num)
        self.reqQueue.put(relay)
        # FIXME: the logic is broken - either there is no concurrency, 
        # or no direct matching between FIFO request and response queues
        resp = self.respQueue.get()
        return resp

    def apduProcessor(self):
        while True:
            try:
                inCommand = self.reqQueue.get()
            except Queue.Empty:
                pass
            else:
                resp = self.process(inCommand)
                self.respQueue.put(resp)

    def process(self, inCommand):
        # print "<", toHexString(inCommand)
        self.client.send_json(inCommand)
        apduResponse = self.client.recv_json()
        bArrResp = list(bytearray(apduResponse))
        print "OUTGOING > ", toHexString(bArrResp)
        return apduResponse



if __name__ == '__main__':
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    dbus.mainloop.glib.threads_init()
    RSAPServer = Server()
    gobject.threads_init()
    mainloop = gobject.MainLoop()

    apduProcessor = threading.Thread(target=RSAPServer.apduProcessor)
    apduProcessor.setDaemon(True)
    apduProcessor.start()

    print "Running RSAP service."
    mainloop.run()
