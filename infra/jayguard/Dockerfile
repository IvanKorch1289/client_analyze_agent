# Jay Guard - PII Protection Proxy
FROM python:3.12-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir \
    fastapi==0.125.0 \
    uvicorn==0.38.0 \
    httpx==0.28.1 \
    presidio-analyzer==2.2.355 \
    presidio-anonymizer==2.2.355 \
    python-dotenv==1.1.1

# Download spaCy model for Presidio
RUN python -m spacy download en_core_web_lg

# Copy application
COPY main.py .

# Run as non-root user
RUN useradd -r -s /bin/false appuser
USER appuser

EXPOSE 8090

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8090"]
