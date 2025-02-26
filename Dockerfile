FROM stateoftheartio/qt6:6.6-gcc-aqt

USER root
WORKDIR /app

# Install pip and additional system dependencies, including libxcb-cursor0
RUN apt-get update && apt-get install -y python3-pip

RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libgl1-mesa-dri \
    libegl1-mesa \
    libglu1-mesa \
    libxkbcommon0 \
    libxcb1 \
    libxcb-util1 \
    libxcb-cursor0 \
    libx11-xcb1 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-render-util0 \
    libxcb-shape0 \
    libxcb-xinerama0 \
    libxcb-xfixes0 \
    libxcb-glx0 \
    libxcb-sync1 \
    libxcb-dri3-0 \
    libxcb-dri2-0 \
    libxcomposite1 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libsm6 \
    libice6 \
    libfontconfig1 \
    libdbus-1-3 \
    libxext6 \
    fonts-dejavu-core \
    libfreetype6 \
    libfreetype6-dev \
    libpng-dev \
    libharfbuzz0b \
    libicu-dev \
    libglib2.0-0 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libatspi2.0-0 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip, setuptools, and wheel
RUN python3 -m pip install --upgrade pip setuptools wheel

# Install Python dependencies
COPY requirements.txt .
RUN python3 -m pip install --no-cache-dir -r requirements.txt

# Copy the project code
COPY . /app

ENV QT_X11_NO_MITSHM=1

ENV POSTGRES_HOST=db
ENV POSTGRES_PORT=5432
ENV POSTGRES_DB=crypto_data
ENV POSTGRES_USER=postgres
ENV POSTGRES_PASSWORD=7aGpc4Uj

CMD ["python3", "-m", "app.data_handler"]
