# Copyright (C) 2018-2020  Vincent Pelletier <plr.vincent@gmail.com>
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
from functools import partial

class metaclassmethod:
    """
    Methods get the instance they are called on as first argument.
    Class methods get the class they are defined in as first argument.
    This class implements a mix of both above for use on metaclass methods:
    they get the (meta)class they are defined on as first argument and the
    class they are called from as second argument.
    """
    def __init__(self, func):
        self.__func = func

    def __get__(self, instance, owner=None):
        return partial(self.__func, owner, instance)

def chainBytearrayList(bytearray_list):
    if len(bytearray_list) == 1:
        return bytearray_list[0]
    # TODO: make a class to not have to copy memory
    result = bytearray(sum(len(x) for x in bytearray_list))
    base = 0
    for chunk in bytearray_list:
        old_base = base
        base += len(chunk)
        result[old_base:base] = chunk
    return result
