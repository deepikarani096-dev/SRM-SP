# ---- Base: Node with Debian (for reliable Python & build tooling) ----
FROM node:20-bullseye

# Set working directory
WORKDIR /app

# Install system dependencies (Python + build tools + MySQL client libs)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip \
    build-essential pkg-config \
    default-libmysqlclient-dev \
    curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# ---- Python virtual environment ----
RUN python3 -m venv /opt/pyenv
ENV PATH="/opt/pyenv/bin:${PATH}"

# Copy Python requirements early (cache-friendly layer)
COPY python_files/requirements.txt ./python_files/requirements.txt
RUN if [ -f "python_files/requirements.txt" ]; then \
      pip install --no-cache-dir -r python_files/requirements.txt; \
    fi

# ---- Node.js dependencies ----
COPY package*.json ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

# ---- App source (Node + Python files) ----
COPY . .

# Default environment
ENV NODE_ENV=production \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/python_files

# Healthcheck (adjust path if needed)
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=5 \
  CMD curl -fsS http://localhost:5001/health || exit 1

# Expose your backend API port
EXPOSE 5001

# Start Node server in dev mode (change to `start` in prod)
CMD ["npm", "run", "dev"]
