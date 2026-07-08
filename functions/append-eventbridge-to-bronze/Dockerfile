FROM python:3.14-slim AS deps

RUN pip install uv
WORKDIR /build
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-hashes -o requirements.txt


FROM public.ecr.aws/lambda/python:3.14 AS base

RUN pip install uv

COPY pyproject.toml uv.lock ./
RUN uv pip install --target ${LAMBDA_TASK_ROOT} -r pyproject.toml

COPY ./append_eventbridge_to_bronze ${LAMBDA_TASK_ROOT}/append_eventbridge_to_bronze


FROM base AS append-to-bronze
CMD ["append_eventbridge_to_bronze.handler.append_to_bronze"]

FROM base AS rebuild-bronze
CMD ["append_eventbridge_to_bronze.handler.rebuild_bronze"]
