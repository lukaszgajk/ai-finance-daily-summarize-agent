FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Kontener nie wyłączy się od razu po starcie, pozwoli nam wejść do środka
CMD ["tail", "-f", "/dev/null"]