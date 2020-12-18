Userland USB Gadget implementation of CCID/ICCD class.

Implements an N-slots USB virtual IC card reader.

Usage
-----

In a nutshell:

.. code:: python

    import f_ccid
    with f_ccid.ICCDFunction(path, slot_count=1) as ccid:
        ccid.slot_list[0].insert(card)
        ccid.processEventsForever()

(but check out functionfs.gadget to setup configfs for you, and provide the
`path` argument above)

This module does not provide any card implementation.

The expected card API is:

.. code:: python

  card.clearVolatiles() -> None

Called when virtual power is cut to the card, which means it must flush its
volatile state.

.. code:: python

  card.getATR() -> bytearray

Called when the host tells the reader to power the card. This must return the
Answer To Reset bytestring for this card. Note that the answer must be mutable:
although it will not be altered by the reader, it will be passed on to C code
which technically could mutate it.

.. code:: python

  card.runAPDU(: bytearray) -> bytearray

Called when the host requests an Application Protocol Data Unit to be executed
by the card. The returned value must contain any response, followed by any
status bytes. Only entire APDUs are sent to the card (assembly is done by the
reader).
