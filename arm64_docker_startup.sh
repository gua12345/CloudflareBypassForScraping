#!/bin/bash

Xvfb :1 -screen 0 1920x1080x24 > xvfb.log 2>&1 &
export DISPLAY=:1

cd /app
python3 server.py > server.log 2>&1
