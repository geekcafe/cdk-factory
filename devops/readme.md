# DevOps

## building
```sh

```

## deploying

```sh
twine upload dist/*

```

## uploading and testing with a "test"

```sh

twine upload --repository-url https://test.pypi.org/legacy/ dist/*

pip install --index-url https://test.pypi.org/simple/ boto3-assist

```