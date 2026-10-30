FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY seatcrew ./seatcrew
COPY examples ./examples
RUN pip install --no-cache-dir .
VOLUME ["/data"]
WORKDIR /data
EXPOSE 8787
# Binds 0.0.0.0 inside the container; publish only to localhost: docker run -p 127.0.0.1:8787:8787 --env-file .env -v $PWD:/data tradecrew
CMD ["tradecrew", "start", "--host", "0.0.0.0", "--port", "8787"]
