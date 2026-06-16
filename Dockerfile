FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY depot/ depot/
COPY templates/ templates/
COPY static/ static/

EXPOSE 80

CMD ["python", "-m", "depot"]
