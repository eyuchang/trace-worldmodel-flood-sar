FROM python:3.12-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -e ".[ui]"
EXPOSE 8000
CMD ["trace-jepa-ui", "--host", "0.0.0.0", "--port", "8000"]
