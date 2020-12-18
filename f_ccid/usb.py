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
import functionfs
from functionfs import ch9

class USBICCDescriptor(functionfs.USBDescriptorHeader):
    """
    USB-ICC function descriptor structure.

    As of USB-ICC ICCD Rev 1.0 .
    """
    # Descriptor is class-specific type 1
    _bDescriptorType = ch9.USB_TYPE_CLASS | 1
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
assert ctypes.sizeof(USBICCDescriptor) == 54

CCID_CLASS_AUTO_CONF_ATR   = 0x00000002
CCID_CLASS_AUTO_ACTIVATION = 0x00000004
CCID_CLASS_AUTO_VOLTAGE    = 0x00000008
CCID_CLASS_AUTO_CLOCK      = 0x00000010
CCID_CLASS_AUTO_BAUD       = 0x00000020
CCID_CLASS_AUTO_PPS_PROP   = 0x00000040
CCID_CLASS_AUTO_PPS_CUR    = 0x00000080
CCID_CLASS_CAN_STOP_CLOCK  = 0x00000100
CCID_CLASS_NODE_ADDR       = 0x00000200
CCID_CLASS_AUTO_IFSD       = 0x00000400
#CCID_CLASS_                = 0x00000800
CCID_CLASS_TPDU            = 0x00010000
CCID_CLASS_SHORT_APDU      = 0x00020000
CCID_CLASS_EXTENDED_APDU   = 0x00040000

CCID_VOLTAGE_SUPPORT_5V = 1
CCID_VOLTAGE_SUPPORT_3V = 2
CCID_VOLTAGE_SUPPORT_1_8V = 3

CCID_PROTOCOL_T0 = 0x01 # byte units
CCID_PROTOCOL_T1 = 0x02 # packet units

CCID_REQ_ABORT = 0x01
CCID_REQ_GET_CLOCK_FREQUENCIES = 0x02
CCID_REQ_GET_DATA_RATES = 0x03

STATE_INITIAL = 0
STATE_APDU_COMMAND_WAIT = 1
STATE_APDU_COMMAND_PARTIAL = 2
STATE_APDU_RESPONSE_PARTIAL = 3

MESSAGE_TYPE_SLOT_CHANGE = 0x50
MESSAGE_TYPE_HARDWARE_ERROR = 0x51

MESSAGE_TYPE_POWER_ON = 0x62
MESSAGE_TYPE_POWER_OFF = 0x63
MESSAGE_TYPE_GET_SLOT_STATUS = 0x65
MESSAGE_TYPE_XFR_BLOCK = 0x6f
MESSAGE_TYPE_GET_PARAMETERS = 0x6c
MESSAGE_TYPE_RESET_PARAMETERS = 0x6d
MESSAGE_TYPE_SET_PARAMETERS = 0x61
MESSAGE_TYPE_ESCAPE = 0x6b
MESSAGE_TYPE_ICC_CLOCK = 0x6e
MESSAGE_TYPE_T0_APDU = 0x6a
MESSAGE_TYPE_SECURE = 0x69
MESSAGE_TYPE_MECHANICAL = 0x71
MESSAGE_TYPE_ABORT = 0x72
MESSAGE_TYPE_SET_RATE_AND_CLOCK = 0x73

MESSAGE_TYPE_DATA_BLOCK = 0x80
MESSAGE_TYPE_SLOT_STATUS = 0x81
MESSAGE_TYPE_PARAMETERS = 0x82
MESSAGE_TYPE_ESCAPE_RESPONSE = 0x83
MESSAGE_TYPE_RATE_AND_CLOCK = 0x84

CLOCK_STATUS_RUNNING = 0
CLOCK_STATUS_STOPPED_L = 1
CLOCK_STATUS_STOPPED_H = 2
CLOCK_STATUS_STOPPED = 3

CHAIN_BEGIN_AND_END = 0
CHAIN_BEGIN = 1
CHAIN_END = 2
CHAIN_INTERMEDIATE = 3
CHAIN_CONTINUE = 0x10

CHAIN_TO_START_STOP_DICT = {
    CHAIN_BEGIN_AND_END: (True,  True),
    CHAIN_BEGIN:         (True,  False),
    CHAIN_END:           (False, True),
    CHAIN_INTERMEDIATE:  (False, False),
}
START_STOP_TO_CHAIN_DICT = {
    y: x
    for x, y in CHAIN_TO_START_STOP_DICT.items()
}

DATA_MAX_LENGTH = 65538

ICC_STATUS_ACTIVE = 0
ICC_STATUS_INACTIVE = 1
ICC_STATUS_NOT_PRESENT = 2

COMMAND_STATUS_OK = 0
COMMAND_STATUS_FAILED = 1
COMMAND_STATUS_TIME_EXT = 2

ERROR_CMD_ABORTED = 0xff
ERROR_ICC_MUTE = 0xfe
ERROR_XFR_PARITY_ERROR = 0xfd
ERROR_XFR_OVERRUN = 0xfc
ERROR_HW_ERROR = 0xfb
ERROR_BAD_ATR_TS = 0xf8
ERROR_BAD_ATR_TCK = 0xf7
ERROR_ICC_PROTOCOL_NOT_SUPPORTED = 0xf6
ERROR_ICC_CLASS_NOT_SUPPORTED = 0xf5
ERROR_PROCEDURE_BYTE_CONFLICT = 0xf4
ERROR_DEACTIVATED_PROTOCOL = 0xf3
ERROR_BUSY_WITH_AUTO_SEQUENCE = 0xf2
ERROR_PIN_TIMEOUT = 0xf0
ERROR_PIN_CANCELLED = 0xef
ERROR_CMD_SLOT_BUSY = 0xe0
ERROR_CMD_NOT_SUPPORTED = 0
ERROR_BAD_LENGTH = 1
ERROR_SLOT_DOES_NOT_EXIST = 5
ERROR_POWERSELECT_NOT_SUPPORTED = 7
ERROR_PROTOCOLNUM_NOT_SUPPORTED = 7 # setParameters
ERROR_BAD_WLEVEL = 8

# All bulk messages should be at least this long, as it is header length.
ICC_BULK_HEAD_LEN = 10
