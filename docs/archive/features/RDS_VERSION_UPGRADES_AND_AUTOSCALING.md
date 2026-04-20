# RDS Major Version Upgrades & Storage Auto-Scaling

## Overview

The RDS stack now supports two important production features:
1. **Major version upgrades** - Upgrade RDS engines to new major versions (e.g., MySQL 8.0 → 8.4)
2. **Storage auto-scaling** - Automatically expand storage when running low on space

## Major Version Upgrades

### Configuration

Add the `allow_major_version_upgrade` flag to your RDS configuration:

```json
{
  "rds": {
    "engine": "mysql",
    "engine_version": "8.4.6",
    "allow_major_version_upgrade": true
  }
}
```

### Single-Step Deployment

You can perform the upgrade in **one deployment**:
1. Set `allow_major_version_upgrade: true`
2. Update `engine_version` to the new version
3. Deploy

CloudFormation applies the flag first, then performs the upgrade atomically.

### Important Pre-Upgrade Steps

⚠️ **Before upgrading:**

1. **Take a manual snapshot**
   ```bash
   aws rds create-db-snapshot \
     --db-instance-identifier your-db-id \
     --db-snapshot-identifier pre-upgrade-snapshot-$(date +%Y%m%d)
   ```

2. **Test in non-production first**
   - Deploy to dev/staging environment
   - Run full application test suite
   - Check for compatibility issues

3. **Review engine-specific changes**
   - MySQL 8.0 → 8.4: [MySQL 8.4 Release Notes](https://dev.mysql.com/doc/relnotes/mysql/8.4/en/)
   - PostgreSQL: Check deprecations and breaking changes
   - Review application compatibility

4. **Plan for downtime**
   - Major upgrades require database restart
   - Downtime varies: 5 minutes to 1+ hours (depends on database size)
   - Schedule during maintenance window

### Supported Upgrade Paths

#### MySQL/MariaDB
- MySQL 5.7 → 8.0 ✅
- MySQL 8.0 → 8.4 ✅
- MariaDB 10.6 → 11.4 ✅

#### PostgreSQL
- PostgreSQL 13 → 14 → 15 → 16 ✅
- Must upgrade one major version at a time

#### SQL Server
- Supports in-place upgrades within edition
- Enterprise/Standard editions only

### Post-Upgrade

After successful upgrade, you can:
1. **Keep the flag** for future upgrades
2. **Remove the flag** in next deployment:
   ```json
   {
     "allow_major_version_upgrade": false
   }
   ```

### Rollback

⚠️ **Major version upgrades cannot be rolled back automatically**

To rollback:
1. Restore from pre-upgrade snapshot
2. This creates a new DB instance
3. Update application connection strings
4. May result in data loss (changes after snapshot)

## Storage Auto-Scaling

### Configuration

Set `max_allocated_storage` to enable automatic storage expansion:

```json
{
  "rds": {
    "allocated_storage": 20,
    "max_allocated_storage": 100
  }
}
```

### How It Works

1. **Initial size**: Database starts with `allocated_storage` (20GB)
2. **Auto-scaling trigger**: When storage usage > 90%
3. **Scaling amount**: Increases by 10% or 10GB (whichever is greater)
4. **Maximum**: Never exceeds `max_allocated_storage` (100GB)
5. **Automatic**: No downtime, happens automatically

### Benefits

✅ **Prevents outages** - No "out of storage" failures  
✅ **Cost-effective** - Only pay for storage actually used  
✅ **Zero-downtime** - Scaling happens automatically  
✅ **Simple management** - Set once, forget about it

### Scaling Behavior

| Current Storage | Usage % | Next Scale Event |
|----------------|---------|------------------|
| 20 GB | 90% | Scale to 30 GB |
| 30 GB | 90% | Scale to 40 GB |
| 40 GB | 90% | Scale to 50 GB |
| ... | ... | ... |
| 100 GB | 90% | Cannot scale (at max) |

### Important Notes

⚠️ **Cannot decrease storage** - Once scaled up, you cannot scale down without restoring from snapshot

⚠️ **Cooldown period** - RDS waits 6 hours between auto-scaling events

⚠️ **Monitoring** - Set CloudWatch alarms for storage usage:
```json
{
  "alarms": {
    "storage_usage_high": {
      "threshold": 80,
      "metric": "FreeStorageSpace"
    }
  }
}
```

### Disable Auto-Scaling

Remove `max_allocated_storage` from config or set to `null`:

```json
{
  "rds": {
    "allocated_storage": 20,
    "max_allocated_storage": null
  }
}
```

## Complete Example

```json
{
  "name": "my-app-prod-rds",
  "module": "rds_stack",
  "enabled": true,
  "rds": {
    "identifier": "my-app-prod-db",
    "engine": "mysql",
    "engine_version": "8.4.6",
    "instance_class": "db.t4g.small",
    
    "// Major Version Upgrade": "",
    "allow_major_version_upgrade": true,
    
    "// Storage Auto-Scaling": "",
    "allocated_storage": 20,
    "max_allocated_storage": 100,
    
    "// Standard Settings": "",
    "multi_az": true,
    "backup_retention": 7,
    "storage_encrypted": true,
    "deletion_protection": true,
    
    "database_name": "myapp",
    "master_username": "admin",
    
    "ssm": {
      "imports": {
        "vpc_id": "/prod/myapp/vpc/id",
        "subnet_ids": "/prod/myapp/vpc/private-subnet-ids",
        "security_group_ids": ["/prod/myapp/sg/rds-id"]
      }
    }
  }
}
```

## CDK Implementation

### Properties Added to RdsConfig

```python
@property
def allow_major_version_upgrade(self) -> bool:
    """Whether to allow major version upgrades"""
    return self.__config.get("allow_major_version_upgrade", False)

@property
def max_allocated_storage(self) -> Optional[int]:
    """Maximum storage for auto-scaling in GB (enables storage auto-scaling if set)"""
    max_storage = self.__config.get("max_allocated_storage")
    return int(max_storage) if max_storage is not None else None
```

### Stack Implementation

```python
db_props = {
    # ... other properties ...
    "allow_major_version_upgrade": self.rds_config.allow_major_version_upgrade,
}

# Add storage auto-scaling if configured
if self.rds_config.max_allocated_storage:
    db_props["max_allocated_storage"] = self.rds_config.max_allocated_storage
    logger.info(
        f"Storage auto-scaling enabled: {self.rds_config.allocated_storage}GB "
        f"-> {self.rds_config.max_allocated_storage}GB"
    )
```

## Monitoring & Alerts

### CloudWatch Metrics to Monitor

1. **FreeStorageSpace** - Alert when < 20%
2. **DatabaseConnections** - Watch for connection issues during upgrade
3. **ReadLatency / WriteLatency** - Monitor performance after upgrade
4. **CPUUtilization** - Check for performance regression

### Recommended Alarms

```json
{
  "alarms": {
    "low_storage": {
      "metric": "FreeStorageSpace",
      "threshold": 10737418240,
      "comparison": "LessThanThreshold",
      "evaluation_periods": 2,
      "description": "Storage < 10GB remaining"
    },
    "high_cpu_post_upgrade": {
      "metric": "CPUUtilization",
      "threshold": 80,
      "comparison": "GreaterThanThreshold",
      "evaluation_periods": 3,
      "description": "CPU usage consistently high after upgrade"
    }
  }
}
```

## Troubleshooting

### Upgrade Fails

**Error**: `The AllowMajorVersionUpgrade flag must be present when upgrading to a new major version`

**Solution**: Ensure `allow_major_version_upgrade: true` is set in the same deployment as the version change.

---

**Error**: `Cannot upgrade from X.Y to X.Z`

**Solution**: Some engines require incremental upgrades (e.g., PostgreSQL 12 → 13 → 14, not 12 → 14 directly).

---

### Storage Won't Scale

**Issue**: Database at 95% but not scaling

**Check**:
1. Verify `max_allocated_storage` is set and > `allocated_storage`
2. Check if within 6-hour cooldown period
3. Ensure not at `max_allocated_storage` limit
4. Review CloudWatch metrics for `FreeableMemory`

---

### Performance Issues After Upgrade

**Symptoms**: Slow queries after major version upgrade

**Actions**:
1. Update table statistics: `ANALYZE TABLE table_name;` (MySQL)
2. Rebuild indexes if necessary
3. Check for new query optimizer behavior
4. Review slow query logs
5. Consider parameter group adjustments

## Best Practices

### Major Version Upgrades

✅ **DO:**
- Test in lower environments first
- Take manual snapshots before upgrading
- Review release notes for breaking changes
- Schedule during maintenance windows
- Monitor closely for 24-48 hours post-upgrade

❌ **DON'T:**
- Skip testing in non-prod
- Upgrade production during business hours
- Upgrade multiple major versions without testing each
- Forget to update application dependencies

### Storage Auto-Scaling

✅ **DO:**
- Set `max_allocated_storage` to 2-5x initial size
- Monitor storage trends
- Set CloudWatch alarms for 80% usage
- Budget for maximum storage costs

❌ **DON'T:**
- Set max too low (frequent hitting of limit)
- Set max too high (unexpected costs)
- Ignore storage growth trends
- Rely solely on auto-scaling without monitoring

## Related Documentation

- [AWS RDS User Guide - Upgrading](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_UpgradeDBInstance.Upgrading.html)
- [RDS Storage Auto-Scaling](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_PIOPS.StorageTypes.html#USER_PIOPS.Autoscaling)
- [MySQL 8.4 Release Notes](https://dev.mysql.com/doc/relnotes/mysql/8.4/en/)
- [PostgreSQL Upgrade Guide](https://www.postgresql.org/docs/current/upgrading.html)

## Version History

- **v0.16.3** - Added `allow_major_version_upgrade` and `max_allocated_storage` support
