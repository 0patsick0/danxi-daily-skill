from __future__ import annotations

import unittest

from danxi_daily.security import normalize_allowed_hosts, require_https, validate_allowed_host


class SecurityTests(unittest.TestCase):
    def test_require_https_rejects_http(self) -> None:
        with self.assertRaises(ValueError):
            require_https("http://forum.fduhole.com/api")

    def test_allowlist_rejects_unknown_host(self) -> None:
        allowlist = normalize_allowed_hosts("forum.fduhole.com,api.fduhole.com")
        with self.assertRaises(ValueError):
            validate_allowed_host("https://evil.example.com/api", allowlist)


if __name__ == "__main__":
    unittest.main()
