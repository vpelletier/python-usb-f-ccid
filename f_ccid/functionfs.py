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
from ctypes import *
import errno
import fcntl
import io
import itertools
import os
import select
import sys
import warnings
import ioctl_opt

__all__ = (
    'Function',

    # XXX: Not very pythonic...
    'getDescriptor',
    'getOSDesc',
    'getOSExtPropDesc',
    'USBInterfaceDescriptor',
    'USBEndpointDescriptorNoAudio',
    'USBEndpointDescriptor',
    'OSExtCompatDesc',
)

class Enum(object):
    def __init__(self, member_dict, scope_dict=None):
        if scope_dict is None:
            # Affect caller's locals, not this module's.
            # pylint: disable=protected-access
            scope_dict = sys._getframe(1).f_locals
            # pylint: enable=protected-access
        forward_dict = {}
        reverse_dict = {}
        next_value = 0
        for name, value in member_dict.items():
            if value is None:
                value = next_value
                next_value += 1
            forward_dict[name] = value
            if value in reverse_dict:
                raise ValueError('Multiple names for value %r: %r, %r' % (
                    value, reverse_dict[value], name
                ))
            reverse_dict[value] = name
            scope_dict[name] = value
        self.forward_dict = forward_dict
        self.reverse_dict = reverse_dict

    def __call__(self, value):
        return self.reverse_dict[value]

    def get(self, value, default=None):
        return self.reverse_dict.get(value, default)

_u8 = c_ubyte
assert sizeof(_u8) == 1
_le16 = c_ushort
assert sizeof(_le16) == 2
_le32 = c_uint
assert sizeof(_le32) == 4

# Translated from linux/usb/ch9.h, minimal subset for functionfs.h
# CONTROL REQUEST SUPPORT

# USB directions
#
# This bit flag is used in endpoint descriptors' bEndpointAddress field.
# It's also one of three fields in control requests bRequestType.
USB_DIR_OUT = 0 # to device
USB_DIR_IN = 0x80 # to host

# USB types, the second of three bRequestType fields
USB_TYPE_MASK = (0x03 << 5)
USB_TYPE_STANDARD = (0x00 << 5)
USB_TYPE_CLASS = (0x01 << 5)
USB_TYPE_VENDOR = (0x02 << 5)
USB_TYPE_RESERVED = (0x03 << 5)

# USB recipients, the third of three bRequestType fields
USB_RECIP_MASK = 0x1f
USB_RECIP_DEVICE = 0x00
USB_RECIP_INTERFACE = 0x01
USB_RECIP_ENDPOINT = 0x02
USB_RECIP_OTHER = 0x03
# From Wireless USB 1.0
USB_RECIP_PORT = 0x04
USB_RECIP_RPIPE = 0x05

# Standard requests, for the bRequest field of a SETUP packet.
#
# These are qualified by the bRequestType field, so that for example
# TYPE_CLASS or TYPE_VENDOR specific feature flags could be retrieved
# by a GET_STATUS request.
USB_REQ_GET_STATUS = 0x00
USB_REQ_CLEAR_FEATURE = 0x01
USB_REQ_SET_FEATURE = 0x03
USB_REQ_SET_ADDRESS = 0x05
USB_REQ_GET_DESCRIPTOR = 0x06
USB_REQ_SET_DESCRIPTOR = 0x07
USB_REQ_GET_CONFIGURATION = 0x08
USB_REQ_SET_CONFIGURATION = 0x09
USB_REQ_GET_INTERFACE = 0x0A
USB_REQ_SET_INTERFACE = 0x0B
USB_REQ_SYNCH_FRAME = 0x0C
USB_REQ_SET_SEL = 0x30
USB_REQ_SET_ISOCH_DELAY = 0x31

USB_REQ_SET_ENCRYPTION = 0x0D # Wireless USB
USB_REQ_GET_ENCRYPTION = 0x0E
USB_REQ_RPIPE_ABORT = 0x0E
USB_REQ_SET_HANDSHAKE = 0x0F
USB_REQ_RPIPE_RESET = 0x0F
USB_REQ_GET_HANDSHAKE = 0x10
USB_REQ_SET_CONNECTION = 0x11
USB_REQ_SET_SECURITY_DATA = 0x12
USB_REQ_GET_SECURITY_DATA = 0x13
USB_REQ_SET_WUSB_DATA = 0x14
USB_REQ_LOOPBACK_DATA_WRITE = 0x15
USB_REQ_LOOPBACK_DATA_READ = 0x16
USB_REQ_SET_INTERFACE_DS = 0x17

# specific requests for USB Power Delivery
USB_REQ_GET_PARTNER_PDO = 20
USB_REQ_GET_BATTERY_STATUS = 21
USB_REQ_SET_PDO = 22
USB_REQ_GET_VDM = 23
USB_REQ_SEND_VDM = 24

# The Link Power Management (LPM) ECN defines USB_REQ_TEST_AND_SET command,
# used by hubs to put ports into a new L1 suspend state, except that it
# forgot to define its number ...

# USB feature flags are written using USB_REQ_{CLEAR,SET}_FEATURE, and
# are read as a bit array returned by USB_REQ_GET_STATUS.  (So there
# are at most sixteen features of each type.)  Hubs may also support a
# new USB_REQ_TEST_AND_SET_FEATURE to put ports into L1 suspend.
USB_DEVICE_SELF_POWERED = 0 # (read only)
USB_DEVICE_REMOTE_WAKEUP = 1 # dev may initiate wakeup
USB_DEVICE_TEST_MODE = 2 # (wired high speed only)
USB_DEVICE_BATTERY = 2 # (wireless)
USB_DEVICE_B_HNP_ENABLE = 3 # (otg) dev may initiate HNP
USB_DEVICE_WUSB_DEVICE = 3 # (wireless)
USB_DEVICE_A_HNP_SUPPORT = 4 # (otg) RH port supports HNP
USB_DEVICE_A_ALT_HNP_SUPPORT = 5 # (otg) other RH port does
USB_DEVICE_DEBUG_MODE = 6 # (special devices only)

# Test Mode Selectors
# See USB 2.0 spec Table 9-7
TEST_J = 1
TEST_K = 2
TEST_SE0_NAK = 3
TEST_PACKET = 4
TEST_FORCE_EN = 5

# New Feature Selectors as added by USB 3.0
# See USB 3.0 spec Table 9-7
USB_DEVICE_U1_ENABLE = 48 # dev may initiate U1 transition
USB_DEVICE_U2_ENABLE = 49 # dev may initiate U2 transition
USB_DEVICE_LTM_ENABLE = 50 # dev may send LTM
USB_INTRF_FUNC_SUSPEND = 0 # function suspend

USB_INTR_FUNC_SUSPEND_OPT_MASK = 0xFF00
# Suspend Options, Table 9-8 USB 3.0 spec
USB_INTRF_FUNC_SUSPEND_LP = (1 << (8 + 0))
USB_INTRF_FUNC_SUSPEND_RW = (1 << (8 + 1))

# Interface status, Figure 9-5 USB 3.0 spec
USB_INTRF_STAT_FUNC_RW_CAP = 1
USB_INTRF_STAT_FUNC_RW = 2

USB_ENDPOINT_HALT = 0 # IN/OUT will STALL

# Bit array elements as returned by the USB_REQ_GET_STATUS request.
USB_DEV_STAT_U1_ENABLED = 2 # transition into U1 state
USB_DEV_STAT_U2_ENABLED = 3 # transition into U2 state
USB_DEV_STAT_LTM_ENABLED = 4 # Latency tolerance messages

# Feature selectors from Table 9-8 USB Power Delivery spec
USB_DEVICE_BATTERY_WAKE_MASK = 40
USB_DEVICE_OS_IS_PD_AWARE = 41
USB_DEVICE_POLICY_MODE = 42
USB_PORT_PR_SWAP = 43
USB_PORT_GOTO_MIN = 44
USB_PORT_RETURN_POWER = 45
USB_PORT_ACCEPT_PD_REQUEST = 46
USB_PORT_REJECT_PD_REQUEST = 47
USB_PORT_PORT_PD_RESET = 48
USB_PORT_C_PORT_PD_CHANGE = 49
USB_PORT_CABLE_PD_RESET = 50
USB_DEVICE_CHARGING_POLICY = 54

class USBCtrlRequest(LittleEndianStructure):
    """
    struct usb_ctrlrequest - SETUP data for a USB device control request
    @bRequestType: matches the USB bmRequestType field
    @bRequest: matches the USB bRequest field
    @wValue: matches the USB wValue field (le16 byte order)
    @wIndex: matches the USB wIndex field (le16 byte order)
    @wLength: matches the USB wLength field (le16 byte order)

    This structure is used to send control requests to a USB device.  It matches
    the different fields of the USB 2.0 Spec section 9.3, table 9-2.  See the
    USB spec for a fuller description of the different fields, and what they are
    used for.

    Note that the driver for any interface can issue control requests.
    For most devices, interfaces don't coordinate with each other, so
    such requests may be made at any time.
    """
    _pack_ = 1
    _fields_ = [
        ('bRequestType', _u8),
        ('bRequest', _u8),
        ('wValue', _le16),
        ('wIndex', _le16),
        ('wLength', _le16),
    ]

# STANDARD DESCRIPTORS ... as returned by GET_DESCRIPTOR, or
# (rarely) accepted by SET_DESCRIPTOR.
#
# Note that all multi-byte values here are encoded in little endian
# byte order "on the wire".  Within the kernel and when exposed
# through the Linux-USB APIs, they are not converted to cpu byte
# order; it is the responsibility of the client code to do this.
# The single exception is when device and configuration descriptors (but
# not other descriptors) are read from usbfs (i.e. /proc/bus/usb/BBB/DDD);
# in this case the fields are converted to host endianness by the kernel.

# Descriptor types ... USB 2.0 spec table 9.5
USB_DT_DEVICE = 0x01
USB_DT_CONFIG = 0x02
USB_DT_STRING = 0x03
USB_DT_INTERFACE = 0x04
USB_DT_ENDPOINT = 0x05
USB_DT_DEVICE_QUALIFIER = 0x06
USB_DT_OTHER_SPEED_CONFIG = 0x07
USB_DT_INTERFACE_POWER = 0x08
# these are from a minor usb 2.0 revision (ECN)
USB_DT_OTG = 0x09
USB_DT_DEBUG = 0x0a
USB_DT_INTERFACE_ASSOCIATION = 0x0b
# these are from the Wireless USB spec
USB_DT_SECURITY = 0x0c
USB_DT_KEY = 0x0d
USB_DT_ENCRYPTION_TYPE = 0x0e
USB_DT_BOS = 0x0f
USB_DT_DEVICE_CAPABILITY = 0x10
USB_DT_WIRELESS_ENDPOINT_COMP = 0x11
USB_DT_WIRE_ADAPTER = 0x21
USB_DT_RPIPE = 0x22
USB_DT_CS_RADIO_CONTROL = 0x23
# From the T10 UAS specification
USB_DT_PIPE_USAGE = 0x24
# From the USB 3.0 spec
USB_DT_SS_ENDPOINT_COMP = 0x30
# From the USB 3.1 spec
USB_DT_SSP_ISOC_ENDPOINT_COMP = 0x31

# Conventional codes for class-specific descriptors.  The convention is
# defined in the USB "Common Class" Spec (3.11).  Individual class specs
# are authoritative for their usage, not the "common class" writeup.
USB_DT_CS_DEVICE = (USB_TYPE_CLASS | USB_DT_DEVICE)
USB_DT_CS_CONFIG = (USB_TYPE_CLASS | USB_DT_CONFIG)
USB_DT_CS_STRING = (USB_TYPE_CLASS | USB_DT_STRING)
USB_DT_CS_INTERFACE = (USB_TYPE_CLASS | USB_DT_INTERFACE)
USB_DT_CS_ENDPOINT = (USB_TYPE_CLASS | USB_DT_ENDPOINT)

class LittleEndianDescriptorStructure(LittleEndianStructure):
    """
    All standard descriptors have these 2 fields at the beginning
    """
    _pack_ = 1
    _fields_ = [
        ('bLength', _u8),
        ('bDescriptorType', _u8),
    ]

###

class USBInterfaceDescriptor(LittleEndianDescriptorStructure):
    """
    USB_DT_INTERFACE: Interface descriptor
    """
    _bDescriptorType = USB_DT_INTERFACE
    _fields_ = [
        ('bInterfaceNumber', _u8),
        ('bAlternateSetting', _u8),
        ('bNumEndpoints', _u8),
        ('bInterfaceClass', _u8),
        ('bInterfaceSubClass', _u8),
        ('bInterfaceProtocol', _u8),
        ('iInterface', _u8),
    ]

# Endpoints
USB_ENDPOINT_NUMBER_MASK = 0x0f # in bEndpointAddress
USB_ENDPOINT_DIR_MASK = 0x80

USB_ENDPOINT_XFERTYPE_MASK = 0x03 # in bmAttributes
USB_ENDPOINT_XFER_CONTROL = 0
USB_ENDPOINT_XFER_ISOC = 1
USB_ENDPOINT_XFER_BULK = 2
USB_ENDPOINT_XFER_INT = 3
USB_ENDPOINT_MAX_ADJUSTABLE = 0x80

# The USB 3.0 spec redefines bits 5:4 of bmAttributes as interrupt ep type.
USB_ENDPOINT_INTRTYPE = 0x30
USB_ENDPOINT_INTR_PERIODIC = (0 << 4)
USB_ENDPOINT_INTR_NOTIFICATION = (1 << 4)

USB_ENDPOINT_SYNCTYPE = 0x0c
USB_ENDPOINT_SYNC_NONE = (0 << 2)
USB_ENDPOINT_SYNC_ASYNC = (1 << 2)
USB_ENDPOINT_SYNC_ADAPTIVE = (2 << 2)
USB_ENDPOINT_SYNC_SYNC = (3 << 2)

USB_ENDPOINT_USAGE_MASK = 0x30
USB_ENDPOINT_USAGE_DATA = 0x00
USB_ENDPOINT_USAGE_FEEDBACK = 0x10
USB_ENDPOINT_USAGE_IMPLICIT_FB = 0x20 # Implicit feedback Data endpoint

# Translated from linux/usb/functionfs.h
DESCRIPTORS_MAGIC = 1
STRINGS_MAGIC = 2
DESCRIPTORS_MAGIC_V2 = 3

Flags = Enum({
    'HAS_FS_DESC': 1,
    'HAS_HS_DESC': 2,
    'HAS_SS_DESC': 4,
    'HAS_MS_OS_DESC': 8,
    'VIRTUAL_ADDR': 16,
    'EVENTFD': 32,
    'ALL_CTRL_RECIP': 64,
    'CONFIG0_SETUP': 128,
})

# Descriptor of an non-audio endpoint
class USBEndpointDescriptorNoAudio(LittleEndianDescriptorStructure):
    """
    USB_DT_ENDPOINT: Endpoint descriptor without audio fields.
    """
    _bDescriptorType = USB_DT_ENDPOINT
    _fields_ = [
        ('bEndpointAddress', _u8),
        ('bmAttributes', _u8),
        ('wMaxPacketSize', _le16),
        ('bInterval', _u8),
    ]

# Descriptor with audio - from ch9.h
class USBEndpointDescriptor(USBEndpointDescriptorNoAudio):
    """
    USB_DT_ENDPOINT: Endpoint descriptor
    """
    _fields_ = [
        # NOTE:  these two are _only_ in audio endpoints.
        ('bRefresh', _u8),
        ('bSynchAddress', _u8),
    ]

class DescsHeadV2(LittleEndianStructure):
    _pack_ = 1
    _fields_ = [
        ('magic', _le32),
        ('length', _le32),
        ('flags', _le32),
    ]
    # _le32 fs_count, hs_count, fs_count; must be included manually in
    # the structure taking flags into consideration.

class DescsHead(LittleEndianStructure):
    _pack_ = 1
    _fields_ = [
        ('magic', _le32),
        ('length', _le32),
        ('fs_count', _le32),
        ('hs_count', _le32),
    ]

class _BCount(LittleEndianStructure):
    _fields_ = [
        ('bCount', _u8),
        ('Reserved', _u8),
    ]

class _Count(Union):
    #_anonymous_ = [
    #    'b',
    #],
    _fields_ = [
        ('b', _BCount),
        ('wCount', _le16),
    ]

class OSDescHeader(LittleEndianStructure):
    """
    MS OS Descriptor header

    OSDesc[] is an array of valid MS OS Feature Descriptors which have one of
    the following formats:

    | off | name            | type | description              |
    |-----+-----------------+------+--------------------------|
    |   0 | inteface        | U8   | related interface number |
    |   1 | dwLength        | U32  | length of the descriptor |
    |   5 | bcdVersion      | U16  | currently supported: 1   |
    |   7 | wIndex          | U16  | currently supported: 4   |
    |   9 | bCount          | U8   | number of ext. compat.   |
    |  10 | Reserved        | U8   | 0                        |
    |  11 | ExtCompat[]     |      | list of ext. compat. d.  |

    | off | name            | type | description              |
    |-----+-----------------+------+--------------------------|
    |   0 | inteface        | U8   | related interface number |
    |   1 | dwLength        | U32  | length of the descriptor |
    |   5 | bcdVersion      | U16  | currently supported: 1   |
    |   7 | wIndex          | U16  | currently supported: 5   |
    |   9 | wCount          | U16  | number of ext. compat.   |
    |  11 | ExtProp[]       |      | list of ext. prop. d.    |
    """
    _pack_ = 1
    _anonymous_ = [
        'u',
    ]
    _fields_ = [
        ('interface', _u8),
        ('dwLength', _le32),
        ('bcdVersion', _le16),
        ('wIndex', _le16),
        ('u', _Count),
    ]

class OSExt(LittleEndianStructure):
    pass

class OSExtCompatDesc(OSExt):
    """
    ExtCompat[] is an array of valid Extended Compatiblity descriptors
    which have the following format:

    | off | name                  | type | description                         |
    |-----+-----------------------+------+-------------------------------------|
    |   0 | bFirstInterfaceNumber | U8   | index of the interface or of the 1st|
    |     |                       |      | interface in an IAD group           |
    |   1 | Reserved              | U8   | 0                                   |
    |   2 | CompatibleID          | U8[8]| compatible ID string                |
    |  10 | SubCompatibleID       | U8[8]| subcompatible ID string             |
    |  18 | Reserved              | U8[6]| 0                                   |
    """
    _fields_ = [
        ('bFirstInterfaceNumber', _u8),
        ('Reserved1', _u8),
        ('CompatibleID', _u8 * 8),
        ('SubCompatibleID', _u8 * 8),
        ('Reserved2', _u8 * 6),
    ]

class OSExtPropDescHead(OSExt):
    """
    ExtProp[] is an array of valid Extended Properties descriptors
    which have the following format:

    | off | name                  | type | description                         |
    |-----+-----------------------+------+-------------------------------------|
    |   0 | dwSize                | U32  | length of the descriptor            |
    |   4 | dwPropertyDataType    | U32  | 1..7                                |
    |   8 | wPropertyNameLength   | U16  | bPropertyName length (NL)           |
    |  10 | bPropertyName         |U8[NL]| name of this property               |
    |10+NL| dwPropertyDataLength  | U32  | bPropertyData length (DL)           |
    |14+NL| bProperty             |U8[DL]| payload of this property            |
    """
    _pack_ = 1
    _fields_ = [
        ('dwSize', _le32),
        ('dwPropertyDataType', _le32),
        ('wPropertyNameLength', _le16),
    ]

class StringsHead(LittleEndianStructure):
    """
    Strings format:

    | off | name       | type                  | description                |
    |-----+------------+-----------------------+----------------------------|
    |   0 | magic      | LE32                  | FUNCTIONFS_STRINGS_MAGIC   |
    |   4 | length     | LE32                  | length of the data chunk   |
    |   8 | str_count  | LE32                  | number of strings          |
    |  12 | lang_count | LE32                  | number of languages        |
    |  16 | stringtab  | StringTab[lang_count] | table of strings per lang  |
    """
    _pack_ = 1
    _fields_ = [
        ('magic', _le32),
        ('length', _le32),
        ('str_count', _le32),
        ('lang_count', _le32),
    ]

class StringBase(LittleEndianStructure):
    """
    For each language there is one stringtab entry (ie. there are lang_count
    stringtab entires).  Each StringTab has following format:

    | off | name    | type              | description                        |
    |-----+---------+-------------------+------------------------------------|
    |   0 | lang    | LE16              | language code                      |
    |   2 | strings | String[str_count] | array of strings in given language |

    For each string there is one strings entry (ie. there are str_count
    string entries).  Each String is a NUL terminated string encoded in
    UTF-8.
    """
    _pack_ = 1
    _fields_ = [
        ('lang', _le16),
    ]


event_type = Enum({
    'BIND': 0,
    'UNBIND': 1,

    'ENABLE': 2,
    'DISABLE': 3,

    'SETUP': 4,

    'SUSPEND': 5,
    'RESUME': 6,
})

class _u(Union):
    _pack_ = 1
    _fields_ = [
        # SETUP: packet; DATA phase i/o precedes next event
        # (setup.bmRequestType & USB_DIR_IN) flags direction
        ('setup', USBCtrlRequest),
    ]

class Event(LittleEndianStructure):
    """
    Events are delivered on the ep0 file descriptor, when the user mode driver
    reads from this file descriptor after writing the descriptors.  Don't
    stop polling this descriptor.

    NOTE:  this structure must stay the same size and layout on
    both 32-bit and 64-bit kernels.
    """
    _pack_ = 1
    _fields_ = [
        ('u', _u),

        # event_type
        ('type', _u8),
        ('_pad', _u8 * 3),
    ]

# Endpoint ioctls
# The same as in gadgetfs

# IN transfers may be reported to the gadget driver as complete
#    when the fifo is loaded, before the host reads the data;
# OUT transfers may be reported to the host's "client" driver as
#    complete when they're sitting in the FIFO unread.
# THIS returns how many bytes are "unclaimed" in the endpoint fifo
# (needed for precise fault handling, when the hardware allows it)
FIFO_STATUS = ioctl_opt.IO(ord('g'), 1)

# discards any unclaimed data in the fifo.
FIFO_FLUSH = ioctl_opt.IO(ord('g'), 2)

# resets endpoint halt+toggle; used to implement set_interface.
# some hardware (like pxa2xx) can't support this.
CLEAR_HALT = ioctl_opt.IO(ord('g'), 3)

# Specific for functionfs

# Returns reverse mapping of an interface.  Called on EP0.  If there
# is no such interface returns -EDOM.  If function is not active
# returns -ENODEV.
INTERFACE_REVMAP = ioctl_opt.IO(ord('g'), 128)

# Returns real bEndpointAddress of an endpoint.  If function is not
# active returns -ENODEV.
ENDPOINT_REVMAP = ioctl_opt.IO(ord('g'), 129)

# Returns endpoint descriptor. If function is not active returns -ENODEV.
ENDPOINT_DESC = ioctl_opt.IOR(ord('g'), 130, USBEndpointDescriptor)

### Pythonic API

def getDescriptor(klass, **kw):
    """
    Automatically fills bLength and bDescriptorType.
    """
    # XXX: not very pythonic...
    return klass(
        bLength=sizeof(klass),
        bDescriptorType=klass._bDescriptorType,
        **kw
    )

def getOSDesc(interface, ext_list):
    """
    Return an OS description header.
    interface (int)
        Related interface number.
    ext_list (list of OSExtCompatDesc or OSExtPropDesc)
        List of instances of extended descriptors.
    """
    try:
        ext_type, = {type(ext_list) for x in ext_list}
    except ValueError:
        raise TypeError('Extensions of a single type are required.')
    if isinstance(ext_type, OSExtCompatDesc):
        wIndex = 4
        kw = {
            'b': {
                'bCount': len(ext_list),
                'Reserved': 0,
            },
        }
    elif isinstance(ext_type, OSExtPropDescHead):
        wIndex = 5
        kw = {
            'wCount': len(ext_list),
        }
    else:
        raise TypeError('Extensions of unexpected type')
    klass = type(
        'OSDesc',
        OSDescHeader,
        {
            '_fields_': [
                ('ext_list', ext_type * len(ext_list)),
            ],
        },
    )
    return klass(
        interface=interface,
        dwLength=sizeof(klass),
        bcdVersion=1,
        wIndex=wIndex,
        ext_list=ext_list,
        **kw
    )

def getOSExtPropDesc(data_type, name, value):
    """
    Returns an OS extension property descriptor.
    data_type (int)
        See wPropertyDataType documentation.
    name (string)
        See PropertyName documentation.
    value (string)
        See PropertyData documentation.
        NULL chars must be explicitely included in the value when needed,
        this function does not add any terminating NULL for example.
    """
    klass = type(
        'OSExtPropDesc',
        OSExtPropDescHead,
        {
            '_fields_': [
                ('bPropertyName', c_char * len(name)),
                ('dwPropertyDataLength', _le32),
                ('bProperty', c_char * len(value)),
            ],
        }
    )
    return klass(
        dwSize=sizeof(klass),
        dwPropertyDataType=data_type,
        wPropertyNameLength=len(name),
        bPropertyName=name,
        dwPropertyDataLength=len(value),
        bProperty=value,
    )

# Legacy descriptors format (deprecated as of 3.14):
#
# | off | name      | type         | description                          |
# |-----+-----------+--------------+--------------------------------------|
# |   0 | magic     | LE32         | FUNCTIONFS_DESCRIPTORS_MAGIC         |
# |   4 | length    | LE32         | length of the whole data chunk       |
# |   8 | fs_count  | LE32         | number of full-speed descriptors     |
# |  12 | hs_count  | LE32         | number of high-speed descriptors     |
# |  16 | fs_descrs | Descriptor[] | list of full-speed descriptors       |
# |     | hs_descrs | Descriptor[] | list of high-speed descriptors       |
#
# All numbers must be in little endian order.
def getDescs(*args, **kw):
    """
    Return a legacy format FunctionFS suitable for serialisation.
    Deprecated as of 3.14 .
    """
    warnings.warn(
        DeprecationWarning,
        'Legacy format, deprecated as of 3.14.',
    )
    raise NotImplementedError('TODO') # TODO
    klass = type(
        'Descs',
        DescsHead,
        {
            'fs_descrs': None, # TODO
            'hs_descrs': None, # TODO
        },
    )
    return klass(
        magic=DESCRIPTORS_MAGIC,
        length=sizeof(klass),
        **kw
    )

def getDescsV2(flags, fs_list=(), hs_list=(), ss_list=(), os_list=()):
    """
    Return a FunctionFS descriptor suitable for serialisation.

    flags (int)
        Any combination of VIRTUAL_ADDR, EVENTFD, ALL_CTRL_RECIP,
        CONFIG0_SETUP.
    {fs,hs,ss,os}_list (list of descriptors)
        Instances of the following classes:
        {fs,hs,ss}_list:
            USBInterfaceDescriptor
            USBEndpointDescriptorNoAudio
            USBEndpointDescriptor
            TODO: HID
            TODO: OTG
            TODO: Interface Association
            TODO: SS companion
            All (non-empty) lists must define the same number of interfaces
            and endpoints, and endpoint descriptors must be given in the same
            order, bEndpointAddress-wise.
        os_list:
            OSDesc
    """
    # TODO: add usage example
    count_field_list = []
    descr_field_list = []
    kw = {}
    for descriptor_list, flag, prefix, allowed_descriptor_klass in (
        (fs_list, HAS_FS_DESC, 'fs', LittleEndianDescriptorStructure),
        (hs_list, HAS_HS_DESC, 'hs', LittleEndianDescriptorStructure),
        (ss_list, HAS_SS_DESC, 'ss', LittleEndianDescriptorStructure),
        (os_list, HAS_MS_OS_DESC, 'os', OSDescHeader),
    ):
        if descriptor_list:
            for index, descriptor in enumerate(descriptor_list):
                if not isinstance(descriptor, allowed_descriptor_klass):
                    raise TypeError(
                        'Descriptor %r of unexpected type: %r' % (
                            index,
                            type(descriptor),
                        ),
                    )
            descriptor_dict = {
                'desc_%i' % x: y
                for x, y in enumerate(descriptor_list)
            }
            flags |= flag
            count_name = prefix + 'count'
            descr_name = prefix + 'descr'
            count_field_list.append((count_name, _le32))
            descr_type = type(
                't_' + descr_name,
                (LittleEndianStructure, ),
                {
                    '_pack_': 1,
                    '_fields_': [
                        (x, type(y))
                        for x, y in descriptor_dict.iteritems()
                    ],
                }
            )
            descr_field_list.append((descr_name, descr_type))
            kw[count_name] = len(descriptor_dict)
            kw[descr_name] = descr_type(**descriptor_dict)
        elif flags & flag:
            raise ValueError(
                'Flag %r set but descriptor list empty, cannot generate type.' % (
                    Flags.get(flag),
                )
            )
    klass = type(
        'DescsV2_0x%02x' % (
            flags & (
                HAS_FS_DESC |
                HAS_HS_DESC |
                HAS_SS_DESC |
                HAS_MS_OS_DESC
            ),
            # XXX: include contained descriptors type information ? (and name ?)
        ),
        (DescsHeadV2, ),
        {
            '_fields_': count_field_list + descr_field_list,
        },
    )
    return klass(
        magic=DESCRIPTORS_MAGIC_V2,
        length=sizeof(klass),
        flags=flags,
        **kw
    )

def getStrings(lang_dict):
    """
    Return a FunctionFS descriptor suitable for serialisation.

    lang_dict (dict)
        Key: language ID (ex: 0x0409 for en-us)
        Value: list of unicode objects
        All values must have the same number of items.
    """
    field_list = []
    kw = {}
    try:
        str_count = len(next(lang_dict.itervalues()))
    except StopIteration:
        str_count = 0
    else:
        for lang, string_list in lang_dict.iteritems():
            if len(string_list) != str_count:
                raise ValueError('All values must have the same string count.')
            field_id = 'strings_%04x' % lang
            strings = b'\x00'.join(x.encode('utf-8') for x in string_list) + b'\x00'
            field_type = type(
                'String',
                (StringBase, ),
                {
                    '_fields_': [
                        ('strings', c_char * len(strings)),
                    ],
                },
            )
            field_list.append((field_id, field_type))
            kw[field_id] = field_type(
                lang=lang,
                strings=strings,
            )
    klass = type(
        'Strings',
        (StringsHead, ),
        {
            '_fields_': field_list,
        },
    )
    return klass(
        magic=STRINGS_MAGIC,
        length=sizeof(klass),
        str_count=str_count,
        lang_count=len(lang_dict),
        **kw
    )

def serialise(structure):
    return (c_char * sizeof(structure)).from_address(addressof(structure))

class EndpointFileBase(io.FileIO):
    def _ioctl(self, func, arg=0, mutate_flag=False):
        result = fcntl.ioctl(self, func, arg, mutate_flag)
        if result < 0:
            raise IOError(result)
        return result

class Endpoint0File(EndpointFileBase):
    """
    File object exposing ioctls available on endpoint zero.
    """
    def halt(self, request_type):
        """
        Halt current endpoint.
        """
        try:
            if request_type & USB_DIR_IN:
                self.read(0)
            else:
                self.write('')
        except IOError, exc:
            if exc.errno != errno.EL2HLT:
                raise
        else:
            raise ValueError('halt did not return EL2HLT ?')

    def getRealInterfaceNumber(self, interface):
        """
        Returns the host-visible interface number.
        """
        return self._ioctl(INTERFACE_REVMAP, interface)

    # TODO: Add any standard IOCTL in usb_gadget_ops.ioctl ?

class EndpointFile(EndpointFileBase):
    """
    File object exposing ioctls available on non-zero endpoints.
    """
    _halted = False

    def getRealEndpointNumber(self):
        """
        Returns the host-visible endpoint number.
        """
        return self._ioctl(ENDPOINT_REVMAP)

    def clearHalt(self):
        """
        Clears endpoint halt, and resets toggle.

        See drivers/usb/gadget/udc/core.c:usb_ep_clear_halt
        """
        self._ioctl(CLEAR_HALT)
        self._halted = False

    def getFIFOStatus(self):
        """
        Returns the number of bytes in fifo.
        """
        return self._ioctl(FIFO_STATUS)

    def flushFIFO(self):
        """
        Discards Endpoint FIFO content.
        """
        self._ioctl(FIFO_FLUSH)

    def getDescriptor(self):
        """
        Returns the currently active endpoint descriptor
        (depending on current USB speed).
        """
        result = USBEndpointDescriptor()
        self._ioctl(ENDPOINT_DESC, result, True)
        return result

    def _halt(self):
        raise NotImplementedError

    def halt(self):
        """
        Halt current endpoint.
        """
        try:
            self._halt()
        except IOError, exc:
            if exc.errno != errno.EBADMSG:
                raise
        else:
            raise ValueError('halt did not return EBADMSG ?')
        self._halted = True

    def isHalted(self):
        return self._halted

class EndpointOUTFile(EndpointFile):
    """
    Write-only endpoint file.
    """
    @staticmethod
    def read(*args, **kw):
        """
        Always raises IOError.
        """
        raise IOError('File not open for reading')

    def _halt(self):
        super(EndpointOUTFile, self).read(0)

class EndpointINFile(EndpointFile):
    """
    Read-only endpoint file.
    """
    @staticmethod
    def write(*args, **kw):
        """
        Always raises IOError.
        """
        raise IOError('File not open for writing')

    def _halt(self):
        super(EndpointINFile, self).write('')

_INFINITY = itertools.repeat(None)
_ONCE = (None, )

class Function(object):
    """
    Pythonic class for interfacing with FunctionFS.
    """
    _closed = False

    def __init__(
        self,
        path,
        fs_list=(), hs_list=(), ss_list=(),
        os_list=(),
        lang_dict={},
        all_ctrl_recip=False, config0_setup=False,
    ):
        """
        path (string)
            Path to the functionfs mountpoint (where the ep* files are
            located).
        {fs,hs,ss}_list (list of descriptors)
            XXX: may change to avoid requiring ctype objects.
        os_list (list of descriptors)
            XXX: may change to avoid requiring ctype objects.
        lang_dict (dict)
            Keys: language id (ex: 0x0402 for "us-en").
            Values: List of unicode objects. First item becomes string
                    descriptor 1, and so on. Must contain at least as many
                    string descriptors as the highest string index declared
                    in all descriptors.
        all_ctrl_recip (bool)
            When true, this function will receive all control transactions.
            Useful when implementing non-standard control transactions.
        config0_setup (bool)
            When true, this function will receive control transactions before
            any configuration gets enabled.
        """
        self._path = path
        ep0 = Endpoint0File(os.path.join(path, 'ep0'), 'r+')
        self._ep_list = ep_list = [ep0]
        self._ep_address_dict = ep_address_dict = {}
        flags = 0
        if all_ctrl_recip:
            flags |= ALL_CTRL_RECIP
        if config0_setup:
            flags |= CONFIG0_SETUP
        desc = getDescsV2(
            flags,
            fs_list=fs_list,
            hs_list=hs_list,
            ss_list=ss_list,
            os_list=os_list,
        )
        desc_s = serialise(desc)
        print ' '.join(('%02x' % ord(x) for x in desc_s))
        ep0.write(desc_s)
        # TODO: try v1 on failure ?
        strings = getStrings(lang_dict)
        ep0.write(serialise(strings))
        for descriptor in fs_list or hs_list or ss_list:
            if descriptor.bDescriptorType == USB_DT_ENDPOINT:
                assert descriptor.bEndpointAddress not in ep_address_dict, (
                    descriptor,
                    ep_address_dict[descriptor.bEndpointAddress],
                )
                index = len(ep_list)
                ep_address_dict[descriptor.bEndpointAddress] = index
                ep_list.append(
                    (
                        EndpointINFile
                        if descriptor.bEndpointAddress & USB_DIR_IN
                        else EndpointOUTFile
                    )(
                        os.path.join(path, 'ep%u' % (index, )),
                        'r+',
                    )
                )


    @property
    def ep0(self):
        """
        Endpoint 0, use when handling setup transactions.
        """
        return self._ep_list[0]

    def close(self):
        """
        Close all endpoint file descriptors.
        """
        ep_list = self._ep_list
        while ep_list:
            ep_list.pop().close()
        self._closed = True

    def __del__(self):
        self.close()

    __event_dict = {
        BIND: 'onBind',
        UNBIND: 'onUnbind',
        ENABLE: 'onEnable',
        DISABLE: 'onDisable',
        # SETUP: handled specially
        SUSPEND: 'onSuspend',
        RESUME: 'onResume',
    }

    def __process(self, iterator):
        readinto = self.ep0.readinto
        # FunctionFS can queue up to 4 events, so let's read that much.
        event_len = sizeof(Event)
        array_type = Event * 4
        buf = bytearray(sizeof(array_type))
        event_list = array_type.from_buffer(buf)
        event_dict = self.__event_dict
        for _ in iterator:
            if self._closed:
                break
            try:
                length = readinto(buf)
            except IOError, exc:
                if exc.errno == errno.EINTR:
                    continue
                raise
            if not length:
                # Note: also catches None, returned when ep0 is non-blocking
                break # TODO: test if this happens when ep0 gets closed
                      # (by FunctionFS or in another thread or in a handler)
            count, remainder = divmod(length, event_len)
            assert remainder == 0, (length, event_len)
            for index in xrange(count):
                event = event_list[index]
                event_type = event.type
                if event_type == SETUP:
                    setup = event.u.setup
                    try:
                        self.onSetup(
                            setup.bRequestType,
                            setup.bRequest,
                            setup.wValue,
                            setup.wIndex,
                            setup.wLength,
                        )
                    except BaseException:
                        # On *ANY* exception, halt endpoint
                        self.ep0.halt(setup.bRequestType)
                        raise
                else:
                    getattr(self, event_dict[event.type])()

    def processEventsForever(self):
        """
        Process kernel ep0 events until closed.

        ep0 must be in blocking mode, otherwise behaves like `process`.
        """
        self.__process(_INFINITY)

    def processEvents(self):
        """
        Process at least one kernel event if ep0 is in blocking mode.
        Process any already available event if ep0 is in non-blocking mode.
        """
        self.__process(_ONCE)

    def getEndpoint(self, index):
        """
        Return a file object corresponding to given endpoint index,
        in descriptor list order.
        """
        return self._ep_list[address]

    def getEndpointByAddress(self, address):
        """
        Return a file object corresponding to given endpoint address.
        """
        return self.getEndpoint(self._ep_address_dict[address])

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def onBind(self):
        """
        Triggered when FunctionFS signals gadget binding.

        May be overridden in subclass.
        """
        pass

    def onUnbind(self):
        """
        Triggered when FunctionFS signals gadget unbinding.

        May be overridden in subclass.
        """
        pass

    def onEnable(self):
        """
        Called when FunctionFS signals the function was (re)enabled.
        This may happen several times without onDisable being called, which
        must reset the function to its default state.

        May be overridden in subclass.
        """
        pass

    def onDisable(self):
        """
        Called when FunctionFS signals the function was (re)disabled.
        This may happen several times without onEnable being called.

        May be overridden in subclass.
        """
        pass

    def onSetup(self, request_type, request, value, index, length):
        """
        Called when a setup USB transaction was received.

        Default implementation:
        - handles USB_REQ_GET_STATUS on interface and endpoints
        - handles USB_REQ_CLEAR_FEATURE(USB_ENDPOINT_HALT) on endpoints
        - handles USB_REQ_SET_FEATURE(USB_ENDPOINT_HALT) on endpoints
        - halts on everything else

        If this method raises anything, endpoint 0 is halted by its caller.

        May be overridden in subclass.
        """
        if (request_type & USB_TYPE_MASK) == USB_TYPE_STANDARD:
            recipient = request_type & USB_RECIP_MASK
            is_in = (request_type & USB_DIR_IN) == USB_DIR_IN
            if request == USB_REQ_GET_STATUS:
                if is_in and length == 2:
                    if recipient == USB_RECIP_INTERFACE:
                        self.ep0.write('\x00\x00')
                        return
                    elif recipient == USB_RECIP_ENDPOINT:
                        self.ep0.write(
                            struct.pack(
                                'BB',
                                0,
                                1 if self.getEndpoint(index).isHalted() else 0,
                            ),
                        )
                        return
            elif request == USB_REQ_CLEAR_FEATURE:
                if not is_in and length == 0:
                    if recipient == USB_RECIP_ENDPOINT:
                        if value == USB_ENDPOINT_HALT:
                            self.getEndpoint(index).clearHalt()
                            self.ep0.read(0)
                            return
            elif request == USB_REQ_SET_FEATURE:
                if not is_in and length == 0:
                    if recipient == USB_RECIP_ENDPOINT:
                        if value == USB_ENDPOINT_HALT:
                            self.getEndpoint(index).halt()
                            self.ep0.read(0)
                            return
        self.ep0.halt(request_type)

    def onSuspend(self):
        """
        Called when FunctionFS signals the host stops USB traffic.

        May be overridden in subclass.
        """
        pass

    def onResume(self):
        """
        Called when FunctionFS signals the host restarts USB traffic.

        May be overridden in subclass.
        """
        pass
