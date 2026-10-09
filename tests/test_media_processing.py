import unittest

from app.media_processing import (
    BatchProcessingReceipt,
    CapabilityAvailability,
    CAPABILITY_REGISTRY,
    MediaAsset,
    MediaKind,
    MediaProcessingError,
    ProcessingReceipt,
    ProcessingState,
    get_processing_capability,
    plan_processing_job,
)


SHA_A = "a" * 64
SHA_B = "b" * 64


class MediaProcessingContractTests(unittest.TestCase):
    def _video_asset(self) -> MediaAsset:
        return MediaAsset(
            asset_id="asset-video-1",
            sha256=SHA_A,
            media_kind=MediaKind.VIDEO,
            size_bytes=1024,
            relative_path="media/video.mp4",
        )

    def test_media_asset_rejects_path_escape_and_invalid_digest(self):
        for relative_path in (
            "/etc/passwd",
            "../outside.mp4",
            "media/../outside.mp4",
            "media//video.mp4",
            "media/./video.mp4",
        ):
            with self.subTest(relative_path=relative_path), self.assertRaises(MediaProcessingError):
                MediaAsset(
                    asset_id="asset-1",
                    sha256=SHA_A,
                    media_kind=MediaKind.VIDEO,
                    size_bytes=1,
                    relative_path=relative_path,
                )

        with self.assertRaises(MediaProcessingError):
            MediaAsset(
                asset_id="asset-1",
                sha256="not-a-digest",
                media_kind=MediaKind.VIDEO,
                size_bytes=1,
                relative_path="media/video.mp4",
            )

    def test_unknown_operations_fail_closed(self):
        with self.assertRaises(MediaProcessingError):
            get_processing_capability("invented-operation")

    def test_registry_distinguishes_runtime_and_policy_states(self):
        self.assertEqual(
            CAPABILITY_REGISTRY["extract_audio"].availability,
            CapabilityAvailability.REQUIRES_DEPENDENCY,
        )
        self.assertEqual(
            CAPABILITY_REGISTRY["transcribe"].availability,
            CapabilityAvailability.UNAVAILABLE,
        )
        self.assertEqual(
            CAPABILITY_REGISTRY["speaker_labels"].availability,
            CapabilityAvailability.REQUIRES_HARDWARE,
        )
        self.assertEqual(
            CAPABILITY_REGISTRY["remove_watermark"].availability,
            CapabilityAvailability.POLICY_BLOCKED,
        )

    def test_only_explicitly_available_operation_can_be_planned(self):
        job = plan_processing_job(
            job_id="job-probe-1",
            input_asset=self._video_asset(),
            operation_id="probe",
            parameters={"include_streams": True},
        )
        self.assertEqual(job.operation_id, "probe")
        self.assertEqual(job.operation_version, "1")
        self.assertEqual(job.input_asset_id, "asset-video-1")
        self.assertTrue(job.parameters["include_streams"])

        with self.assertRaises(MediaProcessingError):
            plan_processing_job(
                job_id="job-transform-1",
                input_asset=self._video_asset(),
                operation_id="extract_audio",
            )

        with self.assertRaises(MediaProcessingError):
            plan_processing_job(
                job_id="job-policy-1",
                input_asset=self._video_asset(),
                operation_id="remove_watermark",
            )

    def test_job_parameters_are_copied_and_immutable(self):
        source = {"include_streams": True}
        job = plan_processing_job(
            job_id="job-probe-1",
            input_asset=self._video_asset(),
            operation_id="probe",
            parameters=source,
        )
        source["include_streams"] = False
        self.assertTrue(job.parameters["include_streams"])
        with self.assertRaises(TypeError):
            job.parameters["include_streams"] = False

    def test_completed_receipt_requires_derived_output_provenance(self):
        receipt = ProcessingReceipt(
            job_id="job-1",
            state=ProcessingState.COMPLETED,
            input_asset_id="asset-video-1",
            input_sha256=SHA_A,
            operation_id="transcode",
            operation_version="1",
            output_asset_id="asset-video-2",
            output_sha256=SHA_B,
        )
        self.assertEqual(receipt.state, ProcessingState.COMPLETED)

        with self.assertRaises(MediaProcessingError):
            ProcessingReceipt(
                job_id="job-1",
                state=ProcessingState.COMPLETED,
                input_asset_id="asset-video-1",
                input_sha256=SHA_A,
                operation_id="transcode",
                operation_version="1",
            )

    def test_non_completed_receipt_cannot_claim_output(self):
        with self.assertRaises(MediaProcessingError):
            ProcessingReceipt(
                job_id="job-1",
                state=ProcessingState.RUNNING,
                input_asset_id="asset-video-1",
                input_sha256=SHA_A,
                operation_id="transcode",
                operation_version="1",
                output_asset_id="asset-video-2",
                output_sha256=SHA_B,
            )

    def test_failed_receipt_requires_explicit_error_code(self):
        with self.assertRaises(MediaProcessingError):
            ProcessingReceipt(
                job_id="job-failed",
                state=ProcessingState.FAILED,
                input_asset_id="asset-video-1",
                input_sha256=SHA_A,
                operation_id="transcode",
                operation_version="1",
            )

        receipt = ProcessingReceipt(
            job_id="job-failed",
            state=ProcessingState.FAILED,
            input_asset_id="asset-video-1",
            input_sha256=SHA_A,
            operation_id="transcode",
            operation_version="1",
            error_code="processor_failed",
        )
        self.assertEqual(receipt.error_code, "processor_failed")

    def test_batch_failure_is_never_silently_promoted_to_complete(self):
        completed = ProcessingReceipt(
            job_id="job-ok",
            state=ProcessingState.COMPLETED,
            input_asset_id="asset-video-1",
            input_sha256=SHA_A,
            operation_id="transcode",
            operation_version="1",
            output_asset_id="asset-video-2",
            output_sha256=SHA_B,
        )
        failed = ProcessingReceipt(
            job_id="job-bad",
            state=ProcessingState.FAILED,
            input_asset_id="asset-video-3",
            input_sha256=SHA_A,
            operation_id="transcode",
            operation_version="1",
            error_code="processor_failed",
        )
        batch = BatchProcessingReceipt(batch_id="batch-1", items=(completed, failed))
        self.assertEqual(batch.state, ProcessingState.FAILED)

    def test_batch_rejects_duplicate_job_ids(self):
        failed_a = ProcessingReceipt(
            job_id="job-dup",
            state=ProcessingState.FAILED,
            input_asset_id="asset-video-1",
            input_sha256=SHA_A,
            operation_id="transcode",
            operation_version="1",
            error_code="failed_a",
        )
        failed_b = ProcessingReceipt(
            job_id="job-dup",
            state=ProcessingState.FAILED,
            input_asset_id="asset-video-2",
            input_sha256=SHA_B,
            operation_id="transcode",
            operation_version="1",
            error_code="failed_b",
        )
        with self.assertRaises(MediaProcessingError):
            BatchProcessingReceipt(batch_id="batch-dup", items=(failed_a, failed_b))


if __name__ == "__main__":
    unittest.main()
