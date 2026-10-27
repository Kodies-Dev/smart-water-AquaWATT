FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .
COPY etl ./etl
COPY model ./model
COPY anomalie ./anomalie
COPY aplikacja ./aplikacja
COPY testy ./testy
COPY sql ./sql
ENTRYPOINT ["python", "main.py"]
CMD ["wszystko"]
