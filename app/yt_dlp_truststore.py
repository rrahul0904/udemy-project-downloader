from __future__ import annotations

import yt_dlp

try:
    import truststore

    truststore.inject_into_ssl()
except Exception:
    pass

from yt_dlp.extractor import udemy
from yt_dlp.utils import unescapeHTML

_original_extract_course_info = udemy.UdemyIE._extract_course_info


def _extract_course_info_with_next_fallback(self, webpage, video_id):
    try:
        return _original_extract_course_info(self, webpage, video_id)
    except Exception:
        course_id = self._search_regex(
            [
                r"courseId=(\d+)",
                r"/course/\d+x\d+/(\d+)_",
                r'"courseId"\s*:\s*(\d+)',
                r"&quot;courseId&quot;\s*:\s*(\d+)",
            ],
            webpage,
            "course id",
        )
        title = unescapeHTML(self._html_extract_title(webpage) or "")
        return course_id, title


udemy.UdemyIE._extract_course_info = _extract_course_info_with_next_fallback


if __name__ == "__main__":
    yt_dlp.main()
