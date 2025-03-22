# pip install -r ./requirements.txt --upgrade
# pip install -r ./requirements-dev.txt --upgrade
# mypy --install-types --non-interactive 
mypy --check-untyped-defs ./src 