#!/usr/bin/env python

import threading
import Queue
import math
import numpy as np

from smartcard.CardType import AnyCardType
from smartcard.CardRequest import CardRequest
from smartcard.CardConnectionObserver import CardConnectionObserver
from smartcard.CardConnectionObserver import ConsoleCardConnectionObserver
from smartcard.util import toHexString

from smartcard.sw.ErrorCheckingChain import ErrorCheckingChain
from smartcard.sw.ISO7816_4ErrorChecker import ISO7816_4ErrorChecker
from smartcard.sw.ISO7816_8ErrorChecker import ISO7816_8ErrorChecker
from smartcard.sw.SWExceptions import SWException, WarningProcessingException

import zmq
import zmq.auth
import sys
import logging
import os
from zmq.auth.thread import ThreadAuthenticator

class RSAPMessageProtocol:
    # Message is of a format:
    # |  1  |  1   |    2   |        varies          |
    #  msgID #param reserved     payload 
    #
    # Payload (parameter) looks like
    # |  1  |  1  |    2    |     varies      | 0-3 |  
    #  param  rsv. paramLen    parameter value  padding
    #   ID
    # The length of each parameter will be a multiple of 4 bytes - use padding to reach that
    def __init__(self):
        self.messageID = {
            0x00: 'CONNECT_REQ',
            0x01: 'CONNECT_RESP',
            0x02: 'DISCONNECT_REQ',
            0x03: 'DISCONNECT_RESP',
            0x04: 'DISCONNECT_IND',
            0x05: 'TRANSFER_APDU_REQ',
            0x06: 'TRANSFER_APDU_RESP',
            0x07: 'TRANSFER_ATR_REQ',
            0x08: 'TRANSFER_ATR_RESP',
            0x09: 'POWER_SIM_OFF_REQ',
            0x0A: 'POWER_SIM_OFF_RESP',
            0x0B: 'POWER_SIM_ON_REQ',
            0x0C: 'POWER_SIM_ON_RESP',
            0x0D: 'RESET_SIM_REQ',
            0x0E: 'RESET_SIM_RESP',
            0x0F: 'TRANSFER_CARD_READER_STATUS_REQ',
            0x10: 'TRANSFER_CARD_READER_STATUS_RESP',
            0x11: 'STATUS_IND',
            0x12: 'ERROR_RESP',
            0x13: 'SET_TRANSPORT_PROTOCOL_REQ',
            0x14: 'SET_TRANSPORT_PROTOCOL_RESP'
        }
        self.messageName = dict((v,k) for k, v in self.messageID.iteritems())
        self.parameterID = {
            0x00: 'MaxMsgSize',
            0x01: 'ConnectionStatus',
            0x02: 'ResultCode',
            0x03: 'DisconnectionType',
            0x04: 'CommandAPDU',
            0x10: 'CommandAPDU7816',
            0x05: 'ResponseAPDU',
            0x06: 'ATR',
            0x07: 'CardReaderStatus',
            0x08: 'StatusChange',
            0x09: 'TransportProtocol'
        }
        self.parameterName = dict((v,k) for k, v in self.parameterID.iteritems())
        self.msgReserved = [0x00, 0x00]
        self.paramReserved = [0x00]

        self.steps = [
            [self.messageName['CONNECT_REQ']],
            [self.messageName['TRANSFER_ATR_REQ']],
            [self.messageName['TRANSFER_APDU_REQ']]
        ]
        self.currentStep = 0

    def isMessageComplete(self, message):
        if (len(message) < 4):
            return False
        mID = message[0]
        parameters = message[1]
        if parameters == 0:
            return True
        currentPos = 4
        for i in range(parameters):
            if (len(message) < currentPos+4):
                return False
            # Length of the parameter as encoded in the message
            paramLen = (message[currentPos+2] << 8) + message[currentPos+3]
            # Payload (parameter + padding) length has to be a multiple of 4
            fullLen = int(math.ceil(paramLen/float(4))*4)
            if (len(message) < currentPos+4+fullLen):
                return False
            # Move onto the next parameter
            currentPos = currentPos+4+fullLen
        return True

    def getExpectedCommands(self):
        return self.steps[self.currentStep]

    def advanceStep(self):
        if (self.currentStep < len(self.steps)-1):
            self.currentStep = self.currentStep + 1

    def expectedCommand(self, message):
        currentlyExpected = self.steps[self.currentStep]
        for expected in currentlyExpected:
            if expected == message[0]:
                return True
        return False


    def printMessage(self, message):
        print toHexString(message)
        mID = message[0]
        parameters = message[1]
        print self.messageID[mID], ", ", parameters, " parameters:"
        currentPos = 4
        for i in range(parameters):
            # Length of the parameter as encoded in the message
            paramLen = (message[currentPos+2] << 8) + message[currentPos+3]
            # Payload (parameter + padding) length has to be a multiple of 4
            fullLen = int(math.ceil(paramLen/float(4))*4)
            paramVal = message[currentPos+4:currentPos+4+paramLen]
            print self.parameterID[message[currentPos]], " = ", toHexString(paramVal), "(length =", paramLen, ")"
            # Move onto the next parameter
            currentPos = currentPos+4+fullLen
        return True

    def decodeCONNECT_REQ(self, message):
        if (self.messageID[message[0]] != 'CONNECT_REQ'):
            raise NameError('Not a CONNECT_REQ message')
        if (self.parameterID[message[4]] == 'MaxMsgSize'):
            return message[6]<<8+message[7]

    def generateCONNECT_RESP(self, connect_req):
        mID = self.messageName['CONNECT_RESP']
        params = 1
        paramID = self.parameterName['ConnectionStatus']
        paramLen = 1
        #MaxMsgSize = decodeCONNECT_REQ(connect_req)
        #pValue = [MaxMsgSize>>4, MaxMsgSize&0x1111]
        pValue = [0x00]
        parameter = [paramID]+self.paramReserved+[0x00, paramLen]+pValue
        return [mID]+[params]+self.msgReserved+self.addParameterPadding(parameter)

    def generateSTATUS_IND(self):
        mID = self.messageName['STATUS_IND']
        params = 1
        paramID = self.parameterName['StatusChange']
        paramLen = 1
        StatusChange = 0x01
        pValue = [StatusChange]
        parameter = [paramID]+self.paramReserved+[0x00, paramLen]+pValue
        return [mID]+[params]+self.msgReserved+self.addParameterPadding(parameter)

    def generateTRANSFER_APDU_RESP(self, apdu):
        mID = self.messageName['TRANSFER_APDU_RESP']
        params = 2
        param1ID = self.parameterName['ResultCode']
        param1Len = 1
        #TODO
        ResultCode = 0x00
        parameter1 = self.addParameterPadding([param1ID]+self.paramReserved+[0x00, param1Len]+[ResultCode])
        param2ID = self.parameterName['ResponseAPDU']
        param2Len = len(apdu)
        parameter2 = self.addParameterPadding([param2ID]+self.paramReserved+[param2Len>>8, param2Len&0xFF]+apdu)
        return [mID]+[params]+self.msgReserved+parameter1+parameter2

    def extractAPDU_REQ(self, message):
        if (self.messageID[message[0]] != 'TRANSFER_APDU_REQ'):
            raise NameError('Not a TRANSFER_APDU_REQ message')
        if (self.parameterID[message[4]] == 'CommandAPDU' or self.parameterID[message[4]] == 'CommandAPDU7816'):
            length = (message[6] << 8) + message[7]
            apduReq = message[8:8+length]
            return apduReq

    def generateTRANSFER_ATR_RESP(self, atr):
        mID = self.messageName['TRANSFER_ATR_RESP']
        params = 2
        param1ID = self.parameterName['ResultCode']
        param1Len = 1
        #TODO
        ResultCode = 0x00
        parameter1 = self.addParameterPadding([param1ID]+self.paramReserved+[0x00, param1Len]+[ResultCode])
        param2ID = self.parameterName['ATR']
        param2Len = len(atr)
        print "ATR length=", param2Len, "or [", param2Len>>8, param2Len&0xFF,"]"
        parameter2 = self.addParameterPadding([param2ID]+self.paramReserved+[param2Len>>8, param2Len&0xFF]+atr)
        return [mID]+[params]+self.msgReserved+parameter1+parameter2

    def addParameterPadding(self, parameter):
        needLength = int(math.ceil(len(parameter)/float(4))*4)
        for i in range(len(parameter), needLength):
            parameter = parameter + [0x00]
        return parameter
    





class Server():
    def __init__(self):
        cardtype = AnyCardType()
        cardrequest = CardRequest(timeout=10, cardType=cardtype)
        print "waiting for card"
        self.cardservice = cardrequest.waitforcard()
        # errorchain=[]
        # errorchain=[ ErrorCheckingChain( errorchain, ISO7816_8ErrorChecker() ),
        #              ErrorCheckingChain( errorchain, ISO7816_4ErrorChecker() ) ]
        # self.cardservice.connection.setErrorCheckingChain( errorchain )
        observer=ConsoleCardConnectionObserver()
        self.cardservice.connection.addObserver( observer )
        print "Connecting cardservice"
        self.cardservice.connection.connect()

        self.rsap = RSAPMessageProtocol()

        self.buffer = []
        self.state = "CONNECT_REQ"

    def process(self, inCommand):
        inMessage = list(bytearray(inCommand))
        self.buffer += inMessage
        print "Current buffer", toHexString(self.buffer)
        if not self.rsap.isMessageComplete(self.buffer):
            print "Message incomplete, waiting"
            return []
        print "Message complete"
        message = self.buffer
        self.buffer = []
        self.rsap.printMessage(message)
        if (not self.rsap.expectedCommand(message)):
            print "Not an expected message!"

        rsap = self.rsap

        if (message[0] == rsap.messageName['CONNECT_REQ']):
            print "Restart from CONNECT_REQ"
            rsap.currentStep = 0

        if (rsap.currentStep == 0):
            response1 = rsap.generateCONNECT_RESP(message)
            rsap.printMessage(response1)
            # TODO: return this as well... somehow!
            response2 = rsap.generateSTATUS_IND()
            rsap.printMessage(response2)
            rsap.advanceStep()
            return response2

        if (rsap.currentStep == 1):
            response = rsap.generateTRANSFER_ATR_RESP(self.cardservice.connection.getATR())
            rsap.printMessage(response)
            rsap.advanceStep()
            return response

        if (rsap.currentStep == 2):
            apduRequest = rsap.extractAPDU_REQ(message)
            resp, sw1, sw2 = self.cardservice.connection.transmit(apduRequest)
            apduResponse = resp + [sw1, sw2]
            if sw1 == 0x61:
                apdu = [0x00, 0xC0, 0x00, 0x00, sw2]
                resp, sw1, sw2 = self.cardservice.connection.transmit(apdu)
                apduResponse = resp + [sw1, sw2]
            response = rsap.generateTRANSFER_APDU_RESP(apduResponse)
            rsap.printMessage(response)
            rsap.advanceStep()
            return response

        return []

def run():
    ''' Run secure server '''

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

    server = ctx.socket(zmq.REP)

    server_secret_file = os.path.join(secret_keys_dir, "server.key_secret")
    server_public, server_secret = zmq.auth.load_certificate(server_secret_file)
    server.curve_secretkey = server_secret
    server.curve_publickey = server_public
    server.curve_server = True  # must come before bind
    server.bind('tcp://*:9000')

    RSAPServer = Server()

    while True:
        print("recv")
        message = server.recv_json()
        print("Received request: %s" % message)
        result = RSAPServer.process(message)
        server.send_json(result)

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
