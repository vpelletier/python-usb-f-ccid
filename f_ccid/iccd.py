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

# pylint: disable=missing-docstring, too-many-ancestors

import ctypes
from .usb import (
    COMMAND_STATUS_OK,
    MESSAGE_TYPE_ABORT,
    MESSAGE_TYPE_DATA_BLOCK,
    MESSAGE_TYPE_ESCAPE,
    MESSAGE_TYPE_ESCAPE_RESPONSE,
    MESSAGE_TYPE_GET_PARAMETERS,
    MESSAGE_TYPE_GET_SLOT_STATUS,
    MESSAGE_TYPE_HARDWARE_ERROR,
    MESSAGE_TYPE_ICC_CLOCK,
    MESSAGE_TYPE_MECHANICAL,
    MESSAGE_TYPE_PARAMETERS,
    MESSAGE_TYPE_POWER_OFF,
    MESSAGE_TYPE_POWER_ON,
    MESSAGE_TYPE_RATE_AND_CLOCK,
    MESSAGE_TYPE_RESET_PARAMETERS,
    MESSAGE_TYPE_SECURE,
    MESSAGE_TYPE_SET_PARAMETERS,
    MESSAGE_TYPE_SET_RATE_AND_CLOCK,
    MESSAGE_TYPE_SLOT_CHANGE,
    MESSAGE_TYPE_SLOT_STATUS,
    MESSAGE_TYPE_T0_APDU,
    MESSAGE_TYPE_XFR_BLOCK,
)
from .utils import metaclassmethod

NO_DATA = bytearray()

class PackedLittleEndianStructure(ctypes.LittleEndianStructure):
    _pack_ = 1

# ctypes.LittleEndianStructure is not an instance of type, but an instance of
# _ctypes.PyCStructType . So introspect that class to auto-determine the
# correct metaclass base. It's turtles all the way down.
class _ICCDStructRegistrar(type(ctypes.LittleEndianStructure)):
    """
    Metaclass for ICCD message classes.
    Manages the message type registry for parsing buffers into the correct
    obhect.
    """
    __register = {}
    def __new__(metacls, name, bases, clsdict):
        cls = super().__new__(metacls, name, bases, clsdict)
        try:
            bMessageType = clsdict['_bMessageType']
        except KeyError:
            pass # abstract subclass
        else:
            assert bMessageType not in metacls.__register, (
                bMessageType,
                metacls.__register[bMessageType],
                cls,
            )
            metacls.__register[bMessageType] = cls
        return cls

    @metaclassmethod
    def guess_subtype_from_buffer(metacls, cls, source, offset=0):
        from_buffer = super().from_buffer
        message_type = from_buffer(ICCDMessageBase, source, offset).bMessageType
        try:
            found_cls = metacls.__register[message_type]
            if not issubclass(found_cls, cls):
                raise KeyError
        except KeyError:
            raise ValueError(
                'Invalid bMessageType: 0x%02x' % (message_type, ),
            ) from None
        return from_buffer(found_cls, source, offset)

class ICCDMessageBase(
    PackedLittleEndianStructure,
    metaclass=_ICCDStructRegistrar,
):
    def __repr__(self):
        return '<%s(%s)>' % (
            self.__class__.__name__,
            ', '.join(
                '%s=%r' % (x[0], getattr(self, x[0], None))
                for cls in reversed(self.__class__.mro())
                for x in cls.__dict__.get('_fields_', ())
            ),
        )

    def __init__(self, **kw):
        super().__init__(
            bMessageType=self._bMessageType,
            **kw
        )

    _fields_ = (
        ('bMessageType', ctypes.c_ubyte),
    )

class ICCDBulkMessageBase(ICCDMessageBase):
    _fields_ = (
        ('dwLength', ctypes.c_uint),
        ('bSlot', ctypes.c_ubyte),
        ('bSeq', ctypes.c_ubyte),
    )

# ICCD notification messages. Intended for INT endpoint to host.

class ICCDNotifySlotChangeBase(ICCDMessageBase):
    _bMessageType = MESSAGE_TYPE_SLOT_CHANGE

_notify_slot_change_cache_dict = {}
def ICCDNotifySlotChange(slot_state_list):
    slot_count = len(slot_state_list)
    try:
        klass = _notify_slot_change_cache_dict[slot_count]
    except KeyError:
        klass = _notify_slot_change_cache_dict[slot_count] = type(
            'ICCDNotifySlotChange%i' % slot_count,
            (ICCDNotifySlotChangeBase, ),
            {
                '_fields_': sum(
                    (
                        (
                            ('present%i' % index, ctypes.c_ubyte, 1),
                            ('changed%i' % index, ctypes.c_ubyte, 1),
                        )
                        for index in range(slot_count)
                    ),
                    (),
                ),
            },
        )
        slot_len, remainder = divmod(slot_count, 4)
        if remainder:
            slot_len += 1
        assert ctypes.sizeof(klass) == ctypes.sizeof(ICCDNotifySlotChangeBase) + slot_len, (
            ctypes.sizeof(klass),
            ctypes.sizeof(ICCDNotifySlotChangeBase) + slot_len,
        )
    return klass(**{
        key + str(index): value
        for index, slot_state_dict in enumerate(slot_state_list)
        for key, value in slot_state_dict.items()
    })

class ICCDNotifyHardwareError(ICCDMessageBase):
    _bMessageType = MESSAGE_TYPE_HARDWARE_ERROR
    _fields_ = (
        ('bSlot', ctypes.c_ubyte),
        ('bSeq', ctypes.c_ubyte),
        ('bHardwareErrorCode', ctypes.c_ubyte),
    )

# ICCD response messages. Intended for BULK endpoint to host.

class ICCDResponseBase(ICCDBulkMessageBase):
    def __init__(
        self,
        bmICCStatus,
        bmCommandStatus=COMMAND_STATUS_OK,
        bError=0,
        **kw
    ):
        super().__init__(
            bmICCStatus=bmICCStatus,
            bmCommandStatus=bmCommandStatus,
            bError=bError,
            **kw
        )

    _fields_ = (
        ('bmICCStatus', ctypes.c_ubyte, 2),
        ('bmRFU', ctypes.c_ubyte, 4),
        ('bmCommandStatus', ctypes.c_ubyte, 2),
        ('bError', ctypes.c_byte),
    )

class ICCDResponseDataBlock(ICCDResponseBase):
    _bMessageType = MESSAGE_TYPE_DATA_BLOCK
    _fields_ = (
        ('bChainParameter', ctypes.c_ubyte),
    )

class ICCDResponseSlotStatus(ICCDResponseBase):
    _bMessageType = MESSAGE_TYPE_SLOT_STATUS
    _fields_ = (
        ('bClockStatus', ctypes.c_ubyte),
    )

class ICCDResponseParametersBase(ICCDResponseBase):
    _bMessageType = MESSAGE_TYPE_PARAMETERS
    _fields_ = (
        ('bProtocolNum', ctypes.c_ubyte),
    )

class ICCDResponseParameterT0(ICCDResponseParametersBase):
    _fields_ = (
        ('bmFindexDindex', ctypes.c_ubyte),
        ('bmTCCKS', ctypes.c_ubyte),
        ('bGuardTime', ctypes.c_ubyte),
        ('bmWaitingIntegers', ctypes.c_ubyte),
        ('bClockStop', ctypes.c_ubyte),
    )

class ICCDResponseParameterT1(ICCDResponseParameterT0):
    _fields_ = (
        ('bIFSC', ctypes.c_ubyte),
        ('bNadValue', ctypes.c_ubyte),
    )

GET_PARAMETERS_STRUCT_DICT = {
    0: ICCDResponseParameterT0,
    1: ICCDResponseParameterT1,
}

class _ICCDResponseParametersBase(ICCDResponseParametersBase):
    def __new__(cls, bProtocolNum, **kw):
        return GET_PARAMETERS_STRUCT_DICT[bProtocolNum](
            bProtocolNum=bProtocolNum,
            **kw
        )

    @classmethod
    def from_buffer(cls, data):
        return GET_PARAMETERS_STRUCT_DICT[
            super().from_buffer(data).bProtocolNum
        ].from_buffer(data)

class ICCDResponseEscape(ICCDResponseBase):
    _bMessageType = MESSAGE_TYPE_ESCAPE_RESPONSE

class ICCDResponseRateAndClock(ICCDResponseBase):
    _bMessageType = MESSAGE_TYPE_RATE_AND_CLOCK
    _fields_ = (
        ('bRFU', ctypes.c_ubyte),
        ('dwClockFrequency', ctypes.c_uint),
        ('dwDataRate', ctypes.c_uint),
    )

# ICCD request messages. Intended for BULK endpoint from host.

class ICCDRequestBase(ICCDBulkMessageBase):
    def getResponse(self, body=NO_DATA, **kw):
        """
        Return an instance of the appropriate response type for this request.
        """
        return (
            self.response_type(
                dwLength=len(body),
                bSlot=self.bSlot,
                bSeq=self.bSeq,
                **kw
            ),
            body,
        )

class ICCDRequestPowerOn(ICCDRequestBase):
    _bMessageType = MESSAGE_TYPE_POWER_ON
    response_type = ICCDResponseDataBlock
    _fields_ = (
        ('bPowerSelect', ctypes.c_ubyte),
        ('abRFU', ctypes.c_ubyte * 2),
    )

class ICCDRequestPowerOff(ICCDRequestBase):
    _bMessageType = MESSAGE_TYPE_POWER_OFF
    response_type = ICCDResponseSlotStatus
    _fields_ = (
        ('abRFU', ctypes.c_ubyte * 3),
    )

class ICCDRequestGetSlotStatus(ICCDRequestBase):
    _bMessageType = MESSAGE_TYPE_GET_SLOT_STATUS
    response_type = ICCDResponseSlotStatus
    _fields_ = (
        ('abRFU', ctypes.c_ubyte * 3),
    )

class ICCDRequestXfrBlock(ICCDRequestBase):
    _bMessageType = MESSAGE_TYPE_XFR_BLOCK
    response_type = ICCDResponseDataBlock
    _fields_ = (
        ('bBWI', ctypes.c_ubyte),
        ('wLevelParameter', ctypes.c_ushort),
    )

class ICCDRequestGetParameters(ICCDRequestBase):
    _bMessageType = MESSAGE_TYPE_GET_PARAMETERS
    response_type = _ICCDResponseParametersBase
    _fields_ = (
        ('abRFU', ctypes.c_ubyte * 3),
    )

class ICCDRequestResetParameters(ICCDRequestBase):
    _bMessageType = MESSAGE_TYPE_RESET_PARAMETERS
    response_type = _ICCDResponseParametersBase
    _fields_ = (
        ('abRFU', ctypes.c_ubyte * 3),
    )

class ICCDRequestSetParameters(ICCDRequestBase):
    _bMessageType = MESSAGE_TYPE_SET_PARAMETERS
    response_type = _ICCDResponseParametersBase
    _fields_ = (
        ('bProtocolNum', ctypes.c_ubyte),
        ('abRFU', ctypes.c_ubyte * 2),
    )

class ICCDRequestSetParametersT0(ICCDRequestSetParameters):
    _fields_ = (
        ('bmFindexDindex', ctypes.c_ubyte),
        ('bmTCCKS', ctypes.c_ubyte),
        ('bGuardTime', ctypes.c_ubyte),
        ('bmWaitingIntegers', ctypes.c_ubyte),
        ('bClockStop', ctypes.c_ubyte),
    )

class ICCDRequestSetParametersT1(ICCDRequestSetParametersT0):
    _fields_ = (
        ('bIFSC', ctypes.c_ubyte),
        ('bNadValue', ctypes.c_ubyte),
    )

ICCD_REQUEST_SET_PARAMETERS_LENGTH = ctypes.sizeof(ICCDRequestSetParameters)
ICCD_REQUEST_SET_PARAMETERS_T0_LENGTH = ctypes.sizeof(
    ICCDRequestSetParametersT0,
) - ICCD_REQUEST_SET_PARAMETERS_LENGTH
ICCD_REQUEST_SET_PARAMETERS_T1_LENGTH = ctypes.sizeof(
    ICCDRequestSetParametersT1,
) - ICCD_REQUEST_SET_PARAMETERS_LENGTH

SET_PARAMETERS_STRUCT_DICT = {
    0: ICCDRequestSetParametersT0,
    1: ICCDRequestSetParametersT1,
}

class _ICCDRequestSetParameters(ICCDRequestSetParameters):
    @classmethod
    def from_buffer(cls, data):
        return SET_PARAMETERS_STRUCT_DICT[
            super().from_buffer(data).bProtocolNum
        ].from_buffer(data)

class ICCDRequestEscape(ICCDRequestBase):
    _bMessageType = MESSAGE_TYPE_ESCAPE
    response_type = ICCDResponseEscape
    _fields_ = (
        ('abRFU', ctypes.c_ubyte * 3),
    )

class ICCDRequestICCClock(ICCDRequestBase):
    _bMessageType = MESSAGE_TYPE_ICC_CLOCK
    response_type = ICCDResponseSlotStatus
    _fields_ = (
        ('bClockCommand', ctypes.c_ubyte),
        ('abRFU', ctypes.c_ubyte * 2),
    )

class ICCDRequestT0APDU(ICCDRequestBase):
    _bMessageType = MESSAGE_TYPE_T0_APDU
    response_type = ICCDResponseSlotStatus
    _fields_ = (
        ('bmChanges', ctypes.c_ubyte),
        ('bClassResponse', ctypes.c_ubyte),
        ('bClassEnvelope', ctypes.c_ubyte),
    )

class ICCDRequestSecure(ICCDRequestBase):
    _bMessageType = MESSAGE_TYPE_SECURE
    response_type = ICCDResponseDataBlock
    _fields_ = (
        ('bBWI', ctypes.c_ubyte),
        ('wLevelParameter', ctypes.c_ushort),
    )

class _ICCDRequestSecure(ICCDRequestSecure):
    @classmethod
    def from_buffer(cls, data):
        head = super().from_buffer(data)
        if head.wLevelParameter in (0, 1):
            return _ICCDRequestPINOperation.from_buffer(data)
        return head

class ICCDRequestPINOperation(ICCDRequestSecure):
    _fields_ = (
        ('bPINOperation', ctypes.c_ubyte),
    )

class _ICCDRequestPINOperation(ICCDRequestPINOperation):
    @classmethod
    def from_buffer(cls, data):
        head = super().from_buffer(data)
        if head.bPINOperation == 0:
            return ICCDRequestPINVerification.from_buffer(data)
        elif head.bPINOperation == 1:
            return _ICCDRequestPINModificationBase.from_buffer(data)
        return head

class ICCDRequestPINVerification(ICCDRequestPINOperation):
    _fields_ = (
        ('bTimeOut', ctypes.c_ubyte),
        ('bmFormatString', ctypes.c_ubyte),
        ('bmPINBlockString', ctypes.c_ubyte),
        ('bmPINLengthFormat', ctypes.c_ubyte),
        ('wPINMaxExtraDigit', ctypes.c_ushort),
        ('bEntryValidationCondition', ctypes.c_ubyte),
        ('bNumberMessage', ctypes.c_ubyte),
        ('wLangId', ctypes.c_ushort),
        ('bMsgIndex', ctypes.c_ubyte),
        ('bTeoPrologue', ctypes.c_ubyte * 3),
    )

class ICCDRequestPINModificationBase(ICCDRequestPINOperation):
    _fields_ = (
        ('bTimeOut', ctypes.c_ubyte),
        ('bmFormatString', ctypes.c_ubyte),
        ('bmPINBlockString', ctypes.c_ubyte),
        ('bmPINLengthFormat', ctypes.c_ubyte),
        ('bInsertionOffsetOld', ctypes.c_ubyte),
        ('bInsertionOffsetNew', ctypes.c_ubyte),
        ('wPINMaxExtraDigit', ctypes.c_ushort),
        ('bConfirmPIN', ctypes.c_ubyte),
        ('bEntryValidationCondition', ctypes.c_ubyte),
        ('bNumberMessage', ctypes.c_ubyte),
        ('wLangId', ctypes.c_ushort),
        ('bMsgIndex1', ctypes.c_ubyte),
    )

class _ICCDRequestPINModificationBase(ICCDRequestPINModificationBase):
    @classmethod
    def from_buffer(cls, data):
        bNumberMessage = super().from_buffer(data).bNumberMessage
        if bNumberMessage in (0, 1):
            return ICCDRequestPINModification1.from_buffer(data)
        if bNumberMessage == 2:
            return ICCDRequestPINModification2.from_buffer(data)
        if bNumberMessage == 3:
            return ICCDRequestPINModification3.from_buffer(data)
        raise ValueError(bNumberMessage)

class ICCDRequestPINModification1(ICCDRequestPINModificationBase):
    _fields_ = (
        ('bTeoPrologue', ctypes.c_ubyte * 3),
    )

class ICCDRequestPINModification2(ICCDRequestPINModificationBase):
    _fields_ = (
        ('bMsgIndex2', ctypes.c_ubyte),
        ('bTeoPrologue', ctypes.c_ubyte * 3),
    )

class ICCDRequestPINModification3(ICCDRequestPINModificationBase):
    _fields_ = (
        ('bMsgIndex2', ctypes.c_ubyte),
        ('bMsgIndex3', ctypes.c_ubyte),
        ('bTeoPrologue', ctypes.c_ubyte * 3),
    )

class ICCDRequestMechanical(ICCDRequestBase):
    _bMessageType = MESSAGE_TYPE_MECHANICAL
    response_type = ICCDResponseSlotStatus
    _fields_ = (
        ('bFunction', ctypes.c_ubyte),
        ('abRFU', ctypes.c_ubyte * 2),
    )

class ICCDRequestAbort(ICCDRequestBase):
    _bMessageType = MESSAGE_TYPE_ABORT
    response_type = ICCDResponseSlotStatus
    _fields_ = (
        ('abRFU', ctypes.c_ubyte * 3),
    )

class ICCDRequestRateAndClockRequest(ICCDRequestBase):
    _bMessageType = MESSAGE_TYPE_SET_RATE_AND_CLOCK
    response_type = ICCDResponseRateAndClock
    _slots_ = (
        ('abRFU', ctypes.c_ubyte * 3),
        ('dwClockFrequency', ctypes.c_uint),
        ('dwDataRate', ctypes.c_uint),
    )
