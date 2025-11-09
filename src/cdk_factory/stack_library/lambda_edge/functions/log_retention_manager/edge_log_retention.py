#!/usr/bin/env python3
import boto3
from botocore.exceptions import ClientError
import os

profile_name = os.getenv('AWS_PROFILE')
session = boto3.Session(region_name='us-east-1', profile_name=profile_name)
ec2 = session.client('ec2')

def set_edge_log_retention(retention_days=7, dry_run=True):
    """
    Find Lambda@Edge log groups across all regions and set retention policies.
    
    Args:
        retention_days (int): Number of days to retain logs
        dry_run (bool): If True, only show what would be changed
    """
    # Get all AWS regions
    regions = [region['RegionName'] for region in ec2.describe_regions()['Regions']]
    
    edge_log_groups = []
    total_changed = 0
    
    print(f"🔍 Hunting for Lambda@Edge log groups across {len(regions)} regions...")
    print(f"🎯 Target retention: {retention_days} days")
    print(f"🧪 Dry run: {dry_run}")
    print("=" * 60)
    
    for region in regions:
        try:
            logs = session.client('logs', region_name=region)
            
            # Find log groups with us-east-1 prefix (indicating Edge functions)
            paginator = logs.get_paginator('describe_log_groups')
            for page in paginator.paginate():
                for log_group in page.get('logGroups', []):
                    log_group_name = log_group['logGroupName']
                    
                    # Check if it's a Lambda@Edge log group
                    if '/aws/lambda/us-east-1.' in log_group_name:
                        current_retention = log_group.get('retentionInDays')
                        
                        edge_log_groups.append({
                            'region': region,
                            'name': log_group_name,
                            'current_retention': current_retention,
                            'stored_bytes': log_group.get('storedBytes', 0)
                        })
                        
                        # Set retention if needed
                        if current_retention != retention_days:
                            if dry_run:
                                print(f"📍 {region}: Would set {log_group_name} to {retention_days} days (current: {current_retention})")
                            else:
                                try:
                                    logs.put_retention_policy(
                                        logGroupName=log_group_name,
                                        retentionInDays=retention_days
                                    )
                                    print(f"✅ {region}: Set {log_group_name} to {retention_days} days")
                                    total_changed += 1
                                except ClientError as e:
                                    print(f"❌ {region}: Failed to set {log_group_name} - {e}")
                        else:
                            print(f"✓ {region}: {log_group_name} already has {retention_days} days retention")
                            
        except ClientError as e:
            # Skip regions where CloudWatch Logs isn't available
            continue
    
    print("=" * 60)
    print(f"📊 Summary:")
    print(f"   Found {len(edge_log_groups)} Lambda@Edge log groups")
    print(f"   Total storage: {sum(g['stored_bytes'] for g in edge_log_groups) / (1024**3):.2f} GB")
    if not dry_run:
        print(f"   Changed {total_changed} log groups")
    
    return edge_log_groups

if __name__ == "__main__":
    # Dry run first to see what would be changed
    edge_logs = set_edge_log_retention(retention_days=7, dry_run=True)
    
    # Uncomment the line below to actually make changes
    # set_edge_log_retention(retention_days=7, dry_run=False)