FROM python:3.14-slim AS deps

RUN pip install poetry
WORKDIR /build
COPY pyproject.toml poetry.lock ./
RUN poetry export -f requirements.txt --without-hashes --output requirements.txt


FROM public.ecr.aws/lambda/python:3.14 AS base

COPY --from=deps /build/requirements.txt .
RUN pip install -r requirements.txt --target ${LAMBDA_TASK_ROOT}
COPY ./append_eventbridge_to_bronze ${LAMBDA_TASK_ROOT}/append_eventbridge_to_bronze


FROM base AS append-to-bronze
CMD ["append_eventbridge_to_bronze.handler.append_to_bronze"]

FROM base AS rebuild-bronze
CMD ["append_eventbridge_to_bronze.handler.rebuild_bronze"]
