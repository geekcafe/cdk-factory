# Define Python version for flexibility
ARG PYTHON_VERSION=3.12
FROM --platform=linux/amd64 public.ecr.aws/lambda/python:${PYTHON_VERSION}

# Set environment variable for reuse and clarity
ENV PYTHON_BIN=/var/lang/bin/python${PYTHON_VERSION}

# Show important locations
RUN echo "Lambda task root: $LAMBDA_TASK_ROOT" && \
    echo "PYTHONPATH: $PYTHONPATH" && \
    echo "Working Directory: $(pwd)"

# Run system upgrade, prefer dnf (yum is deprecated)
RUN (command -v dnf && dnf upgrade -y) || echo "No compatible package manager found"

# Upgrade pip
RUN $PYTHON_BIN -m pip install --upgrade pip

# Set a custom PYTHONPATH if needed
# ENV PYTHONPATH="${PYTHONPATH}:/your/custom/path"

# Copy source files into the container
COPY ./src/lambda_handlers/summary_report/app.py "$LAMBDA_TASK_ROOT/"
COPY ./src/lambda_handlers/summary_report/requirements.txt "$LAMBDA_TASK_ROOT/"
COPY ./src/lambda_handlers/summary_report/mock-data/ "$LAMBDA_TASK_ROOT/mock-data/"

# Install Python dependencies into Lambda task root
RUN pip3 install -r "$LAMBDA_TASK_ROOT/requirements.txt" --target "$LAMBDA_TASK_ROOT"

# List contents for verification
RUN echo "Listing contents of LAMBDA_TASK_ROOT:" && ls -al "$LAMBDA_TASK_ROOT"

# Define Lambda handler
CMD [ "app.lambda_handler" ]
