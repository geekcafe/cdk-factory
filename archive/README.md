# Archive Directory

This directory contains historical scripts and files that were used during development but are no longer needed for active operations.

## Contents

### migrate_to_enhanced_ssm.py
**Date**: September 2025  
**Purpose**: Migration script used to upgrade the AWS CDK Factory framework from the original SSM parameter pattern to the enhanced SSM parameter pattern.

**What it did**:
- Updated 10+ configuration classes to inherit from `EnhancedBaseConfig`
- Updated 11+ stack implementations to use `EnhancedSsmParameterMixin`
- Added imports for enhanced base configuration
- Preserved backward compatibility with existing configurations
- Created backup files during migration (later removed after successful testing)

**Migration Results**:
- All 105 unit tests passing
- Enhanced SSM pattern with auto-discovery functionality
- Environment-aware parameter paths
- Flexible template patterns for custom SSM parameter naming
- Full backward compatibility maintained

**Status**: ✅ Migration completed successfully - script archived for reference

This script serves as documentation of the migration process and could be referenced for future similar migrations or rollback procedures if ever needed.
