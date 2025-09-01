def lambda_handler(event, context):
    """Test lambda handler for unit testing."""
    return {
        'statusCode': 200,
        'body': 'Hello from test lambda!'
    }
