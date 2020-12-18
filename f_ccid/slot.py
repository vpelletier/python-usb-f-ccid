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

from .usb import (
    ICC_STATUS_NOT_PRESENT,
    ICC_STATUS_INACTIVE,
    ICC_STATUS_ACTIVE,
)
from .utils import chainBytearrayList

ABORT_MARKER = object()

class ICCDSlot:
    """
    Represents a card slot in a reader.

    You should only call "insert" and "remove", the rest of the API is
    intended for ICCDFunction.
    """
    def __init__(self, onEvent):
        self.status = ICC_STATUS_NOT_PRESENT
        self.changed = False
        self._data = []
        self._abort_control_sequence = None
        self._abort_response = None
        self._card = None
        self._onEvent = onEvent

    # Public API
    def insert(self, card):
        """
        Insert given card in this slot.
        Raises RuntimeError if there is alredy a card in this slot.
        """
        if self._card is not None:
            raise RuntimeError('Card already present')
        self._card = card
        self.status = ICC_STATUS_INACTIVE
        self.clearAPDU()
        self.changed = True
        self._onEvent()

    def remove(self):
        """
        Remove a card from this slot.
        Raises RuntimeError if there is no card in this slot.
        Returns retrieved card.
        """
        card = self._card
        if card is None:
            raise RuntimeError('No card present')
        card.clearVolatile()
        self._card = None
        self.status = ICC_STATUS_NOT_PRESENT
        self.clearAPDU()
        self.changed = True
        self._onEvent()
        return card

    # Abort protocol
    def isAborting(self):
        """
        Whether an abort is in progress.
        """
        return (
            self._abort_control_sequence is not None or
            self._abort_response is not None
        )

    def abortFromBulk(self, response):
        """
        Signal reception of an abort command on bulk endpoint.

        If control abort was already received for this sequence number, returns
        the response so it gets sent to host.
        Otherwise, given response is kept until control abort is received,
        and ABORT_MARKER is returned.
        """
        if self._abort_control_sequence == response[0].bSeq:
            self._abort_control_sequence = None
            return response
        assert self._abort_response is None
        self._abort_response = response
        return ABORT_MARKER

    def abortFromControl(self, sequence):
        """
        Signal reception of an abort command on control endpoint.

        If bulk abort was already received for this sequence number, returns
        the kept response so it gets sent to host.
        Otherwise, sequence number is kept and ABORT_MARKER is returned.
        """
        response = self._abort_response
        if response is None or sequence != response.bSeq:
            assert self._abort_control_sequence is None
            self._abort_control_sequence = sequence
            return ABORT_MARKER
        self._abort_response = None
        return response

    # Normal internal API
    def getSlotChangeNotification(self):
        """
        Return slot status: whether a card is present, and whether this changed
        since last time this method was called.
        """
        changed = self.changed
        self.changed = False
        return {
            'present': self.status != ICC_STATUS_NOT_PRESENT,
            'changed': changed,
        }

    def powerOn(self):
        """
        Tell the slot to power up.

        Return Answer-To-Reset data from card if thre is a card present, raises
        AttributeError otherwise.
        """
        if self.status == ICC_STATUS_INACTIVE:
            self.status = ICC_STATUS_ACTIVE
        assert not self._data
        atr = self._card.getATR()
        print('ICCDSlot.powerOn ATR:', atr.hex())
        return atr

    def powerOff(self):
        """
        Tell the slot to power down.
        """
        if self.status == ICC_STATUS_ACTIVE:
            self.status = ICC_STATUS_INACTIVE
            self._card.clearVolatile()
        self.clearAPDU()

    def clearAPDU(self):
        """
        Clear any previous (incomplete ?) APDU transfer.
        """
        del self._data[:]

    def storeAPDU(self, apdu):
        """
        Store a chunk of an APDU command.
        """
        self._data.append(apdu)

    def runAPDU(self):
        """
        Send stored APDU to card and return its response.
        """
        result = self._card.runAPDU(chainBytearrayList(self._data))
        self.clearAPDU()
        return result
