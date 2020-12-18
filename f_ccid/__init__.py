# Copyright (C) 2016-2020  Vincent Pelletier <plr.vincent@gmail.com>
#
# This file is part of python-usb-f-ccid.
# python-usb-f-ccid is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# python-usb-f-ccid is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with python-usb-f-ccid.  If not, see <http://www.gnu.org/licenses/>.

import ctypes
import errno
from functools import partial
import struct
import functionfs
from functionfs import ch9
from .usb import (
    CCID_CLASS_AUTO_BAUD,
    CCID_CLASS_AUTO_CLOCK,
    CCID_CLASS_AUTO_CONF_ATR,
    CCID_CLASS_AUTO_IFSD,
    CCID_CLASS_AUTO_PPS_PROP,
    CCID_CLASS_AUTO_VOLTAGE,
    CCID_CLASS_EXTENDED_APDU,
    CCID_PROTOCOL_T1,
    CCID_REQ_ABORT,
    CCID_REQ_GET_CLOCK_FREQUENCIES,
    CCID_REQ_GET_DATA_RATES,
    CCID_VOLTAGE_SUPPORT_5V,
    CHAIN_BEGIN_AND_END,
    CHAIN_CONTINUE,
    CHAIN_TO_START_STOP_DICT,
    CLOCK_STATUS_RUNNING,
    CLOCK_STATUS_STOPPED,
    COMMAND_STATUS_FAILED,
    DATA_MAX_LENGTH,
    ERROR_BAD_LENGTH,
    ERROR_BAD_WLEVEL,
    ERROR_CMD_ABORTED,
    ERROR_CMD_NOT_SUPPORTED,
    ERROR_ICC_MUTE,
    ERROR_PROTOCOLNUM_NOT_SUPPORTED,
    ERROR_POWERSELECT_NOT_SUPPORTED,
    ERROR_SLOT_DOES_NOT_EXIST,
    ICC_STATUS_NOT_PRESENT,
    MESSAGE_TYPE_ABORT,
    MESSAGE_TYPE_GET_PARAMETERS,
    MESSAGE_TYPE_GET_SLOT_STATUS,
    MESSAGE_TYPE_ICC_CLOCK,
    MESSAGE_TYPE_MECHANICAL,
    MESSAGE_TYPE_POWER_OFF,
    MESSAGE_TYPE_POWER_ON,
    MESSAGE_TYPE_RESET_PARAMETERS,
    MESSAGE_TYPE_SET_PARAMETERS,
    MESSAGE_TYPE_SET_RATE_AND_CLOCK,
    MESSAGE_TYPE_XFR_BLOCK,
    START_STOP_TO_CHAIN_DICT,
    USBICCDescriptor,
)
from .iccd import (
    ICCDMessageBase,
    ICCDNotifySlotChange,
    ICCDRequestBase,
    ICCD_REQUEST_SET_PARAMETERS_T0_LENGTH,
    ICCD_REQUEST_SET_PARAMETERS_T1_LENGTH,
)
from .slot import ABORT_MARKER, ICCDSlot

class EndpointOUTFile(functionfs.EndpointOUTFile):
    def __init__(self, onComplete, *args, **kw):
        self.onComplete = onComplete
        super().__init__(*args, **kw)

class ICCDFunction(functionfs.Function):
    """
    USB function declaration an request handler implementing the USB SmartCard
    CCID interface class in bulk transfer mode.
    """
    BULK_IN_INDEX = 1
    BULK_OUT_INDEX = 2
    INT_IN_INDEX = 3

    def __init__(self, path, slot_count=1):
        self._enabled = False
        self.slot_list = tuple(
            ICCDSlot(onEvent=self.__notifySlotChange)
            for _ in range(slot_count)
        )
        # Pick the same values as USB-ICC ICCD rev 1.0 . These values are
        # meaningless anyway.
        self._clock_list = clock_list = [3580] # kHz
        self._rate_list = rate_list = [9600] # bps
        # Each slot takes 2 bits, so 4 slots per bmSlotICCState byte.
        interrupt_bytes, remainder = divmod(slot_count, 4)
        if remainder:
            interrupt_bytes += 1
        fs_list, hs_list, ss_list = functionfs.getInterfaceInAllSpeeds(
            interface={
                'bInterfaceClass': ch9.USB_CLASS_CSCID,
                'iInterface': 1,
            },
            endpoint_list=[
                {
                    'endpoint': {
                        'bEndpointAddress': self.BULK_IN_INDEX | ch9.USB_DIR_IN,
                        'bmAttributes': ch9.USB_ENDPOINT_XFER_BULK,
                    },
                },
                {
                    'endpoint': {
                        'bEndpointAddress': self.BULK_OUT_INDEX | ch9.USB_DIR_OUT,
                        'bmAttributes': ch9.USB_ENDPOINT_XFER_BULK,
                    },
                },
                {
                    'endpoint': {
                        'bEndpointAddress': self.INT_IN_INDEX | ch9.USB_DIR_IN,
                        'bmAttributes': ch9.USB_ENDPOINT_XFER_INT,
                        # add bMessageType byte
                        'wMaxPacketSize': interrupt_bytes + 1,
                        'bInterval': 255,
                    },
                },
            ],
            class_descriptor_list=[
                functionfs.getDescriptor(
                    USBICCDescriptor,
                    bcdCCID=0x0110, # CCID spec rev 1.1
                    bMaxSlotIndex=slot_count - 1,
                    bVoltageSupport=CCID_VOLTAGE_SUPPORT_5V,
                    dwProtocols=CCID_PROTOCOL_T1, # T1 only
                    dwDefaultClock=max(clock_list),
                    dwMaximumClock=max(clock_list),
                    bNumClockSupported=(
                        0
                        if len(clock_list) == 1 else
                        len(clock_list)
                    ),
                    dwDataRate=max(rate_list),
                    dwMaxDataRate=max(rate_list),
                    bNumDataRatesSupported=(
                        0
                        if len(rate_list) == 1 else
                        len(rate_list)
                    ),
                    dwMaxIFSD=254, # only possible value for CCID_PROTOCOL_T1
                    dwSynchProtocols=0, # fixed for legacy reasons
                    dwMechanical=0, # fixed for legacy reasons
                    dwFeatures=(
                        CCID_CLASS_AUTO_CONF_ATR |
                        CCID_CLASS_AUTO_VOLTAGE |
                        CCID_CLASS_AUTO_CLOCK |
                        CCID_CLASS_AUTO_BAUD |
                        CCID_CLASS_AUTO_PPS_PROP |
                        CCID_CLASS_AUTO_IFSD |
                        CCID_CLASS_EXTENDED_APDU
                    ),
                    # "extended APDU"'s longest message for BULK mode,
                    # between 261+10 and 65544+10. Pick the largest.
                    dwMaxCCIDMessageLength=65554,
                    bClassGetResponse=0xff,
                    bClassEnvelope=0xff,
                    wLcdLayout=0, # fixed for legacy reasons
                    bPinSupport=0, # fixed for legacy reasons
                    bMaxCCIDBusySlots=slot_count,
                ),
            ],
        )
        super().__init__(
            path,
            fs_list=fs_list,
            hs_list=hs_list,
            ss_list=ss_list,
            lang_dict={
                0x0409: (
                    'python-usb-f-ccid',
                ),
            },
        )

    def onBind(self):
        """
        Called by FunctionFS when the gadget gets bound to the bus.
        """
        super().onBind()
        self.__notifySlotChange()

    def onUnbind(self):
        """
        Called by FunctionFS when the gadget gets unbound from the bus.
        """
        self._enabled = False
        for slot in self.slot_list:
            slot.powerOff()
        super().onUnbind()

    def onEnable(self):
        """
        Called by FunctionFS when this function is enabled by an host.
        """
        super().onEnable()
        self._enabled = True
        self.__notifySlotChange()

    def onDisable(self):
        """
        Called by FunctionFS when this function is disabled by an host.
        """
        self._enabled = False
        for slot in self.slot_list:
            slot.powerOff()
        super().onDisable()

    #def onSuspend(self):
    #    """
    #    Called by FunctionFS when USB bus enters suspended state.
    #    """
    #    for slot in self.slot_list:
    #        slot.powerOff()
    #    super().onSuspend()
    #
    #def onResume(self):
    #    """
    #    Called by FunctionFS when USB bus resumes from suspended state.
    #    """
    #    self.__notifySlotChange()
    #    super().onResume()

    def onSetup(self, request_type, request, value, index, length):
        """
        Called by FunctionFS when a SETUP packet was received for this
        interface or one of its endpoints.
        """
        if (
            request_type & ch9.USB_TYPE_MASK == ch9.USB_TYPE_CLASS and
            request_type & ch9.USB_RECIP_MASK == ch9.USB_RECIP_INTERFACE
        ):
            if (request_type & ch9.USB_DIR_IN) == ch9.USB_DIR_IN:
                if request == CCID_REQ_GET_CLOCK_FREQUENCIES:
                    response = b''.join(
                        (
                            struct.pack('<I', x)
                            for x in self._clock_list
                        ),
                    )[:length]
                    self.ep0.write(response)
                    return
                if request == CCID_REQ_GET_DATA_RATES:
                    response = b''.join(
                        (
                            struct.pack('<I', x)
                            for x in self._rate_list
                        ),
                    )[:length]
                    self.ep0.write(response)
                    return
            else:
                if request == CCID_REQ_ABORT:
                    slot_index = value & 0xff
                    try:
                        slot = self.slot_list[slot_index]
                    except KeyError:
                        self.ep0.halt(request_type)
                    response = slot.abortFromControl(
                        sequence=value >> 8,
                    )
                    if response is not ABORT_MARKER:
                        self.__submitINIterator(
                            self.BULK_IN_INDEX,
                            response,
                        )
                    self.ep0.read(0)
                    return
        super().onSetup(
            request_type,
            request,
            value,
            index,
            length,
        )

    def __submitINIterator(self, endpoint_index, response):
        """
        response must be an iterable of at least one item, each item having
        2 elements:
        - message header: an ICCDMessageBase subclass instance
        - message body: a bytearray or None
        """
        # XXX: handle EAGAIN ? seems unlikely to be reauired...
        buffer_list = []
        for head, body in response:
            buffer_list.append(functionfs.serialise(head))
            if body:
                buffer_list.append(body)
        if not buffer_list:
            raise ValueError('Empty submission')
        self.getEndpoint(endpoint_index).submit(buffer_list)

    def __notifySlotChange(self):
        """
        Update host on all slots which changed since previous notification.
        Does nothing if this function is not enabled by host.
        """
        if self._enabled:
            self.__submitINIterator(
                endpoint_index=self.INT_IN_INDEX,
                response=(
                    (
                        ICCDNotifySlotChange([
                            x.getSlotChangeNotification()
                            for x in self.slot_list
                        ]),
                        None,
                    ),
                ),
            )

    def __onOUTComplete(self, data, status):
        """
        Parses ICCD header, calls onICCDRequest and sends the response(s)
        to host.
        """
        if status < 0:
            if status == -errno.ESHUTDOWN:
                return
            raise IOError(status)
        message = ICCDRequestBase.guess_subtype_from_buffer(data)
        response = self.onICCDRequest(
            head=message,
            body=data[ctypes.sizeof(message):],
        )
        # If we receive ABORT_MARKER it means we received abort through bulk
        # endpoint before receiving it through control endpoint.
        # No response may go out right now, self.onSetup will send it later.
        if response is not ABORT_MARKER:
            self.__submitINIterator(
                endpoint_index=self.BULK_IN_INDEX,
                response=response,
            )

    def getEndpointClass(self, is_in, descriptor):
        if is_in:
            return super().getEndpointClass(is_in=is_in, descriptor=descriptor)
        assert descriptor.bEndpointAddress == self.BULK_OUT_INDEX, (
            descriptor.bEndpointAddress
        )
        return partial(EndpointOUTFile, onComplete=self.__onOUTComplete)

    def onICCDRequest(self, head, body):
        """
        Handles one ICCD request. Inspired by WSGI design.
        """
        message_type = head.bMessageType
        try:
            slot = self.slot_list[head.bSlot]
        except KeyError:
            # No command may run on a non-existant slot
            return (head.getResponse(
                bmICCStatus=ICC_STATUS_NOT_PRESENT,
                bmCommandStatus=COMMAND_STATUS_FAILED,
                bError=ERROR_SLOT_DOES_NOT_EXIST,
            ), )

        getErrorResponse = lambda error, **kw: head.getResponse(
            bmICCStatus=slot.status,
            bmCommandStatus=COMMAND_STATUS_FAILED,
            bError=error,
            **kw
        )
        getResponse = lambda **kw: head.getResponse(
            bmICCStatus=slot.status,
            **kw
        )

        if message_type == MESSAGE_TYPE_ABORT:
            if head.dwLength:
                return (getErrorResponse(ERROR_BAD_LENGTH), )
            return (slot.abortFromBulk(getResponse(
                bClockStatus=CLOCK_STATUS_RUNNING,
            )), )
        elif message_type == MESSAGE_TYPE_POWER_OFF:
            slot.powerOff()
            return (getResponse(bClockStatus=CLOCK_STATUS_RUNNING), )
        elif message_type == MESSAGE_TYPE_GET_SLOT_STATUS:
            if head.dwLength:
                return (getErrorResponse(ERROR_BAD_LENGTH), )
            return (getResponse(bClockStatus=CLOCK_STATUS_RUNNING), )
        elif message_type == MESSAGE_TYPE_SET_RATE_AND_CLOCK: # Single-clock
            return (getErrorResponse(ERROR_CMD_NOT_SUPPORTED), )

        # All other commands require a card being present
        if slot.status == ICC_STATUS_NOT_PRESENT:
            return (getErrorResponse(ERROR_ICC_MUTE), )

        if message_type in (
            MESSAGE_TYPE_GET_PARAMETERS,
            MESSAGE_TYPE_RESET_PARAMETERS,
            MESSAGE_TYPE_SET_PARAMETERS,
        ):
            if message_type == MESSAGE_TYPE_SET_PARAMETERS:
                if head.bProtocolNum != 1:
                    return (getErrorResponse(
                        ERROR_PROTOCOLNUM_NOT_SUPPORTED,
                        bProtocolNum=0, # Placeholder
                    ), )
                if head.dwLength not in (
                    # T0 is not supported anyway
                    #ICCD_REQUEST_SET_PARAMETERS_T0_LENGTH,
                    ICCD_REQUEST_SET_PARAMETERS_T1_LENGTH,
                ):
                    return (getErrorResponse(
                        ERROR_BAD_LENGTH,
                        bProtocolNum=0, # Placeholder
                    ), )
            else:
                if head.dwLength:
                    return (getErrorResponse(
                        ERROR_BAD_LENGTH,
                        bProtocolNum=0, # Placeholder
                    ), )
            return (getResponse(
                bProtocolNum=1,
                bmFindexDindex=0x11,
                bmTCCKST=0x11,
                bGuardTimeT=0xfe,
                bmWaitingIntegersT=0x55,
                bClockStop=CLOCK_STATUS_STOPPED,
                bIFSC=0xfe,
                bNadValue=0,
            ), )
        elif message_type == MESSAGE_TYPE_ICC_CLOCK: # Cannot stop clock
            return (getErrorResponse(ERROR_CMD_NOT_SUPPORTED), )
        elif message_type == MESSAGE_TYPE_MECHANICAL: # No motor in reader
            return (getErrorResponse(ERROR_CMD_NOT_SUPPORTED), )

        # Abort all other commands if there is an abort going on.
        if slot.isAborting():
            return (getErrorResponse(ERROR_CMD_ABORTED), )

        if message_type == MESSAGE_TYPE_POWER_ON:
            if head.dwLength:
                return (getErrorResponse(ERROR_BAD_LENGTH), )
            if head.bPowerSelect:
                return (getErrorResponse(ERROR_POWERSELECT_NOT_SUPPORTED), )
            return (getResponse(
                bChainParameter=CHAIN_BEGIN_AND_END,
                body=slot.powerOn(),
            ), )
        elif message_type == MESSAGE_TYPE_XFR_BLOCK:
            if len(body) != head.dwLength:
                return (getErrorResponse(ERROR_BAD_LENGTH), )
            try:
                start, stop = CHAIN_TO_START_STOP_DICT[head.wLevelParameter]
            except KeyError:
                return (getErrorResponse(ERROR_BAD_WLEVEL), )
            if start:
                slot.clearAPDU()
            slot.storeAPDU(body)
            if stop:
                response_body = slot.runAPDU()
                result = []
                chunk_cutoff = 0
                start = True
                while True:
                    previous_cutoff = chunk_cutoff
                    chunk_cutoff += DATA_MAX_LENGTH
                    chunk = response_body[previous_cutoff:chunk_cutoff]
                    stop = len(chunk) < DATA_MAX_LENGTH
                    result.append(getResponse(
                        bChainParameter=START_STOP_TO_CHAIN_DICT[
                            (start, stop)
                        ],
                        body=chunk,
                    ))
                    if stop:
                        break
                    start = False
                return result
            return (getResponse(bChainParameter=CHAIN_CONTINUE), )
        #elif message_type == MESSAGE_TYPE_ESCAPE: # No special CCID features
        #elif message_type == MESSAGE_TYPE_T0_APDU: # No T=0 protocol support
        #elif message_type == MESSAGE_TYPE_SECURE: # No pin pad
        return (getErrorResponse(ERROR_CMD_NOT_SUPPORTED), )
