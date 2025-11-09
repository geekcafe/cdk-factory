from edge_log_retention import set_edge_log_retention
from aws_lambda_powertools import Logger
import json

logger = Logger(service="LambdaEdgeLogRetentionManager")

def lambda_handler(event, context):
    """
    Lambda handler for EventBridge scheduled log retention management
    """
    # Extract parameters from EventBridge detail section

    try:
        logger.info(f"Event: {event}")
        
        detail = event.get('detail', {})
        days = int(detail.get('days', 7))
        dry_run = str(detail.get('dry_run', True)).lower() == 'true'

        set_edge_log_retention(retention_days=days, dry_run=dry_run)
    except Exception as e:

        logger.error(f"Error: {e}, event: {event}, detail: {detail}")


    return {
        'statusCode': 200,
        'body': json.dumps('Log retention management completed successfully')
    }
        
