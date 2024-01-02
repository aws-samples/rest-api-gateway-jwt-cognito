FROM public.ecr.aws/lambda/python:3.11

COPY requirements.txt requirements.txt

RUN pip3 install -r requirements.txt

COPY app.py app.py

CMD [ "app.lambda_handler"]
