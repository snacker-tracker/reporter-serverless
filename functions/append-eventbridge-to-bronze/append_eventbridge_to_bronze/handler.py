import datetime
import json
import logging
import os
import sys
import tempfile
from typing import Any, Iterator

import polars as pl
from deltalake import DeltaTable
from deltalake.exceptions import TableNotFoundError
from deltalake.transaction import CommitProperties, Transaction


def _setup_polars_tmp() -> None:
    temp_dir = tempfile.mkdtemp(dir="/tmp")
    os.environ["POLARS_TEMP_DIR"] = temp_dir

_setup_polars_tmp()

for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

logging.basicConfig(level=logging.INFO, stream=sys.stdout)


class MalformedEventError(Exception):
    pass


class BronzeShapeError(Exception):
    pass


class S3PutObjectParser:
    def __init__(self, logger: logging.Logger) -> None:
        self.logger = logger

    def objects(self, event: dict[str, Any], context: Any) -> Iterator[str]:
        for sqs_message in event.get('Records', []):
            message_id = sqs_message.get('messageId')

            try:
                attributes = sqs_message['attributes']
                sent_timestamp = datetime.datetime.fromtimestamp(int(attributes['SentTimestamp']) / 1000)
                first_receive_timestamp = datetime.datetime.fromtimestamp(int(attributes['ApproximateFirstReceiveTimestamp']) / 1000)
                parsed = json.loads(sqs_message['body'])
            except (KeyError, TypeError, json.JSONDecodeError) as exc:
                raise MalformedEventError(
                    f"SQS message-id={message_id} is not a valid S3 event notification: {exc}"
                ) from exc

            self.logger.info(f"Handling SQS message-id={message_id}, sent_timestamp={sent_timestamp.isoformat()}, first_receive={first_receive_timestamp.isoformat()}")

            for s3_record in parsed.get('Records', []):
                try:
                    bucket = s3_record['s3']['bucket']['name']
                    key = s3_record['s3']['object']['key']
                    event_name = s3_record['eventName']
                    event_time = s3_record['eventTime']
                except KeyError as exc:
                    raise MalformedEventError(
                        f"SQS message-id={message_id} contains a malformed S3 record: {exc}"
                    ) from exc

                self.logger.info(f"event={event_name}, path=s3://{bucket}/{key}, time={event_time}")
                yield f"s3://{bucket}/{key}"

class RebuildOrAppendToBronze:
    def __init__(self, logger: logging.Logger) -> None:
        self.logger = logger

    @staticmethod
    def input_schema() -> pl.Schema:
        return pl.Schema({
            'version': pl.String,
            'id': pl.String,
            'detail-type': pl.String,
            'source': pl.String,
            'account': pl.String,
            'time': pl.String,
            'region': pl.String,
            'resources': pl.List(pl.String),
            'detail': pl.Struct({
                'client_ip': pl.String,
                'request_id': pl.String,
                'payload': pl.Struct({
                    'code': pl.String,
                    'location': pl.String,
                    'scanned_at': pl.String
                }),
                'apiKeyId': pl.String
            })
        })

    def read(self, paths: list[str]) -> pl.DataFrame:
        self.logger.info(f"going to read: {paths}")
        return pl.read_ndjson(paths, schema=self.input_schema())

    def append(self, paths: list[str], transaction_id: str | None = None) -> dict[str, Any]:
        return self.run(paths, "append", transaction_id=transaction_id)

    def rebuild(self, paths: list[str]) -> dict[str, Any]:
        return self.run(paths, "overwrite")

    def run(self, paths: list[str], write_mode: str, transaction_id: str | None = None) -> dict[str, Any]:
        df = self.read(paths)
        original_shape = df.shape
        self.logger.info(f"Read DF: {original_shape}")
        self.logger.info(f"Schema: {df.schema}")

        df = self.cast(df)
        self.logger.info(f"Cast DF: {df.shape}")
        self.logger.info(f"Schema: {df.schema}")

        if original_shape != df.shape:
            raise BronzeShapeError(f"Shape changed after casting: {original_shape} -> {df.shape}")

        self.write(df, write_mode, transaction_id=transaction_id)

        return {
            "statusCode": 200,
            "body": {"paths": paths, "write_mode": write_mode}
        }

    def cast(self, df: pl.DataFrame) -> pl.DataFrame:
        return df.with_columns(
            pl.col("time").str.to_datetime(time_zone='UTC'),
            pl.col("detail").struct.with_fields(
                pl.field("payload").struct.with_fields(
                    pl.field("scanned_at").str.to_datetime(time_zone='UTC')
                )
            )
        )

    def write(self, df: pl.DataFrame, mode: str, transaction_id: str | None = None) -> None:
        prefix = os.environ.get("BRONZE_PREFIX", "bronze")
        path = f"s3://{os.environ['BRONZE_BUCKET']}/{prefix}/"
        self._write_to_delta(path, df, mode, transaction_id=transaction_id)

    def _write_to_delta(self, path: str, df: pl.DataFrame, mode: str, transaction_id: str | None = None) -> None:
        delta_write_options: dict[str, Any] = {}

        if transaction_id is not None:
            if self._already_committed(path, transaction_id):
                self.logger.info(f"Skipping write, transaction_id={transaction_id} already committed at {path}")
                return
            delta_write_options["commit_properties"] = CommitProperties(
                app_transactions=[Transaction(app_id=transaction_id, version=0)]
            )

        self.logger.info(f"Going to write {path}, mode={mode}, transaction_id={transaction_id}")
        df.write_delta(path, mode=mode, delta_write_options=delta_write_options)

    @staticmethod
    def _already_committed(path: str, transaction_id: str) -> bool:
        try:
            table = DeltaTable(path)
        except TableNotFoundError:
            return False
        return table.transaction_version(transaction_id) is not None

def append_to_bronze(event: dict[str, Any], context: Any) -> dict[str, Any]:
    logger = logging.getLogger(RebuildOrAppendToBronze.__name__)
    logger.debug(event)

    parser = S3PutObjectParser(logging.getLogger(S3PutObjectParser.__name__))
    handler = RebuildOrAppendToBronze(logger)

    message_ids = [r['messageId'] for r in event.get('Records', []) if r.get('messageId')]
    transaction_id = ":".join(message_ids) if message_ids else None

    return handler.append(list(parser.objects(event, context)), transaction_id=transaction_id)

def rebuild_bronze(event: dict[str, Any], context: Any) -> dict[str, Any]:
    handler = RebuildOrAppendToBronze(logging.getLogger(RebuildOrAppendToBronze.__name__))
    raw_prefix = os.environ.get("RAW_PREFIX", "raw")
    return handler.rebuild([f"s3://{os.environ['BRONZE_BUCKET']}/{raw_prefix}/**/*"])
