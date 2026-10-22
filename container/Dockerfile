# syntax=docker/dockerfile:1@sha256:4edf897a3ffa55b89f906fc8cc78afdb3f1834cc9c7083565e611a8a7d5fe99e
FROM ubuntu:24.04@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac
ENV DEBIAN_FRONTEND=noninteractive
RUN --mount=type=secret,id=trust,mode=0444 \
    sed -i 's,http://,https://,g' /etc/apt/sources.list.d/ubuntu.sources && \
    apt-get -o Acquire::https::CaInfo=/run/secrets/trust -o APT::Update::Error-Mode=any update && \
    apt-get -o Acquire::https::CaInfo=/run/secrets/trust install -y --no-install-recommends \
      build-essential chrpath cpio diffstat file gawk git iputils-ping libacl1 \
      locales python3 python3-pexpect python3-git python3-jinja2 socat texinfo \
      unzip wget curl xz-utils zstd lz4 bzip2 ca-certificates binutils bc bison \
      flex libssl-dev rsync && \
    locale-gen en_US.UTF-8 && \
    rm -rf /var/lib/apt/lists/*
ENV LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8
USER ubuntu
WORKDIR /workspace/rpi4-yocto
