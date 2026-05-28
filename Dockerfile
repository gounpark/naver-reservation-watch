FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium

COPY naver_reservation_watch.py .

CMD ["python", "naver_reservation_watch.py", "--headless", "--no-sound", "--continue-after-alert"]
