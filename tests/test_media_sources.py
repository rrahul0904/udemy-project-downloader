import unittest

from app.media_sources import (
    ImplementationState,
    MediaSourceError,
    PolicyMode,
    SOURCE_REGISTRY,
    detect_media_source,
)


class MediaSourceTests(unittest.TestCase):
    def test_detects_existing_sources_without_changing_existing_download_behavior(self):
        youtube = detect_media_source("https://www.youtube.com/watch?v=abc123")
        self.assertEqual(youtube.source.key, "youtube")
        self.assertEqual(youtube.source.implementation_state, ImplementationState.EXISTING)
        self.assertTrue(youtube.source.archive_enabled)
        self.assertEqual(youtube.canonical_host, "youtube.com")

        udemy = detect_media_source("https://company.udemy.com/course/python-101/")
        self.assertEqual(udemy.source.key, "udemy")
        self.assertEqual(udemy.source.policy_mode, PolicyMode.AUTHORIZED_SESSION)
        self.assertEqual(udemy.source.implementation_state, ImplementationState.EXISTING)
        self.assertTrue(udemy.source.archive_enabled)

    def test_verified_generic_sources_are_enabled(self):
        samples = {
            "instagram": "https://www.instagram.com/reel/abc/",
            "tiktok": "https://vm.tiktok.com/ZMabc/",
            "facebook": "https://www.facebook.com/watch/?v=123",
            "x": "https://x.com/example/status/123",
            "pinterest": "https://pin.it/abc123",
            "linkedin": "https://www.linkedin.com/posts/example_abc",
            "dailymotion": "https://www.dailymotion.com/video/abc",
            "twitch": "https://www.twitch.tv/videos/123",
            "bluesky": "https://bsky.app/profile/example/post/abc",
            "loom": "https://www.loom.com/share/abc",
            "apple_podcasts": "https://podcasts.apple.com/us/podcast/example/id123?i=456",
        }
        for key, url in samples.items():
            with self.subTest(key=key):
                detected = detect_media_source(url)
                self.assertEqual(detected.source.key, key)
                self.assertEqual(detected.source.implementation_state, ImplementationState.GENERIC_YTDLP)
                self.assertTrue(detected.source.archive_enabled)

    def test_unverified_donor_sources_remain_research_only(self):
        samples = {
            "threads": "https://www.threads.net/@example/post/abc",
            "snapchat": "https://www.snapchat.com/spotlight/abc",
            "sharechat": "https://sharechat.com/post/abc",
            "moj": "https://mojapp.in/@example/video/abc",
            "giphy": "https://giphy.com/gifs/abc",
            "tenor": "https://tenor.com/view/abc",
        }
        for key, url in samples.items():
            with self.subTest(key=key):
                detected = detect_media_source(url)
                self.assertEqual(detected.source.key, key)
                self.assertEqual(detected.source.implementation_state, ImplementationState.RESEARCH_ONLY)
                self.assertFalse(detected.source.archive_enabled)

    def test_registry_keeps_capabilities_separate_from_adapter_state(self):
        self.assertTrue(SOURCE_REGISTRY["instagram"].capabilities.carousel)
        self.assertTrue(SOURCE_REGISTRY["giphy"].capabilities.gif)
        self.assertTrue(SOURCE_REGISTRY["apple_podcasts"].capabilities.audio)
        self.assertFalse(SOURCE_REGISTRY["apple_podcasts"].capabilities.video)
        self.assertTrue(SOURCE_REGISTRY["instagram"].archive_enabled)
        self.assertFalse(SOURCE_REGISTRY["giphy"].archive_enabled)

    def test_accepts_true_subdomains_and_known_aliases(self):
        self.assertEqual(
            detect_media_source("https://music.youtube.com/watch?v=abc").source.key,
            "youtube",
        )
        self.assertEqual(detect_media_source("https://youtu.be/abc").source.key, "youtube")
        self.assertEqual(detect_media_source("https://twitter.com/a/status/1").source.key, "x")
        self.assertEqual(detect_media_source("https://fb.watch/abc/").source.key, "facebook")

    def test_rejects_lookalike_hosts(self):
        bad = [
            "https://youtube.com.evil.example/watch?v=abc",
            "https://notyoutube.com/watch?v=abc",
            "https://instagram.com.evil.example/reel/abc",
            "https://x.com.evil.example/a/status/1",
            "https://udemy.com.evil.example/course/x/",
        ]
        for url in bad:
            with self.subTest(url=url), self.assertRaises(MediaSourceError):
                detect_media_source(url)

    def test_rejects_malformed_or_unsafe_url_shapes(self):
        bad = [
            "youtube.com/watch?v=abc",
            "ftp://youtube.com/watch?v=abc",
            "https://user:secret@youtube.com/watch?v=abc",
            "https://youtube.com:8443/watch?v=abc",
            "https://",
            "not a url",
        ]
        for url in bad:
            with self.subTest(url=url), self.assertRaises(MediaSourceError):
                detect_media_source(url)

    def test_rejects_unknown_sources(self):
        with self.assertRaises(MediaSourceError):
            detect_media_source("https://example.com/video/123")


if __name__ == "__main__":
    unittest.main()
