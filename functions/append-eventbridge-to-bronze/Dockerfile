FROM public.ecr.aws/lambda/python:3.14 AS base

COPY requirements.txt ${LAMBDA_TASK_ROOT}
RUN pip install -r requirements.txt --target ${LAMBDA_TASK_ROOT}

COPY ./ ${LAMBDA_TASK_ROOT}

FROM base AS append-to-bronze
CMD ["append_eventbridge_to_bronze.handler.append_to_bronze"]

FROM base AS rebuild-bronze
CMD ["append_eventbridge_to_bronze.handler.rebuild_bronze"]
