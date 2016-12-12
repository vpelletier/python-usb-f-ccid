# Copyright (C) 2016-2017  Vincent Pelletier <plr.vincent@gmail.com>
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
import select
from . import functionfs
import ctypes

class USBICCDescriptor(functionfs.LittleEndianDescriptorStructure):
    _bDescriptorType = 0x21
    _fields_ = [
        ('bcdCCID', ctypes.c_ushort),
        ('bMaxSlotIndex', ctypes.c_ubyte),
        ('bVoltageSupport', ctypes.c_ubyte),
        ('dwProtocols', ctypes.c_uint),
        ('dwDefaultClock', ctypes.c_uint),
        ('dwMaximumClock', ctypes.c_uint),
        ('bNumClockSupported', ctypes.c_ubyte),
        ('dwDataRate', ctypes.c_uint),
        ('dwMaxDataRate', ctypes.c_uint),
        ('bNumDataRatesSupported', ctypes.c_ubyte),

        ('dwMaxIFSD', ctypes.c_uint),
        ('dwSynchProtocols', ctypes.c_uint),
        ('dwMechanical', ctypes.c_uint),
        ('dwFeatures', ctypes.c_uint),
        ('dwMaxCCIDMessageLength', ctypes.c_uint),
        ('bClassGetResponse', ctypes.c_ubyte),
        ('bClassEnvelope', ctypes.c_ubyte),
        ('wLcdLayout', ctypes.c_ushort),
        ('bPinSupport', ctypes.c_ubyte),
        ('bMaxCCIDBusySlots', ctypes.c_ubyte),
    ]

INTERFACE_DESCRIPTOR = functionfs.getDescriptor(
    functionfs.USBInterfaceDescriptor,
    bInterfaceNumber=0,
    bAlternateSetting=0,
    bNumEndpoints=2, # bulk-IN, bulk-OUT
    bInterfaceClass=0x0b, # Smart Card Device Class
    bInterfaceSubClass=0,
    bInterfaceProtocol=0, # bulk pair, optional interrupt
    iInterface=1,
)

ICC_DESCRIPTOR = functionfs.getDescriptor(
    USBICCDescriptor,
    bcdCCID=0x0110,
    bMaxSlotIndex=0,
    bVoltageSupport=1,
    dwProtocols=2, # Protocol T=1
    dwDefaultClock=0xdfc,
    dwMaximumClock=0xdfc,
    bNumClockSupported=0,
    dwDataRate=0x2580,
    dwMaxDataRate=0x2580,
    bNumDataRatesSupported=0,

    dwMaxIFSD=0xfe, # For Protocol T=1
    dwSynchProtocols=0,
    dwMechanical=0,
    dwFeatures=0x40840, # Short and extended APDU level exchanges
    dwMaxCCIDMessageLength=65544 + 10,
    bClassGetResponse=0xff,
    bClassEnvelope=0xff,
    wLcdLayout=0,
    bPinSupport=0,
    bMaxCCIDBusySlots=1,
)

EP_BULK_OUT_DESCRIPTOR = functionfs.getDescriptor(
    functionfs.USBEndpointDescriptorNoAudio,
    bEndpointAddress=1 | functionfs.USB_DIR_OUT,
    bmAttributes=2,
    wMaxpacketSize=512,
    bInterval=0,
)

EP_BULK_IN_DESCRIPTOR = functionfs.getDescriptor(
    functionfs.USBEndpointDescriptorNoAudio,
    bEndpointAddress=2 | functionfs.USB_DIR_IN,
    bmAttributes=2,
    wMaxpacketSize=512,
    bInterval=0,
)

# XXX: Unused
#EP_INTR_IN_DESCRIPTOR = functionfs.getDescriptor(
#    functionfs.USBEndpointDescriptorNoAudio,
#    bEndpointAddress=3 | functionfs.USB_DIR_IN,
#    bmAttributes=3,
#    wMaxpacketSize=64,
#    bInterval=255,
#)

DESC_LIST = (
    INTERFACE_DESCRIPTOR,
    ICC_DESCRIPTOR,
    EP_BULK_OUT_DESCRIPTOR,
    EP_BULK_IN_DESCRIPTOR,
)

STATE_INITIAL = 0
STATE_APDU_COMMAND_WAIT = 1
STATE_APDU_COMMAND_PARTIAL = 2
STATE_APDU_RESPONSE_PARTIAL = 3

MESSAGE_TYPE_POWER_ON = 0x62
MESSAGE_TYPE_POWER_OFF = 0x63
MESSAGE_TYPE_XFR_BLOCK = 0x6f
MESSAGE_TYPE_DATA_BLOCK = 0x80
MESSAGE_TYPE_SLOT_STATUS = 0x81

CHAIN_BEGIN_AND_END = 0
CHAIN_BEGIN = 1
CHAIN_END = 2
CHAIN_INTERMEDIATE = 3
CHAIN_CONTINUE = 0x10

ICC_STATUS_ACTIVE = 0
ICC_STATUS_INACTIVE = 1
ICC_STATUS_NOT_PRESENT = 2

COMMAND_STATUS_OK = 0
COMMAND_STATUS_FAILED = 1
COMMAND_STATUS_TIME_EXT = 2

ERROR_OK = 0
ERROR_ICC_MUTE = -2
ERROR_XFR_OVERRUN = -4
ERROR_HW_ERROR = -5

# MESSAGE_TYPE: (ICCDBulkMessageHead.u.?, init_kw, has_payload)
_BULK_MESSAGE_TYPE_INIT = {
    MESSAGE_TYPE_POWER_ON: ('power_on', (('bReserved', 1), ('abRFU', (0, 0))), False),
    MESSAGE_TYPE_POWER_OFF: ('power_off', (('abRFU', (0, 0, 0)), ), False),
    MESSAGE_TYPE_XFR_BLOCK: ('xfr_block', (('bReserved', 0), ), True),
    MESSAGE_TYPE_DATA_BLOCK: ('data_block', (), True),
    MESSAGE_TYPE_SLOT_STATUS: ('slot_status', (('bReserved', 0), ), False),
}

class ICCDBulkMessageHead(ctypes.LittleEndianStructure):
    _pack_ = 1
    _fields_ = [
        ('bMessageType', ctypes.c_ubyte),
        ('dwLength', ctypes.c_uint),
        ('bSlot', ctypes.c_ubyte),
        ('bSeq', ctypes.c_ubyte),
        (
            'u',
            type(
                'ICCDBulkMessageUnion',
                (ctypes.Union, ),
                {
                    '_fields_': [
                        (
                            'power_on',
                            type(
                                'ICCDBulkMessagePowerOn',
                                (ctypes.LittleEndianStructure, ),
                                {
                                    '_pack_': 1,
                                    '_fields_': [
                                        ('bReserved', ctypes.c_ubyte),
                                        ('abRFU', ctypes.c_ubyte * 2),
                                    ],
                                },
                            ),
                        ),
                        (
                            'power_off',
                            type(
                                'ICCDBulkMessagePowerOff',
                                (ctypes.LittleEndianStructure, ),
                                {
                                    '_pack_': 1,
                                    '_fields_': [
                                        ('abRFU', ctypes.c_ubyte * 3),
                                    ],
                                },
                            ),
                        ),
                        (
                            'xfr_block',
                            type(
                                'ICCDBulkMessageXfrBlock',
                                (ctypes.LittleEndianStructure, ),
                                {
                                    '_pack_': 1,
                                    '_fields_': [
                                        ('bReserved', ctypes.c_ubyte),
                                        ('wLevelParameter', ctypes.c_ushort),
                                    ],
                                },
                            ),
                        ),
                        (
                            'data_block',
                            type(
                                'ICCDBulkMessageDataBlock',
                                (ctypes.LittleEndianStructure, ),
                                {
                                    '_fields_': [
                                        ('bmICCStatus', ctypes.c_ubyte, 2),
                                        ('bmReserved', ctypes.c_ubyte, 4),
                                        ('bmCommandStatus', ctypes.c_ubyte, 2),
                                        ('bError', ctypes.c_byte),
                                        ('bChainParameter', ctypes.c_ubyte),
                                    ],
                                },
                            ),
                        ),
                        (
                            'slot_status',
                            type(
                                'ICCDBulkMessageSlotStatus',
                                (ctypes.LittleEndianStructure, ),
                                {
                                    '_pack_': 1,
                                    '_fields_': [
                                        ('bmICCStatus', ctypes.c_ubyte, 2),
                                        ('bmReserved', ctypes.c_ubyte, 4),
                                        ('bmCommandStatus', ctypes.c_ubyte, 2),
                                        ('bError', ctypes.c_byte),
                                        ('bReserved', ctypes.c_ubyte),
                                    ],
                                },
                            ),
                        ),
                    ],
                },
            ),
        ),
    ]

ICC_BULK_HEAD_LEN = 10
assert ctypes.sizeof(ICCDBulkMessageHead) == ICC_BULK_HEAD_LEN

def getICCDBulkMessage(message_type, slot, seq, data=b'', **kw):
    union_key, union_init, has_payload = _BULK_MESSAGE_TYPE_INIT[message_type]
    if data and not has_payload:
        raise ValueError(
            'Message type 0x%02x cannot have a payload' % (
                message_type,
            ),
        )
    for key, value in union_init:
        kw.setdefault(key, value)
    return functionfs.serialise(ICCDBulkMessageHead(
        bMessageType=message_type,
        dwLength=ctypes.sizeof(ICCDBulkMessageHead) + len(data),
        bSeq=seq,
        **{
            union_key: kw,
        }
    )) + data

# From gnuk:
# ATR (Answer To Reset) string
# TS = 0x3b: Direct convention
# T0 = 0xda: TA1, TC1 and TD1 follow, 10 historical bytes
# TA1 = 0x11: FI=1, DI=1
# TC1 = 0xff
# TD1 = 0x81: TD2 follows, T=1
# TD2 = 0xb1: TA3, TB3 and TD3 follow, T=1
# TA3 = 0xFE: IFSC = 254 bytes
# TB3 = 0x55: BWI = 5, CWI = 5   (BWT timeout 3.2 sec)
# TD3 = 0x1f: TA4 follows, T=15
# TA4 = 0x03: 5V or 3.3V
# Minimum: 0x3b, 0x8a, 0x80, 0x01
ATR_HEAD = b'\x3b\xda\x11\xff\x81\xb1\xfe\x55\x1f\x03'

# 0x0a
# 0x00,
# 0x31, 0x84,                   Full DF name, GET DATA, MF
# 0x73,
# 0x80, 0x01, 0x80,             Full DF name
#                               1-byte
#                               Command chaining, No extended Lc and Le
# 0x00,
# 0x90, 0x00                    Status info
HISTORICAL_BYTES = b'\x0a\x00\x31\x84\x73\x80\x01\x80\x00\x90\x00'

if sys.version_info[:2] > (2, 7):
    # In python 3, items of bytes are ints
    def _xor(byte_value):
        result = 0
        for item in byte_value:
            result ^= item
        return result
else:
    # In python 2, items of bytes are chars
    def _xor(byte_value):
        result = 0
        for item in byte_value:
            result ^= ord(item)
        return result
ATR_DATA = ATR_HEAD + HISTORICAL_BYTES
ATR_DATA += _xor(ATR_DATA)

class ICCDFunction(functionfs.Function):
    _state = None

    def __init__(self, path):
        super(ICCDFunction, self).__init__(
            path,
            fs_list=DESC_LIST,
            hs_list=DESC_LIST,
            ss_list=DESC_LIST,
            lang_dict={
                0x0409: (
                    'Edison ICCD'.decode('ASCII'),
                ),
            },
        )

    def onEnable(self):
        self._state = STATE_INITIAL

    def onDisable(self):
        self._state = None

    __event_dict = {
        MESSAGE_TYPE_POWER_ON: 'onPowerOn',
        MESSAGE_TYPE_POWER_OFF: 'onPowerOff',
        MESSAGE_TYPE_XFR_BLOCK: 'onXfrBlock',
    }

    def __processICCD(self, iterator):
        infile = self.getEndpoint(1)
        outfile = self.getEndpoint(2)
        iccd_head_buf = bytearray(ICC_BULK_HEAD_LEN)
        icc_head = ICCDBulkMessageHead.frombuffer(iccd_head_buf)
        event_dict = self.__event_dict
        for _ in iterator:
            infile.readinto(iccd_head_buf)
            message_type = icc_head.bMessageType
            try:
                method_id = event_dict[message_type]
            except KeyError:
                infile.halt()
                infile.flushFIFO()
                continue
            if icc_head.bSlot != 0:
                infile.halt()
                infile.flushFIFO()
                continue
            if icc_head.dwLength:
                data = infile.read(icc_head.dwLength)
            else:
                data = ''
            kw = {}
            if message_type == MESSAGE_TYPE_XFR_BLOCK:
                kw['level'] = icc_head.u.xfr_block.wLevelParameter
            try:
                # XXX: not nice to rely on called method to set seq...
                response = getattr(self, method_id)(
                    seq=icc_head.bSeq,
                    data=data,
                    **kw
                )
            except BaseException:
                # On *ANY* exception, halt endpoint
                outfile.halt()
                raise
            else:
                outfile.write(response)

    def onPowerOn(self, seq, data):
        self._state = STATE_INITIAL
        return getICCDBulkMessage(
            message_type=MESSAGE_TYPE_DATA_BLOCK,
            slot=0,
            seq=seq,
            bmICCStatus=ICC_STATUS_ACTIVE,
            bmCommandStatus=COMMAND_STATUS_OK,
            bError=ERROR_OK,
            bChainParameter=CHAIN_BEGIN_AND_END,
            data=ATR_DATA,
        )

    def onPowerOff(self, seq, data):
        self._state = STATE_INITIAL
        return getICCDBulkMessage(
            message_type=MESSAGE_TYPE_SLOT_STATUS,
            slot=0,
            seq=seq,
            bmICCStatus=ICC_STATUS_INACTIVE,
            bmCommandStatus=COMMAND_STATUS_OK,
            bError=ERROR_OK,
        )

    def onXfrBlock(self, seq, level, data):

# Commands used by gnupg's scd
CMD_SELECT_FILE = 0xa4
CMD_VERIFY = 0x20
CMD_CHANGE_REFERENCE_DATA = 0x24
CMD_RESET_RETRY_COUNTER = 0x2c
CMD_GET_DATA = 0xca
CMD_PUT_DATA = 0xda
CMD_MSE = 0x22
CMD_PSO = 0x2a
CMD_INTERNAL_AUTHENTICATE = 0x88
CMD_GENERATE_KEYPAIR = 0x47
CMD_GET_CHALLENGE = 0x84
CMD_READ_BINARY = 0xb0
CMD_READ_RECORD = 0xb2

class APDUHead(ctypes.Structure):
    # XXX: endianness ?
    # XXX: packing ?
    _fields_ = [
        ('class', ctypes.c_ubyte),
        ('ins', ctypes.c_ubyte),
        ('p0', ctypes.c_ubyte),
        ('p1', ctypes.c_ubyte),
    ]
