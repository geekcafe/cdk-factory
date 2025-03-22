#!/bin/bash

python --version
python -m venv .unittest
source ./.unittest/bin/activate
which python


pip install --upgrade pip
pip install -r ./requirements.txt
pip install -r ./requirements-dev.txt


echo "running unit test"
python -m unittest discover -s tests -p "*_test.py"

if [ $? -eq 0 ]; then
    echo "Tests passed successfully"
else
    echo "No tests found or tests failed"
    exit 1
fi