import logging
import os
import boto3
import json
from urllib.parse import unquote
import polars as pl
import tempfile
import datetime
import sys

temp_dir = tempfile.mkdtemp(dir="/tmp")
os.environ["POLARS_TEMP_DIR"] = temp_dir
#logging.basicConfig(level=logging.DEBUG)

for handler in logging.root.handlers[:]:
    logging.info(f"Remove handler: {handler}")
    logging.root.removeHandler(handler)

logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)

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
    def __init__(self, s3_client, logger):
        self.s3_client = s3_client
        self.logger = logger

    def input_schema(self):
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
        return pl.read_ndjson(paths, schema = self.input_schema())

    def append(self, paths):
        return self.run(paths, "append")

    def rebuild(self, paths):
        return self.run(paths, "overwrite")

    def run(self, paths, write_mode):
        print("running!")
        print((paths, write_mode))
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

        print(df.shape)
        print("Done!")

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

def get_handler_object(event, context):
    logger = logging.getLogger(RebuildOrAppendToBronze.__name__)

    s3_client = boto3.client('s3', region_name="ap-southeast-1")

    return RebuildOrAppendToBronze(s3_client, logger)

def append_to_bronze(event, context):
    l = logging.getLogger("append_to_bronze")
    l.info(event)

    logger = logging.getLogger(S3PutObjectParser.__name__)
    parser = S3PutObjectParser(logger)

    handler = get_handler_object(event, context)
    return handler.append(list(parser.objects(event, context)))

def rebuild_bronze(event, context):
    handler = get_handler_object(event, context)
    return handler.rebuild([f"s3://{os.environ['BRONZE_BUCKET']}/raw/**/*"])

"""
def __main__():
    rebuild_bronze(json.load(open("event.json")), {})

if __name__ == '__main__':
    __main__()
"""
