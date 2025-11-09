"""
Lambda@Edge Log Retention Manager

A utility for managing log retention policies across Lambda@Edge functions
deployed in multiple AWS regions. Lambda@Edge functions automatically create
log groups in all regions where CloudFront edge locations exist, making
manual retention management challenging.

This module provides functionality to:
- Discover Lambda@Edge log groups across all AWS regions
- Set uniform retention policies
- Report on current storage usage
- Support dry-run mode for safe testing

Usage:
    from edge_log_retention import set_edge_log_retention
    
    # Dry run to see what would be changed
    log_groups = set_edge_log_retention(retention_days=7, dry_run=True)
    
    # Apply retention policies
    set_edge_log_retention(retention_days=7, dry_run=False)
"""

from .edge_log_retention import set_edge_log_retention

__version__ = "1.0.0"
__author__ = "CDK-Factory"
__license__ = "MIT"

__all__ = [
    "set_edge_log_retention"
]
