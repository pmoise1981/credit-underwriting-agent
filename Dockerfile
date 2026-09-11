FROM public.ecr.aws/lambda/python:3.12

COPY requirements.txt ${LAMBDA_TASK_ROOT}
RUN pip install -r requirements.txt --target "${LAMBDA_TASK_ROOT}"

COPY config.py tools.py guardrails.py agent.py lambda_handler.py ${LAMBDA_TASK_ROOT}

CMD ["lambda_handler.handler"]
