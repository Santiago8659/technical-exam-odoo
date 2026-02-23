# Odoo 14 - Technical Exam Environment
FROM --platform=linux/amd64 odoo:14.0

USER root

# Update repositories to historical Debian archive
RUN sed -i 's/deb.debian.org/archive.debian.org/g' /etc/apt/sources.list && \
    sed -i 's|security.debian.org|archive.debian.org/debian-security|g' /etc/apt/sources.list && \
    sed -i '/stretch-updates/d' /etc/apt/sources.list

# Install dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        curl \
        python3.7 \
        python3.7-dev \
        libldap2-dev \
        libsasl2-dev \
        libssl-dev \
        build-essential

# Configure Python 3.7 as default
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.7 1 && \
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.7 1

# Install pip for Python 3.7
RUN curl -sS https://bootstrap.pypa.io/pip/3.7/get-pip.py | python3.7

# Clean temp files
RUN apt-get clean && rm -rf /var/lib/apt/lists/*

# Configure locale
RUN apt-get update && \
    apt-get install -y locales && \
    sed -i -e 's/# es_ES.UTF-8 UTF-8/es_ES.UTF-8 UTF-8/' /etc/locale.gen && \
    dpkg-reconfigure --frontend=noninteractive locales

ENV LANG es_ES.UTF-8
ENV LC_ALL es_ES.UTF-8

# Install Python requirements
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt
RUN rm -rf /var/lib/apt/lists/* /tmp/requirements.txt

USER odoo
