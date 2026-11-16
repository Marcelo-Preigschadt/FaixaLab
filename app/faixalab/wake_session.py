"""Site sessions signed off the Codespace and checked with a public key."""
import hmac
import re
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


TOKEN = re.compile(r'([0-9]{1,12})\.([a-f0-9]{64})\.([a-f0-9]{128})')


class WakeSession:
    def __init__(self, public, private=None):
        self.public = public
        self.private = private

    @classmethod
    def from_dispatch_token(cls, dispatch_token):
        seed = hmac.digest(dispatch_token.encode(), b'FaixaLab portal session signing v1', 'sha256')
        private = Ed25519PrivateKey.from_private_bytes(seed)
        return cls(private.public_key(), private)

    @classmethod
    def from_public_key(cls, public_key):
        return cls(Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key)))

    def issue(self, scope, expires, account):
        value = f'{expires}.{account}'
        signature = self.private.sign(f'{scope}:{value}'.encode()).hex()
        return f'{value}.{signature}'

    def verify(self, token, scope):
        match = TOKEN.fullmatch(token)
        if match is None or int(match[1]) <= time.time():
            return None
        expires, account, signature = match.groups()
        try:
            self.public.verify(bytes.fromhex(signature), f'{scope}:{expires}.{account}'.encode())
        except InvalidSignature:
            return None
        return account
