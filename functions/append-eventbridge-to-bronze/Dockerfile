FROM public.ecr.aws/lambda/python:3.14 AS lambda

RUN pip install uv

COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-hashes --no-emit-project | uv pip install --target ${LAMBDA_TASK_ROOT} -r -

COPY ./append_eventbridge_to_bronze ${LAMBDA_TASK_ROOT}/append_eventbridge_to_bronze
