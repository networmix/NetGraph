# Dockerfile for my PythonBuildEnv docker container

FROM python:3.10

# The WORKDIR instruction sets the working directory for any RUN, CMD, ENTRYPOINT,
# COPY and ADD instructions that follow it in the Dockerfile.
# If the WORKDIR doesn’t exist, it will be created even if it’s not used
# in any subsequent Dockerfile instruction.
WORKDIR /root/env

# Prevent running interactive config
ENV DEBIAN_FRONTEND noninteractive

COPY requirements.txt ./

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

RUN pip install jupyter

# The VOLUME instruction creates a mount point with the specified name
# and marks it as holding externally mounted volumes from native host or other containers.
VOLUME /root/env

CMD ["/bin/bash"]
