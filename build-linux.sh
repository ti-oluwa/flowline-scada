#!/usr/bin/env bash

NAME="FlowlineSCADA-Linux.exe"
if [ -n "$1" ]; then
  NAME="$1"
fi
nicegui-pack --onefile --windowed --icon "assets/pipeline.ico" --name "$NAME" main.py
