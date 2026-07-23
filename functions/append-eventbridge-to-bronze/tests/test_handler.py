import json
import logging

import pytest
import polars as pl
from unittest.mock import patch

from append_eventbridge_to_bronze.handler import (
    BronzeShapeError,
    MalformedEventError,
    RebuildOrAppendToBronze,
    S3PutObjectParser,
    append_to_bronze,
    rebuild_bronze,
)


def make_sqs_event(s3_paths, message_id="test-msg"):
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
                "messageId": message_id,
                "body": json.dumps({"Records": records}),
                "attributes": {
                    "SentTimestamp": "1768668597226",
                    "ApproximateFirstReceiveTimestamp": "1768668597236",
                },
            }
        ]
    }


def make_df(n=2):
    return pl.DataFrame(
        {
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
        },
        schema=RebuildOrAppendToBronze.input_schema(),
    )


def make_ndjson_file(tmp_path, n=2):
    df = make_df(n)
    path = tmp_path / "input.ndjson"
    df.write_ndjson(path)
    return str(path)


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

    def test_missing_attributes_raises_malformed_event_error(self):
        event = {"Records": [{"messageId": "bad-msg", "body": "{}"}]}
        with pytest.raises(MalformedEventError, match="bad-msg"):
            list(self.parser.objects(event, {}))

    def test_unparseable_body_raises_malformed_event_error(self):
        event = {
            "Records": [{
                "messageId": "bad-json",
                "body": "not json",
                "attributes": {
                    "SentTimestamp": "1768668597226",
                    "ApproximateFirstReceiveTimestamp": "1768668597236",
                },
            }]
        }
        with pytest.raises(MalformedEventError, match="bad-json"):
            list(self.parser.objects(event, {}))

    def test_s3_record_missing_bucket_raises_malformed_event_error(self):
        event = {
            "Records": [{
                "messageId": "missing-bucket",
                "body": json.dumps({"Records": [{"eventName": "ObjectCreated:Put", "s3": {}}]}),
                "attributes": {
                    "SentTimestamp": "1768668597226",
                    "ApproximateFirstReceiveTimestamp": "1768668597236",
                },
            }]
        }
        with pytest.raises(MalformedEventError, match="missing-bucket"):
            list(self.parser.objects(event, {}))


class TestRebuildOrAppendToBronzeCast:
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


class TestRebuildOrAppendToBronzeRunMocked:
    """Exercises run()'s orchestration logic (shape check, dispatch) in isolation."""

    def setup_method(self):
        self.handler = RebuildOrAppendToBronze(logging.getLogger("test"))

    def test_run_raises_bronze_shape_error_when_shape_changes(self):
        original = make_df(3)
        shrunken = make_df(2)
        with patch.object(self.handler, "read", return_value=original), \
             patch.object(self.handler, "cast", return_value=shrunken), \
             patch.object(self.handler, "write"):
            with pytest.raises(BronzeShapeError, match="Shape changed"):
                self.handler.run(["s3://bucket/file"], "append")

    def test_run_returns_200_on_success(self):
        df = make_df()
        with patch.object(self.handler, "read", return_value=df), \
             patch.object(self.handler, "cast", return_value=df), \
             patch.object(self.handler, "write"):
            result = self.handler.run(["s3://bucket/file"], "append")
        assert result["statusCode"] == 200

    def test_append_passes_append_mode_and_transaction_id(self):
        df = make_df()
        with patch.object(self.handler, "read", return_value=df), \
             patch.object(self.handler, "cast", return_value=df), \
             patch.object(self.handler, "write") as mock_write:
            self.handler.append(["s3://bucket/file"], transaction_id="msg-1")
        mock_write.assert_called_once_with(df, "append", transaction_id="msg-1")

    def test_rebuild_passes_overwrite_mode_with_no_transaction_id(self):
        df = make_df()
        with patch.object(self.handler, "read", return_value=df), \
             patch.object(self.handler, "cast", return_value=df), \
             patch.object(self.handler, "write") as mock_write:
            self.handler.rebuild(["s3://bucket/file"])
        mock_write.assert_called_once_with(df, "overwrite", transaction_id=None)


class TestRead:
    def test_read_parses_real_ndjson_file(self, tmp_path):
        handler = RebuildOrAppendToBronze(logging.getLogger("test"))
        path = make_ndjson_file(tmp_path, n=3)

        df = handler.read([path])

        assert df.shape == (3, 9)
        assert df.schema == RebuildOrAppendToBronze.input_schema()


class TestWriteToDeltaRealIO:
    """Exercises the actual Polars/Delta write path (and idempotency check)
    against a local Delta table on disk, instead of mocking read/write away."""

    def test_write_creates_table_and_rows_are_readable(self, tmp_path):
        handler = RebuildOrAppendToBronze(logging.getLogger("test"))
        table_path = str(tmp_path / "bronze")
        df = handler.cast(make_df(2))

        handler._write_to_delta(table_path, df, "append")

        assert pl.read_delta(table_path).shape == (2, 9)

    def test_retrying_same_transaction_id_does_not_duplicate_rows(self, tmp_path):
        handler = RebuildOrAppendToBronze(logging.getLogger("test"))
        table_path = str(tmp_path / "bronze")
        df = handler.cast(make_df(2))

        handler._write_to_delta(table_path, df, "append", transaction_id="msg-1")
        handler._write_to_delta(table_path, df, "append", transaction_id="msg-1")

        assert pl.read_delta(table_path).shape == (2, 9)

    def test_different_transaction_ids_both_append(self, tmp_path):
        handler = RebuildOrAppendToBronze(logging.getLogger("test"))
        table_path = str(tmp_path / "bronze")
        df = handler.cast(make_df(2))

        handler._write_to_delta(table_path, df, "append", transaction_id="msg-1")
        handler._write_to_delta(table_path, df, "append", transaction_id="msg-2")

        assert pl.read_delta(table_path).shape == (4, 9)

    def test_overwrite_replaces_table_contents(self, tmp_path):
        handler = RebuildOrAppendToBronze(logging.getLogger("test"))
        table_path = str(tmp_path / "bronze")

        handler._write_to_delta(table_path, handler.cast(make_df(3)), "append")
        handler._write_to_delta(table_path, handler.cast(make_df(1)), "overwrite")

        assert pl.read_delta(table_path).shape == (1, 9)


class TestLambdaEntryPoints:
    def test_append_to_bronze_derives_transaction_id_from_message_id(self, monkeypatch):
        monkeypatch.setenv("BRONZE_BUCKET", "some-bucket")
        event = make_sqs_event(["s3://bucket/a"], message_id="msg-42")

        with patch(
            "append_eventbridge_to_bronze.handler.RebuildOrAppendToBronze.append"
        ) as mock_append:
            append_to_bronze(event, {})

        mock_append.assert_called_once_with(["s3://bucket/a"], transaction_id="msg-42")

    def test_append_to_bronze_with_no_records_has_no_transaction_id(self, monkeypatch):
        monkeypatch.setenv("BRONZE_BUCKET", "some-bucket")

        with patch(
            "append_eventbridge_to_bronze.handler.RebuildOrAppendToBronze.append"
        ) as mock_append:
            append_to_bronze({"Records": []}, {})

        mock_append.assert_called_once_with([], transaction_id=None)

    def test_rebuild_bronze_globs_raw_prefix(self, monkeypatch):
        monkeypatch.setenv("BRONZE_BUCKET", "some-bucket")

        with patch(
            "append_eventbridge_to_bronze.handler.RebuildOrAppendToBronze.rebuild"
        ) as mock_rebuild:
            rebuild_bronze({}, {})

        mock_rebuild.assert_called_once_with(["s3://some-bucket/raw/**/*"])
