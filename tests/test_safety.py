import unittest

from app.safety import UrlValidationError, normalize_supported_url, normalize_udemy_url, slug_from_url


class SafetyTests(unittest.TestCase):
    def test_accepts_udemy_course_urls(self):
        self.assertEqual(
            normalize_udemy_url("http://www.udemy.com/course/python-101/?coupon=abc"),
            "https://www.udemy.com/course/python-101/?coupon=abc",
        )
        normalized = normalize_supported_url("http://www.udemy.com/course/python-101/?coupon=abc")
        self.assertEqual(normalized.platform, "udemy")
        self.assertEqual(normalized.url, "https://www.udemy.com/course/python-101/?coupon=abc")

    def test_accepts_udemy_business_subdomains(self):
        self.assertEqual(
            normalize_udemy_url("https://example.udemy.com/course/python-101/learn/"),
            "https://example.udemy.com/course/python-101/learn/",
        )

    def test_rejects_non_udemy_urls(self):
        with self.assertRaises(UrlValidationError):
            normalize_udemy_url("https://example.com/?next=https://www.udemy.com/course/x/")

    def test_accepts_youtube_video_urls(self):
        normalized = normalize_supported_url("http://www.youtube.com/watch?v=abc123")
        self.assertEqual(normalized.platform, "youtube")
        self.assertEqual(normalized.url, "https://www.youtube.com/watch?v=abc123")

    def test_accepts_youtu_be_urls(self):
        normalized = normalize_supported_url("https://youtu.be/abc123?t=42")
        self.assertEqual(normalized.platform, "youtube")
        self.assertEqual(normalized.url, "https://youtu.be/abc123?t=42")

    def test_accepts_youtube_playlist_urls(self):
        normalized = normalize_supported_url("https://www.youtube.com/playlist?list=PLabc")
        self.assertEqual(normalized.platform, "youtube")

    def test_accepts_specific_enabled_social_items(self):
        samples = {
            "instagram": "https://www.instagram.com/reel/ABC123/",
            "tiktok": "https://www.tiktok.com/@creator/video/123456789",
            "facebook": "https://www.facebook.com/reel/123456789",
            "x": "https://x.com/creator/status/123456789",
            "pinterest": "https://www.pinterest.com/pin/123456789/",
            "linkedin": "https://www.linkedin.com/posts/example_video-activity-123",
            "dailymotion": "https://www.dailymotion.com/video/x123abc",
            "twitch": "https://www.twitch.tv/videos/123456789",
            "bluesky": "https://bsky.app/profile/example.com/post/3abc",
            "loom": "https://www.loom.com/share/abc123",
            "apple_podcasts": "https://podcasts.apple.com/us/podcast/show/id123?i=456",
        }
        for platform, url in samples.items():
            with self.subTest(platform=platform):
                normalized = normalize_supported_url(url)
                self.assertEqual(normalized.platform, platform)
                self.assertTrue(normalized.url.startswith("https://"))

    def test_rejects_profile_feed_and_bulk_social_urls(self):
        bad = [
            "https://www.instagram.com/example/",
            "https://www.tiktok.com/@creator",
            "https://www.facebook.com/example/videos/",
            "https://x.com/creator",
            "https://www.pinterest.com/example/",
            "https://www.linkedin.com/in/example/",
            "https://www.dailymotion.com/example",
            "https://www.twitch.tv/example",
            "https://bsky.app/profile/example.com",
            "https://www.loom.com/team-videos",
            "https://podcasts.apple.com/us/podcast/show/id123",
        ]
        for url in bad:
            with self.subTest(url=url), self.assertRaises(UrlValidationError):
                normalize_supported_url(url)

    def test_rejects_research_only_sources(self):
        for url in [
            "https://www.threads.net/@example/post/abc",
            "https://www.snapchat.com/spotlight/abc",
            "https://sharechat.com/post/abc",
            "https://mojapp.in/@example/video/abc",
            "https://giphy.com/gifs/abc",
            "https://tenor.com/view/abc",
        ]:
            with self.subTest(url=url), self.assertRaises(UrlValidationError):
                normalize_supported_url(url)

    def test_rejects_channel_wide_youtube_urls(self):
        with self.assertRaises(UrlValidationError):
            normalize_supported_url("https://www.youtube.com/@example/videos")

    def test_rejects_missing_scheme(self):
        with self.assertRaises(UrlValidationError):
            normalize_udemy_url("www.udemy.com/course/x/")

    def test_rejects_embedded_credentials(self):
        with self.assertRaises(UrlValidationError):
            normalize_supported_url("https://user:secret@www.youtube.com/watch?v=abc123")
        with self.assertRaises(UrlValidationError):
            normalize_supported_url("https://user:secret@www.udemy.com/course/python-101/")

    def test_rejects_nonstandard_ports(self):
        with self.assertRaises(UrlValidationError):
            normalize_supported_url("https://www.youtube.com:8443/watch?v=abc123")
        with self.assertRaises(UrlValidationError):
            normalize_supported_url("https://www.udemy.com:9000/course/python-101/")

    def test_normalization_drops_standard_ports_and_fragments(self):
        normalized = normalize_supported_url("https://www.youtube.com:443/watch?v=abc123#frag")
        self.assertEqual(normalized.url, "https://www.youtube.com/watch?v=abc123")

    def test_slug_from_url(self):
        self.assertEqual(slug_from_url("https://www.udemy.com/course/python-101/"), "python-101")
        self.assertEqual(
            slug_from_url("https://www.udemy.com/course/python-101/learn/quiz/123#overview"),
            "python-101",
        )
        self.assertEqual(slug_from_url("https://www.youtube.com/watch?v=abc123"), "abc123")
        self.assertEqual(slug_from_url("https://www.youtube.com/playlist?list=PLabc"), "PLabc")
        self.assertEqual(slug_from_url("https://www.instagram.com/reel/ABC123/"), "ABC123")


if __name__ == "__main__":
    unittest.main()
