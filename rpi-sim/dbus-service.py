#!/usr/bin/env python

import threading
import Queue
import math

import gobject
import dbus
import dbus.service
import dbus.mainloop.glib
from smartcard.CardType import AnyCardType
from smartcard.CardRequest import CardRequest
from smartcard.CardConnectionObserver import CardConnectionObserver
from smartcard.CardConnectionObserver import ConsoleCardConnectionObserver
from smartcard.util import toHexString

from smartcard.sw.ErrorCheckingChain import ErrorCheckingChain
from smartcard.sw.ISO7816_4ErrorChecker import ISO7816_4ErrorChecker
from smartcard.sw.ISO7816_8ErrorChecker import ISO7816_8ErrorChecker
from smartcard.sw.SWExceptions import SWException, WarningProcessingException

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
        expected = False
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
    




class DemoException(dbus.DBusException):
    _dbus_error_name = 'org.smart_e.DemoException'

class Server(dbus.service.Object):
    def __init__(self):
        bus_name = dbus.service.BusName("org.smart_e.RSAP", bus=dbus.SystemBus())
        dbus.service.Object.__init__(self, bus_name, '/RSAPServer')
        # @dbus.service.method("org.smart_e.RSAPServer",
        #                      in_signature='', out_signature='')
        # def InitCard(self):
        cardtype = AnyCardType()
        cardrequest = CardRequest(timeout=10, cardType=cardtype)
        self.cardservice = cardrequest.waitforcard()
        errorchain=[]
        errorchain=[ ErrorCheckingChain( errorchain, ISO7816_8ErrorChecker() ),
                     ErrorCheckingChain( errorchain, ISO7816_4ErrorChecker() ) ]
        self.cardservice.connection.setErrorCheckingChain( errorchain )
        observer=ConsoleCardConnectionObserver()
        self.cardservice.connection.addObserver( observer )
        self.cardservice.connection.connect()

        self.rsap = RSAPMessageProtocol()

        self.buffer = []
        self.state = "CONNECT_REQ"
        self.reqQueue = Queue.Queue()
        self.respQueue = Queue.Queue()

    @dbus.service.method("org.smart_e.RSAPServer",
                          in_signature='', out_signature='')
    def InitCard(self):
        return

    @dbus.service.method("org.smart_e.RSAPServer",
                         in_signature='ay', out_signature='ay')
    def processAPDU(self, inCommand):
        print 'HARDWARE > ', toHexString(list(bytearray(inCommand)))
        self.reqQueue.put(inCommand)
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
