FROM jellyfin/jellyfin:latest

# Install comskip build dependencies + comchap/comcut dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    libargtable2-dev \
    autoconf \
    automake \
    libtool \
    pkg-config \
    ffmpeg \
    libavformat-dev \
    libavcodec-dev \
    libswscale-dev \
    libavutil-dev \
    mkvtoolnix \
    && rm -rf /var/lib/apt/lists/*

# Build comskip from source (latest version)
RUN git clone https://github.com/erikkaashoek/Comskip.git /tmp/comskip \
    && cd /tmp/comskip \
    && ./autogen.sh \
    && ./configure \
    && make \
    && make install \
    && rm -rf /tmp/comskip

# Install comchap (comchap + comcut scripts)
RUN git clone https://github.com/BrettSheleski/comchap.git /tmp/comchap \
    && install -m 755 /tmp/comchap/comchap /usr/local/bin/comchap \
    && install -m 755 /tmp/comchap/comcut /usr/local/bin/comcut \
    && rm -rf /tmp/comchap

# Copy comskip config and post-processing script
COPY comskip.ini /etc/comskip/comskip.ini
COPY postprocess.sh /usr/local/bin/postprocess.sh
RUN chmod +x /usr/local/bin/postprocess.sh
