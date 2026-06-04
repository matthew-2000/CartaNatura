FROM python:3

ENV PYTHONUNBUFFERED 1

WORKDIR /app

COPY ./requirements.txt /app/requirements.txt

RUN pip install -r requirements.txt && pip install --upgrade pip

COPY . .

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]