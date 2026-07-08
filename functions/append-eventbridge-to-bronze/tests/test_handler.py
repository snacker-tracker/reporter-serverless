import json
import logging
import pytest
import polars as pl
from unittest.mock import patch
from append_eventbridge_to_bronze.handler import S3PutObjectParser, RebuildOrAppendToBronze


def make_sqs_event(s3_paths):
    records = []
    for path in s3_paths:
        without_prefix = path.removeprefix("s3://")
        bucket, key = without_prefix.split("/", 1)
        records.append({
            "s3": {"bucket": {"name": bucket}, "object": {"key": key}},
            "eventName": "ObjectCreated:Put",
            "eventTime": "2026-01-17T16:49:56Z",
        })
    return {
        "Records": [
            {
                "messageId": "test-msg",
                "body": json.dumps({"Records": records}),
                "attributes": {
                    "SentTimestamp": "1768668597226",
                    "ApproximateFirstReceiveTimestamp": "1768668597236",
                },
            }
        ]
    }


def make_df(n=2):
    return pl.DataFrame({
        "version": ["0"] * n,
        "id": [f"id-{i}" for i in range(n)],
        "detail-type": ["Scan"] * n,
        "source": ["custom.scanner"] * n,
        "account": ["123456789012"] * n,
        "time": ["2024-01-01T00:00:00Z"] * n,
        "region": ["ap-southeast-1"] * n,
        "resources": [[] for _ in range(n)],
        "detail": [
            {
                "client_ip": "1.2.3.4",
                "request_id": f"req-{i}",
                "payload": {
                    "code": "ABC123",
                    "location": "home",
                    "scanned_at": "2024-01-01T00:00:00Z",
                },
                "apiKeyId": "key-1",
            }
            for i in range(n)
        ],
    })


class TestS3PutObjectParser:
    def setup_method(self):
        self.parser = S3PutObjectParser(logging.getLogger("test"))

    def test_yields_s3_paths(self):
        event = make_sqs_event(["s3://my-bucket/path/to/file"])
        assert list(self.parser.objects(event, {})) == ["s3://my-bucket/path/to/file"]

    def test_empty_records_yields_nothing(self):
        assert list(self.parser.objects({"Records": []}, {})) == []

    def test_multiple_s3_records_in_one_message(self):
        expected = ["s3://bucket/a", "s3://bucket/b"]
        assert list(self.parser.objects(make_sqs_event(expected), {})) == expected


class TestRebuildOrAppendToBronze:
    def setup_method(self):
        self.handler = RebuildOrAppendToBronze(logging.getLogger("test"))

    def test_cast_converts_time_to_datetime(self):
        df = self.handler.cast(make_df())
        assert df["time"].dtype == pl.Datetime

    def test_cast_converts_scanned_at_to_datetime(self):
        df = self.handler.cast(make_df())
        scanned_at = df["detail"].struct.field("payload").struct.field("scanned_at")
        assert scanned_at.dtype == pl.Datetime

    def test_cast_preserves_shape(self):
        df = make_df(5)
        assert self.handler.cast(df).shape == df.shape

    def test_run_raises_when_shape_changes(self):
        original = make_df(3)
        shrunken = make_df(2)
        with patch.object(self.handler, "read", return_value=original), \
             patch.object(self.handler, "cast", return_value=shrunken), \
             patch.object(self.handler, "write"):
            with pytest.raises(Exception, match="Shape"):
                self.handler.run(["s3://bucket/file"], "append")

    def test_run_returns_200_on_success(self):
        df = make_df()
        with patch.object(self.handler, "read", return_value=df), \
             patch.object(self.handler, "cast", return_value=df), \
             patch.object(self.handler, "write"):
            result = self.handler.run(["s3://bucket/file"], "append")
        assert result["statusCode"] == 200

    def test_append_passes_append_mode(self):
        df = make_df()
        with patch.object(self.handler, "read", return_value=df), \
             patch.object(self.handler, "cast", return_value=df), \
             patch.object(self.handler, "write") as mock_write:
            self.handler.append(["s3://bucket/file"])
        mock_write.assert_called_once_with(df, "append")

    def test_rebuild_passes_overwrite_mode(self):
        df = make_df()
        with patch.object(self.handler, "read", return_value=df), \
             patch.object(self.handler, "cast", return_value=df), \
             patch.object(self.handler, "write") as mock_write:
            self.handler.rebuild(["s3://bucket/file"])
        mock_write.assert_called_once_with(df, "overwrite")
