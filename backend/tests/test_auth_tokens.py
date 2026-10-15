from uuid import uuid4
import unittest

from fastapi import HTTPException

from app.api.auth import (
    _create_access_token,
    _decode_access_token,
    _hash_password,
    _verify_password,
)


class AuthTokenTests(unittest.TestCase):
    def test_password_hash_verifies_only_matching_password(self):
        password_hash = _hash_password("long-enough-password")
        self.assertTrue(_verify_password("long-enough-password", password_hash))
        self.assertFalse(_verify_password("different-password", password_hash))

    def test_signed_token_round_trips_user_id(self):
        user_id = uuid4()
        self.assertEqual(_decode_access_token(_create_access_token(str(user_id))), user_id)

    def test_tampered_token_is_rejected(self):
        token = _create_access_token(str(uuid4()))
        with self.assertRaises(HTTPException) as caught:
            _decode_access_token(token[:-1] + ("A" if token[-1] != "A" else "B"))
        self.assertEqual(caught.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
