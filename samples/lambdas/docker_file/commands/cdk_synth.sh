echo building for branch: ${GIT_BRANCH_NAME}
python --version
            
if [ -n "$PYTHON_312_VERSION" ]; then echo "Switching to Python version ${PYTHON_312_VERSION} - using environment var for version"; pyenv global "${PYTHON_312_VERSION}"; fi


python --version
echo printing environment vars
env
echo Extracting stack name from CODEBUILD_INITIATOR
echo $CODEBUILD_INITIATOR
# Extract the second part of CODEBUILD_INITIATOR (stack name)
STACK_NAME=$(echo $CODEBUILD_INITIATOR | cut -d'/' -f2)
echo Stack name is $STACK_NAME
echo $(pwd) 
export WORKING_DIRECTORY=$(pwd)
echo $WORKING_DIRECTORY
# install the main cdk-factory (we'll remove this later - once we publish the package)
pip install -r ./requirements.txt

# run the cdk synth
npx cdk synth {verbose} $STACK_NAME
echo CDK Synth Complete
