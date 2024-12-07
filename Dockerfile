# Use the official Python image from the Docker Hub
FROM python:3.13

# Add Tini, a minimal init system for containers
ENV TINI_VERSION=v0.19.0
ADD https://github.com/krallin/tini/releases/download/${TINI_VERSION}/tini /tini
RUN chmod +x /tini

# Set the working directory inside the container
WORKDIR /root/env

# Prevent running interactive config during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies and remove the package list
RUN apt-get update && \
    apt-get install -y \
        libgeos-dev \
        libproj-dev \
        libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip and setuptools
RUN pip install --no-cache-dir --upgrade pip setuptools

# Copy the requirements file into the container
COPY requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create a mount point for external volumes
VOLUME /root/env

# Set the entrypoint to Tini
ENTRYPOINT ["/tini", "-g", "--"]

# Default command to run when the container starts
CMD ["/bin/bash"]