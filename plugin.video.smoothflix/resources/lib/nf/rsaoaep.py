# -*- coding: utf-8 -*-
# Copyright (C) 2026 Scott
# SPDX-License-Identifier: GPL-3.0-only
"""RSA-OAEP (SHA-1, MGF1) and SubjectPublicKeyInfo encoding.

Netflix's MSL handshake wraps the session keys to the client's RSA public
key with OAEP. This is only that wrapping. It does not touch video keys.
"""

import hashlib
import os
import random

_SMALL = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47)
_OID = bytes.fromhex('06092a864886f70d010101')


def _prime(bits, rng, rounds=8):
    while True:
        candidate = rng.getrandbits(bits) | 1 | (1 << (bits - 1))
        if _is_prime(candidate, rng, rounds):
            return candidate


def _is_prime(number, rng, rounds):
    if number < 2:
        return False
    for small in _SMALL:
        if number % small == 0:
            return number == small
    shift = number - 1
    power = 0
    while shift % 2 == 0:
        shift //= 2
        power += 1
    for _ in range(rounds):
        base = rng.randrange(2, number - 1)
        value = pow(base, shift, number)
        if value in (1, number - 1):
            continue
        for _ in range(power - 1):
            value = pow(value, 2, number)
            if value == number - 1:
                break
        else:
            return False
    return True


def generate(bits=2048):
    """Return n, e, d for a new key."""
    rng = random.SystemRandom()
    exponent = 65537
    while True:
        first = _prime(bits // 2, rng)
        second = _prime(bits // 2, rng)
        if first == second:
            continue
        modulus = first * second
        lam = (first - 1) * (second - 1) // _gcd(first - 1, second - 1)
        if _gcd(exponent, lam) != 1:
            continue
        private = pow(exponent, -1, lam)
        return {'n': modulus, 'e': exponent, 'd': private}


def _gcd(left, right):
    while right:
        left, right = right, left % right
    return left


def _mgf1(seed, length):
    out = b''
    counter = 0
    while len(out) < length:
        out += hashlib.sha1(seed + counter.to_bytes(4, 'big')).digest()
        counter += 1
    return out[:length]


def _i2osp(value, length):
    raw = value.to_bytes(length, 'big')
    if len(raw) != length:
        raise ValueError('integer does not fit')
    return raw


def encrypt(key, message):
    """OAEP-encrypt message for a public key dict with n and e."""
    modulus = key['n']
    size = (modulus.bit_length() + 7) // 8
    hash_len = 20
    if len(message) > size - 2 * hash_len - 2:
        raise ValueError('message too long for OAEP')
    label = hashlib.sha1(b'').digest()
    padding = b'\x00' * (size - len(message) - 2 * hash_len - 2)
    data_block = label + padding + b'\x01' + message
    seed = os.urandom(hash_len)
    masked_data = bytes(a ^ b for a, b in zip(data_block, _mgf1(seed, size - hash_len - 1)))
    masked_seed = bytes(a ^ b for a, b in zip(seed, _mgf1(masked_data, hash_len)))
    encoded = b'\x00' + masked_seed + masked_data
    return _i2osp(pow(int.from_bytes(encoded, 'big'), key['e'], modulus), size)


def decrypt(key, ciphertext):
    """OAEP-decrypt ciphertext with a private key dict."""
    modulus = key['n']
    size = (modulus.bit_length() + 7) // 8
    hash_len = 20
    if len(ciphertext) != size:
        raise ValueError('ciphertext length does not match the key')
    encoded = _i2osp(pow(int.from_bytes(ciphertext, 'big'), key['d'], modulus), size)
    if encoded[0] != 0:
        raise ValueError('OAEP header is wrong')
    masked_seed = encoded[1:1 + hash_len]
    masked_data = encoded[1 + hash_len:]
    seed = bytes(a ^ b for a, b in zip(masked_seed, _mgf1(masked_data, hash_len)))
    data_block = bytes(a ^ b for a, b in zip(masked_data, _mgf1(seed, size - hash_len - 1)))
    label = hashlib.sha1(b'').digest()
    if data_block[:hash_len] != label:
        raise ValueError('OAEP label is wrong')
    rest = data_block[hash_len:]
    index = rest.find(b'\x01')
    if index < 0 or set(rest[:index]) != {0}:
        raise ValueError('OAEP padding is wrong')
    return rest[index + 1:]


def _der_len(length):
    if length < 128:
        return bytes([length])
    raw = length.to_bytes((length.bit_length() + 7) // 8, 'big')
    return bytes([0x80 | len(raw)]) + raw


def _der_int(value):
    raw = value.to_bytes((value.bit_length() + 7) // 8 or 1, 'big')
    if raw[0] & 0x80:
        raw = b'\x00' + raw
    return b'\x02' + _der_len(len(raw)) + raw


def _der_seq(body):
    return b'\x30' + _der_len(len(body)) + body


def public_der(key):
    """SubjectPublicKeyInfo DER for the public half of key."""
    pkcs1 = _der_seq(_der_int(key['n']) + _der_int(key['e']))
    algorithm = _der_seq(_OID + b'\x05\x00')
    bit_string = b'\x03' + _der_len(len(pkcs1) + 1) + b'\x00' + pkcs1
    return _der_seq(algorithm + bit_string)


def public_from_der(blob):
    """Read n and e back out of a SubjectPublicKeyInfo blob."""
    numbers = []

    def take(data, index):
        tag = data[index]
        index += 1
        length = data[index]
        index += 1
        if length & 0x80:
            count = length & 0x7f
            length = int.from_bytes(data[index:index + count], 'big')
            index += count
        content = data[index:index + length]
        index += length
        if tag == 0x30:
            inner = 0
            while inner < len(content):
                inner = take(content, inner)
        elif tag == 0x03 and content and content[0] == 0:
            inner = 0
            body = content[1:]
            while inner < len(body):
                inner = take(body, inner)
        elif tag == 0x02:
            numbers.append(int.from_bytes(content, 'big'))
        return index

    take(blob, 0)
    if len(numbers) < 2:
        raise ValueError('public key DER did not contain n and e')
    return {'n': numbers[-2], 'e': numbers[-1]}
