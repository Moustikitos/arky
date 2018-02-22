# -*- encoding: utf8 -*-
# © Toons

"""This module contains functions to connect with Ledger Nano S"""

import io
import os
import struct

import arky
from arky import HOME, cfg, util

from ledgerblue.comm import getDongle

from six import PY3


def pack(f, v):
	if PY3:
		output = struct.pack(f, v)
	else:
		output = bytes(struct.pack(f, v))
	return output


# convert int to byte
def intasb(i):
	return util.unhexlify(hex(i)[2:])


def parseBip32Path(path):
	"""
	Parse a derivation path.
	~https://github.com/bitcoin/bips/blob/master/bip-0044.mediawiki

	Argument:
	path -- the derivation path

	Return bytes
	"""
	if len(path) == 0:
		return b""
	result = b""
	elements = path.split('/')
	for pathElement in elements:
		element = pathElement.split("'")
		if len(element) == 1:
			result = result + pack(">I", int(element[0]))
		else:
			result = result + pack(">I", 0x80000000 | int(element[0]))
	return result


def buildTxApdu(dongle_path, data):
	"""
	Generate apdu from tx data to be sent into the ledger key.

	Argument:
	dongle_path -- value returned by parseBip32Path
	data -- value returned by arky.core.crypto.getBytes

	Return bytes
	"""

	path_len = len(dongle_path)

	if len(data) > 255 - (path_len + 1):
		data1 = data[:255 - (path_len + 1)]
		data2 = data[255 - (path_len + 1):]
		p1 = util.unhexlify("e0040040")
	else:
		data1 = data
		data2 = util.unhexlify("")
		p1 = util.unhexlify("e0048040")

	return [
		p1 + intasb(path_len + 1 + len(data1)) + intasb(path_len // 4) + dongle_path + data1,
		util.unhexlify("e0048140") + intasb(len(data2)) + data2 if len(data2) else None
	]


def buildPkeyApdu(dongle_path):
	"""
	Generate apdu to get public key from ledger key.

	Argument:
	dongle_path -- value returned by parseBip32Path

	Return bytes
	"""

	path_len = len(dongle_path)
	return util.unhexlify("e0020040") + intasb(1 + path_len) + intasb(path_len // 4) + dongle_path


def getPublicKey(dongle_path, debug=False):
	"""
	Compute the public key associated to a derivation path.

	Argument:
	dongle_path -- value returned by parseBip32Path

	Return str (hex)
	"""
	dongle = getDongle(debug)
	pkey_apdu = buildPkeyApdu(dongle_path)
	data = bytes(dongle.exchange(pkey_apdu))
	dongle.close()
	len_pkey = util.basint(data[0])
	return util.hexlify(data[1:len_pkey + 1])


def signTx(tx, dongle_path, debug=False):
	"""
	Sign a transaction. It generates the signature accordingly to derivation path
	and computes the id of the transaction. The tx is then updated and returned.

	Argument:
	tx -- a dict object containing explicit fields and values defining a valid transaction
	dongle_path -- a derivation path

	Keyword argument:
	debug -- flag to activate debug messages from ledger key [default: False]

	Return dict
	"""
	apdu1, apdu2 = buildTxApdu(dongle_path, arky.core.crypto.getBytes(tx))
	dongle = getDongle(debug)
	if apdu2:
		result = dongle.exchange(apdu2)
	else:
		result = dongle.exchange(apdu1)
	dongle.close()
	tx.update({
		"signature": util.hexlify(result),
		"id": arky.core.crypto.getId(tx)
	})
	return tx


def dumpBip39(pin, bip39, name="unamed"):
	"""
	Encrypt your passphrase using a pin code and save it on the disk.
	Dumped file are located in ~/.bip39/<network-name>.

	Argument:
	pin -- a str containing pin code (no limit in digit number) or a password
	bip39 -- a str containing passphrase

	Keyword argument:
	name -- the name you want to give
	"""

	bip39 = bip39 if isinstance(bip39, bytes) else bip39.encode("utf-8")
	folder = os.path.join(HOME, ".bip39", cfg.network)
	if not os.path.exists(folder):
		os.makedirs(folder)
	with io.open(os.path.join(folder, name + ".bip39"), "wb") as out:
		out.write(util.scramble(util.createBase(pin), util.hexlify(bip39)))


def loadBip39(pin, name="unamed"):
	"""
	Decrypt your saved passphrase located in ~/.bip39/<network-name>.

	Argument:
	pin -- a str containing pin code (no limit in digit number) or a password

	Keyword argument:
	name -- the filname you want decrypt
	"""

	filename = os.path.join(HOME, ".bip39", cfg.network, name + ".bip39")
	if os.path.exists(filename):
		with io.open(filename, "rb") as in_:
			data = util.unScramble(util.createBase(pin), in_.read())
		return util.unhexlify(data).decode("utf-8")
