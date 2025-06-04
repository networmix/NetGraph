# Stage 1: Base image with system dependencies
FROM python:3.13-slim AS base

# Prevent interactive config during installation
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies and cleanup
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y \
    build-essential \
    cmake \
    curl \
    wget \
    unzip \
    git \
    libgeos-dev \
    libproj-dev \
    libgdal-dev \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Stage 2: Build stage for Python packages
FROM base AS jupyterlab

# Set working directory for build
WORKDIR /app

# Copy project files needed for installation
COPY pyproject.toml .
COPY README.md .
COPY ngraph/ ./ngraph/

# Upgrade pip and setuptools
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Install build tools that might be needed
RUN pip install --no-cache-dir build twine

# Install Python packages
RUN pip install --no-cache-dir '.[dev]'

# Install JupyterLab and LSP
RUN pip install --no-cache-dir \
    jupyterlab \
    jupyterlab-lsp \
    python-lsp-server

# Cleanup unnecessary files from pip installations
RUN rm -rf /root/.cache/pip

# Stage 4: Final image
FROM jupyterlab AS final

# Add Tini for better signal handling and proper init
ENV TINI_VERSION=v0.19.0
ADD https://github.com/krallin/tini/releases/download/${TINI_VERSION}/tini /tini
RUN chmod +x /tini

# Set working directory
WORKDIR /root/env

# Create mount point
VOLUME /root/env

# Set entrypoint
ENTRYPOINT ["/tini", "-g", "--"]

# Default command to run when the container starts
CMD ["/bin/bash"]
