# RDS Name Sanitization Implementation Summary

**Version**: 0.15.12+  
**Status**: ✅ Implemented  
**Based on**: AWS RDS Naming Requirements Documentation

## Overview

Implemented comprehensive, engine-aware name sanitization for RDS resources following AWS documentation rules. All sanitization happens automatically with detailed logging.

---

## Implemented Features

### 1. **DB Instance Identifier Sanitization**

All RDS engines follow the same rules for instance identifiers:

- ✅ **Length**: 1-63 characters
- ✅ **Allowed characters**: lowercase letters, digits, hyphens
- ✅ **Must start with**: letter
- ✅ **Cannot end with**: hyphen
- ✅ **No consecutive hyphens**: `--` collapsed to `-`
- ✅ **Auto-lowercase**: converts to lowercase

**Example transformations**:
```
"Prod.DB--01" → "proddb-01"
"123-db" → "db123-db"
"my_database" → "mydatabase"
```

---

### 2. **Master Username Sanitization**

Universal rules across all engines:

- ✅ **Length**: 1-16 characters
- ✅ **Allowed characters**: letters, digits, underscores
- ✅ **Must start with**: letter
- ✅ **Reserved word protection**: avoids `postgres`, `mysql`, `root`, `admin`, `rdsadmin`, `system`, `sa`, `user`
- ✅ **Auto-fix hyphens**: converts `-` to `_`

**Example transformations**:
```
"acme-inc-prod-admin" → "acme_inc_prod_"
"1admin" → "user1admin"
"postgres" → "postgres_usr"
```

---

### 3. **Database Name Sanitization (Engine-Specific)**

#### **MySQL / MariaDB / Aurora MySQL**
- ✅ **Length**: 1-64 characters
- ✅ **Allowed characters**: letters, digits, underscores
- ✅ **Must start with**: letter
- ✅ **Auto-fix hyphens**: converts `-` to `_`

```
"acme-inc-prod" → "acme_inc_prod"
```

#### **PostgreSQL / Aurora PostgreSQL**
- ✅ **Length**: 1-63 characters
- ✅ **Allowed characters**: letters, digits, underscores
- ✅ **Must start with**: letter
- ✅ **Auto-fix hyphens**: converts `-` to `_`

```
"my-app-db" → "my_app_db"
```

#### **SQL Server**
- ✅ **Length**: 1-128 characters
- ✅ **Allowed characters**: letters, digits, underscores
- ✅ **Must start with**: letter
- ✅ **Special rule**: Cannot start with `rdsadmin` (auto-prefixed if detected)
- ✅ **Auto-fix hyphens**: converts `-` to `_`

```
"my-app-db" → "my_app_db"
"rdsadmin_db" → "db_rdsadmin_db"
```

#### **Oracle**
- ✅ **Length**: 1-8 characters (SID constraint)
- ✅ **Allowed characters**: letters, digits only (NO underscores)
- ✅ **Must start with**: letter
- ✅ **Hyphens removed**: stripped entirely

```
"my-db" → "mydb"
"prod_app" → "prodapp"
```

---

## Implementation Details

### Code Location
- **File**: `cdk-factory/src/cdk_factory/configurations/resources/rds.py`
- **Class**: `RdsConfig`

### Key Methods

1. **`_sanitize_instance_identifier_impl()`**
   - Handles DB instance identifier sanitization
   - Returns tuple of (sanitized_value, notes)

2. **`_sanitize_db_name_impl(engine, name)`**
   - Engine-aware database name sanitization
   - Supports: mysql, mariadb, postgres, sqlserver, oracle, aurora variants

3. **`_sanitize_master_username_impl()`**
   - Universal username sanitization
   - Checks reserved words and enforces 16-char limit

### Logging

All sanitization operations are logged with details:

```python
logger.info(f"Sanitized database name from 'acme-inc-prod' to 'acme_inc_prod': replaced hyphens with underscores")
```

### Error Handling

Clear error messages when sanitization is impossible:

```python
ValueError: "Database name 'my-db' (sanitized to '123db') cannot start with a number. Please ensure the database name begins with a letter."
```

---

## Testing Examples

### Example 1: MySQL Database
```json
{
  "engine": "mysql",
  "database_name": "acme-inc-prod",
  "master_username": "acme-inc-prod-admin"
}
```

**Result**:
- Database name: `acme_inc_prod`
- Username: `acme_inc_prod_`

### Example 2: Oracle Database
```json
{
  "engine": "oracle",
  "database_name": "production-app",
  "master_username": "app-admin"
}
```

**Result**:
- Database name: `producti` (truncated to 8 chars, hyphens removed)
- Username: `app_admin`

### Example 3: PostgreSQL Database
```json
{
  "engine": "postgres",
  "database_name": "My-App-DB-2024",
  "master_username": "postgres"
}
```

**Result**:
- Database name: `My_App_DB_2024`
- Username: `postgres_usr` (reserved word avoided)

---

## AWS Documentation References

1. **DB Instance Identifiers**: [CreateDBInstance API](https://docs.aws.amazon.com/AmazonRDS/latest/APIReference/API_CreateDBInstance.html)
2. **Master Username**: [DB Instance Settings](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_CreateDBInstance.Settings.html)
3. **Database Names**: Engine-specific documentation for MySQL, PostgreSQL, SQL Server, Oracle

---

## Breaking Changes

**None** - This is fully backward compatible. Existing configurations will be automatically sanitized with informative logging.

---

## Future Enhancements

- [ ] Add validation for reserved words per engine (currently uses common subset)
- [ ] Support for engine-specific username length limits (some engines allow more than 16)
- [ ] Optional strict mode via configuration flag
- [ ] Pre-deployment validation report

---

## Configuration Example

```json
{
  "name": "{{WORKLOAD_NAME}}-{{ENVIRONMENT}}-rds",
  "module": "rds_stack",
  "enabled": true,
  "rds": {
    "identifier": "{{WORKLOAD_NAME}}-{{ENVIRONMENT}}-db",
    "engine": "mysql",
    "engine_version": "8.0.42",
    "database_name": "{{WORKLOAD_NAME}}-{{ENVIRONMENT}}",
    "master_username": "{{WORKLOAD_NAME}}-admin"
  }
}
```

With `WORKLOAD_NAME=acme-inc` and `ENVIRONMENT=prod`:
- **Instance ID**: `acme-inc-prod-db` (hyphens OK for identifiers)
- **Database name**: `acme_inc_prod` (hyphens → underscores)
- **Username**: `acme_inc_admin` (hyphens → underscores)

All sanitization happens automatically during stack synthesis.
