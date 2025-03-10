# Use the official Ubuntu image as the base image
FROM ubuntu:22.04

# Set environment variables to avoid interactive prompts during build
ENV DEBIAN_FRONTEND=noninteractive

# Install necessary packages for Xvfb and pyvirtualdisplay
RUN apt-get update && \
    apt-get install -y \
        python3 \
        python3-pip \
        gnupg \
        ca-certificates \
        libx11-xcb1 \
        libxcomposite1 \
        libxdamage1 \
        libxrandr2 \
        libxss1 \
        libxtst6 \
        libnss3 \
        libatk-bridge2.0-0 \
        libgtk-3-0 \
        x11-apps \
        fonts-liberation \
        libappindicator3-1 \
        libu2f-udev \
        libvulkan1 \
        libdrm2 \
        xdg-utils \
        xvfb \
        libasound2 \
        libcurl4 \
        libgbm1 \
        && rm -rf /var/lib/apt/lists/*

# Download and install specific version of Google Chrome
RUN apt update
# Install tools to manage PPAs
RUN apt install -y software-properties-common
# Add the xtradeb/apps PPA
RUN add-apt-repository -y ppa:xtradeb/apps
# Update the package list again
RUN apt update
# Install Chromium
RUN apt install -y chromium

# Install Python dependencies including pyvirtualdisplay
RUN pip3 install --upgrade pip
RUN pip3 install pyvirtualdisplay

# Set up a working directory
WORKDIR /app

# Copy application files
COPY . .

# Install Python dependencies
RUN pip3 install -r requirements.txt
RUN pip3 install -r server_requirements.txt


# Expose the port for the FastAPI server
EXPOSE 8000

# Copy and set up startup script
COPY docker_startup.sh /
RUN chmod +x /docker_startup.sh

# Set the entrypoint directly to the startup script
ENTRYPOINT ["bash", "-c", ". /docker_startup.sh && exec bash"]

