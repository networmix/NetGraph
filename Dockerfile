FROM python:3.10

# Add Tini
ENV TINI_VERSION v0.19.0
ADD https://github.com/krallin/tini/releases/download/${TINI_VERSION}/tini /tini
RUN chmod +x /tini

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
RUN pip install networkx
RUN pip install pandas
RUN pip install seaborn
RUN pip install basemap-data-hires
RUN pip install basemap

ENTRYPOINT ["/tini", "-g", "--"]