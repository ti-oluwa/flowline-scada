#!/bin/bash

NAME="FlowlineSCADA-Windows.exe"
if [ -f "$NAME" ]; then
    rm "$NAME"
fi
nicegui-pack --onefile --windowed --icon "assets/pipeline.ico" --name "$NAME" main.py --native
