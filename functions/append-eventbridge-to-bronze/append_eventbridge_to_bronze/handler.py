import logging
import os
import json
import polars as pl
import tempfile
import datetime
import sys

def _setup_polars_tmp():
    temp_dir = tempfile.mkdtemp(dir="/tmp")
    os.environ["POLARS_TEMP_DIR"] = temp_dir

_setup_polars_tmp()

for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

class S3PutObjectParser:
    def __init__(self, logger):
        self.logger = logger

    def objects(self, event, context):
        for sqs_message in event.get('Records', []):
            sent_timestamp = datetime.datetime.fromtimestamp(int(sqs_message['attributes']['SentTimestamp']) / 1000)
            first_receive_timestamp = datetime.datetime.fromtimestamp(int(sqs_message['attributes']['ApproximateFirstReceiveTimestamp']) / 1000)

            self.logger.info(f"Handling SQS message-id={sqs_message.get('messageId')}, sent_timestamp={sent_timestamp.isoformat()}, first_receive={first_receive_timestamp.isoformat()}")

            parsed = json.loads(sqs_message.get('body'))
            for s3_record in parsed.get('Records', []):
                self.logger.info(f"event={s3_record['eventName']}, path=s3://{s3_record['s3']['bucket']['name']}/{s3_record['s3']['object']['key']}, time={s3_record['eventTime']}")
                yield f"s3://{s3_record['s3']['bucket']['name']}/{s3_record['s3']['object']['key']}"

class RebuildOrAppendToBronze:
    def __init__(self, logger):
        self.logger = logger

    @staticmethod
    def input_schema():
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

    def read(self, paths):
        self.logger.info(f"going to read: {paths}")
        return pl.read_ndjson(paths, schema=self.input_schema())

    def append(self, paths):
        return self.run(paths, "append")

    def rebuild(self, paths):
        return self.run(paths, "overwrite")

    def run(self, paths, write_mode):
        df = self.read(paths)
        original_shape = df.shape
        self.logger.info(f"Read DF: {original_shape}")
        self.logger.info(f"Schema: {df.schema}")

        df = self.cast(df)
        self.logger.info(f"Cast DF: {df.shape}")
        self.logger.info(f"Schema: {df.schema}")

        if original_shape != df.shape:
            raise Exception("Shape is no longer the same after casting")

        self.write(df, write_mode)

        return {
            "statusCode": 200,
            "body": {"paths": paths, "write_mode": write_mode}
        }

    def cast(self, df):
        return df.with_columns(
            pl.col("time").str.to_datetime(time_zone='UTC'),
            pl.col("detail").struct.with_fields(
                pl.field("payload").struct.with_fields(
                    pl.field("scanned_at").str.to_datetime(time_zone='UTC')
                )
            )
        )

    def write(self, df, mode):
        path = f"s3://{os.environ['BRONZE_BUCKET']}/bronze/"
        self.logger.info(f"Going to write {path}, mode={mode}")
        df.write_delta(path, mode=mode)

def append_to_bronze(event, context):
    logger = logging.getLogger(RebuildOrAppendToBronze.__name__)
    logger.info(event)

    parser = S3PutObjectParser(logging.getLogger(S3PutObjectParser.__name__))
    handler = RebuildOrAppendToBronze(logger)
    return handler.append(list(parser.objects(event, context)))

def rebuild_bronze(event, context):
    handler = RebuildOrAppendToBronze(logging.getLogger(RebuildOrAppendToBronze.__name__))
    return handler.rebuild([f"s3://{os.environ['BRONZE_BUCKET']}/raw/**/*"])
