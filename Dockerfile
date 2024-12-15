# Stage 1: Base image with system dependencies
FROM python:3.13 AS base

# Prevent interactive config during installation
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies and cleanup
RUN apt-get update && \
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

# Upgrade pip and setuptools
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Copy requirements first to leverage cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Python packages
RUN pip install --no-cache-dir \
    numpy \
    pandas \
    matplotlib \
    seaborn \
    build \
    twine \
    pytest \
    pytest-cov \
    pytest-benchmark \
    pytest-mock \
    pylint \
    black

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