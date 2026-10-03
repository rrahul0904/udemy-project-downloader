import socket
import unittest

from app.fetch_safety import (
    FetchPolicy,
    FetchSafetyError,
    validate_connected_peer,
    validate_fetch_target,
    validate_redirect_target,
)


def resolver_for(*addresses):
    def resolve(host, port):
        return [
            (socket.AF_INET6 if ":" in address else socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port, 0, 0) if ":" in address else (address, port))
            for address in addresses
        ]

    return resolve


class FetchSafetyTests(unittest.TestCase):
    def test_accepts_public_http_and_https_targets(self):
        https = validate_fetch_target(
            "https://EXAMPLE.com./media/video.mp4?x=1#fragment",
            resolver=resolver_for("93.184.216.34"),
        )
        self.assertEqual(https.host, "example.com")
        self.assertEqual(https.port, 443)
        self.assertEqual(https.url, "https://example.com/media/video.mp4?x=1")
        self.assertEqual(https.resolved_ips, frozenset({"93.184.216.34"}))

        http = validate_fetch_target(
            "http://example.com/video.mp4",
            resolver=resolver_for("93.184.216.34"),
        )
        self.assertEqual(http.port, 80)

    def test_accepts_public_ip_literal_without_dns(self):
        def resolver_should_not_run(host, port):
            raise AssertionError("resolver must not run for an IP literal")

        target = validate_fetch_target(
            "https://8.8.8.8/media.mp4",
            resolver=resolver_should_not_run,
        )
        self.assertEqual(target.resolved_ips, frozenset({"8.8.8.8"}))

    def test_rejects_non_http_credentials_and_nonstandard_ports(self):
        samples = [
            "ftp://example.com/file",
            "https://user:secret@example.com/file",
            "https://example.com:8443/file",
            "http://example.com:443/file",
            "https://",
        ]
        for value in samples:
            with self.subTest(value=value), self.assertRaises(FetchSafetyError):
                validate_fetch_target(value, resolver=resolver_for("93.184.216.34"))

    def test_rejects_non_public_ipv4_and_ipv6_ranges(self):
        blocked = [
            "127.0.0.1",
            "10.0.0.8",
            "172.16.0.10",
            "192.168.1.5",
            "169.254.10.20",
            "0.0.0.0",
            "224.0.0.1",
            "::1",
            "fc00::1",
            "fe80::1",
        ]
        for address in blocked:
            with self.subTest(address=address), self.assertRaises(FetchSafetyError):
                validate_fetch_target(
                    "https://media.example/file",
                    resolver=resolver_for(address),
                )

    def test_fails_closed_when_dns_returns_mixed_public_and_private_addresses(self):
        with self.assertRaises(FetchSafetyError):
            validate_fetch_target(
                "https://media.example/file",
                resolver=resolver_for("93.184.216.34", "10.0.0.4"),
            )

    def test_rejects_empty_or_invalid_resolver_results(self):
        with self.assertRaises(FetchSafetyError):
            validate_fetch_target("https://media.example/file", resolver=lambda host, port: [])

        with self.assertRaises(FetchSafetyError):
            validate_fetch_target(
                "https://media.example/file",
                resolver=lambda host, port: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("not-an-ip", port))],
            )

    def test_revalidates_every_redirect_target(self):
        allowed = validate_redirect_target(
            "https://media.example/start",
            "/next/file.mp4",
            redirect_count=0,
            resolver=resolver_for("93.184.216.34"),
        )
        self.assertEqual(allowed.host, "media.example")

        with self.assertRaises(FetchSafetyError):
            validate_redirect_target(
                "https://media.example/start",
                "http://localhost/internal",
                redirect_count=0,
                resolver=resolver_for("127.0.0.1"),
            )

    def test_enforces_redirect_budget(self):
        policy = FetchPolicy(max_redirects=2)
        with self.assertRaises(FetchSafetyError):
            validate_redirect_target(
                "https://media.example/start",
                "/third",
                redirect_count=2,
                policy=policy,
                resolver=resolver_for("93.184.216.34"),
            )
        with self.assertRaises(FetchSafetyError):
            validate_redirect_target(
                "https://media.example/start",
                "/next",
                redirect_count=-1,
                policy=policy,
                resolver=resolver_for("93.184.216.34"),
            )

    def test_peer_validation_blocks_dns_rebinding_and_address_drift(self):
        target = validate_fetch_target(
            "https://media.example/file",
            resolver=resolver_for("93.184.216.34"),
        )
        self.assertEqual(validate_connected_peer("93.184.216.34", target), "93.184.216.34")

        for peer in ["10.0.0.9", "127.0.0.1", "8.8.8.8"]:
            with self.subTest(peer=peer), self.assertRaises(FetchSafetyError):
                validate_connected_peer(peer, target)

    def test_resolver_failure_is_a_policy_failure(self):
        def failing_resolver(host, port):
            raise socket.gaierror("no answer")

        with self.assertRaises(FetchSafetyError):
            validate_fetch_target("https://media.example/file", resolver=failing_resolver)


if __name__ == "__main__":
    unittest.main()
