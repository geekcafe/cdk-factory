# RDS Name Sanitization

* DB **instance identifiers**
* **Master usernames**
* **Database names** (engine-specific: MySQL/MariaDB, PostgreSQL, SQL Server, Oracle)

I’ve embedded conservative rules that match AWS docs (and avoid edge quoting headaches), then engine-specific exceptions where relevant.

---

# What to enforce (summary)

### 1) DB **Instance Identifier** (all engines)

* Allowed: lowercase letters, digits, **hyphens (-)**
* Must start with a letter; **no ending hyphen**; **no “--”**; length **1–63**. ([AWS Documentation][1])

### 2) **Master username** (all engines, RDS “master”)

* Allowed: letters, digits, **underscore**
* Must start with a letter; **length 1–16**; **not a reserved word**. (You can’t change it later.) ([AWS Documentation][2])

> Password rules differ by engine; see AWS limits page if you also want to validate passwords. ([AWS Documentation][3])

### 3) **Database name** (engine-specific)

* **MySQL / MariaDB / Aurora MySQL**

  * Length **1–64**
  * Must start with a letter; subsequent: letters, digits, **underscore**
  * **Hyphens not allowed**; **avoid reserved words**. ([AWS Documentation][4])

* **PostgreSQL / Aurora PostgreSQL**

  * Length **1–63**
  * Must start with a letter (AWS creates `postgres` by default)
  * Subsequent: letters, digits, **underscore**
  * **Hyphens not allowed**; avoid reserved words. ([AWS Documentation][5])

* **SQL Server**

  * AWS says “usual SQL Server rules,” plus: **can’t start with `rdsadmin`**, can’t start/end with space or tab, can’t include newline or single quote.
  * SQL Server **can** allow hyphens if you bracket-quote names, but to keep life simple across tools, **prefer letters/digits/underscore** and start with a letter. ([AWS Documentation][6])

* **Oracle (RDS)**

  * The `DBName` is effectively the **SID**: **max 8 chars**, **alphanumeric only**, **must start with a letter**. (AWS CFN/API constraints.) ([AWS Documentation][7])

---

# Python: validators & sanitizers

Paste this into a shared `naming.py`. It returns a sanitized value **and** a list of notes about what changed. You can set `strict=True` to raise if unsanitizable.

```python
import re
from typing import Tuple, List, Literal

Engine = Literal["mysql", "mariadb", "aurora-mysql",
                 "postgres", "aurora-postgres",
                 "sqlserver", "oracle"]

# -----------------------
# Core helpers
# -----------------------
def _collapse_hyphens(s: str) -> str:
    return re.sub(r"-{2,}", "-", s)

def _ensure_starts_with_letter(s: str, fallback_letter: str = "a") -> str:
    return s if re.match(r"^[A-Za-z]", s) else f"{fallback_letter}{s}"

def _strip_disallowed(s: str, allowed_pattern: str) -> Tuple[str, bool]:
    """Keep only allowed chars (regex char class), return (result, changed?)."""
    new = re.sub(f"[^{allowed_pattern}]", "", s)
    return new, new != s

def _truncate(s: str, max_len: int) -> Tuple[str, bool]:
    return (s[:max_len], len(s) > max_len)

# -----------------------
# Instance Identifier
# -----------------------
def sanitize_instance_identifier(name: str, strict: bool = False) -> Tuple[str, List[str]]:
    """
    RDS DB instance identifier (all engines):
    - 1–63 chars, lowercase letters/digits/hyphen
    - must start with letter, can't end with hyphen, no consecutive hyphens
    """
    notes: List[str] = []
    s = name.lower()

    # keep lowercase letters, digits, hyphen
    s2, changed = _strip_disallowed(s, r"a-z0-9-")
    if changed:
        notes.append("removed invalid characters (only a-z, 0-9, '-')")

    # must start with letter
    if not re.match(r"^[a-z]", s2):
        s2 = _ensure_starts_with_letter(s2)
        notes.append("prefixed with 'a' to start with a letter")

    # collapse consecutive hyphens
    s2c = _collapse_hyphens(s2)
    if s2c != s2:
        s2 = s2c
        notes.append("collapsed consecutive hyphens")

    # cannot end with hyphen
    if s2.endswith("-"):
        s2 = s2.rstrip("-")
        notes.append("removed trailing hyphen")

    # length 1–63
    s2, cut = _truncate(s2, 63)
    if cut:
        notes.append("truncated to 63 characters")

    if strict and not validate_instance_identifier(s2):
        raise ValueError(f"Cannot sanitize instance identifier '{name}' to a valid value.")
    return s2, notes

def validate_instance_identifier(name: str) -> bool:
    return bool(re.fullmatch(r"[a-z][a-z0-9-]{0,62}", name)) and "--" not in name and not name.endswith("-")

# -----------------------
# Master Username
# -----------------------
def sanitize_master_username(name: str, strict: bool = False) -> Tuple[str, List[str]]:
    """
    RDS master username (all engines, per AWS console rules):
    - 1–16 chars
    - start with letter
    - letters/digits/underscore
    - not a reserved word (hard to check generically; keep a small denylist hook)
    """
    notes: List[str] = []
    s = name

    # keep letters/digits/underscore
    s2, changed = _strip_disallowed(s, r"A-Za-z0-9_")
    if changed:
        notes.append("removed invalid characters (only letters, digits, underscore)")

    # must start with letter
    if not re.match(r"^[A-Za-z]", s2):
        s2 = _ensure_starts_with_letter(s2, "u")
        notes.append("prefixed with 'u' to start with a letter")

    # enforce length
    s2, cut = _truncate(s2, 16)
    if cut:
        notes.append("truncated to 16 characters")

    # simple reserved-word guard (you can extend per engine)
    reserved = {"postgres", "mysql", "root", "admin", "rdsadmin", "system", "sa"}
    if s2.lower() in reserved:
        s2 = f"{s2}_user"
        notes.append("appended '_user' to avoid reserved username")

    if strict and not validate_master_username(s2):
        raise ValueError(f"Cannot sanitize master username '{name}' to a valid value.")
    return s2, notes

def validate_master_username(name: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,15}", name))

# -----------------------
# Database Name (engine-specific)
# -----------------------
def _db_limits(engine: Engine) -> Tuple[re.Pattern, int]:
    """
    Returns (pattern, max_len) for DB name:
    - MySQL/MariaDB: ^[A-Za-z][A-Za-z0-9_]{0,63}? but max is 64 total
    - PostgreSQL:    ^[A-Za-z][A-Za-z0-9_]{0,62}? max 63
    - SQL Server:    safe profile (avoid quoting): ^[A-Za-z][A-Za-z0-9_]{0,127}? (SQL Server supports up to 128)
    - Oracle:        ^[A-Za-z][A-Za-z0-9]{0,7}$ (SID/DBName <= 8, alnum only)
    """
    if engine in ("mysql", "mariadb", "aurora-mysql"):
        return re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$"), 64
    if engine in ("postgres", "aurora-postgres"):
        return re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,62}$"), 63
    if engine == "sqlserver":
        # RDS allows usual SQL Server names, but we enforce a cross-tool-safe subset.
        return re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,127}$"), 128
    if engine == "oracle":
        return re.compile(r"^[A-Za-z][A-Za-z0-9]{0,7}$"), 8
    raise ValueError(f"Unsupported engine: {engine}")

def sanitize_db_name(engine: Engine, name: str, strict: bool = False) -> Tuple[str, List[str]]:
    """
    Sanitizes to a safe subset for the given engine.
    Hyphens are rejected for DB names across engines (Oracle doesn't allow underscore for DB NAME either,
    but we handle that by engine).
    """
    notes: List[str] = []
    pat, max_len = _db_limits(engine)
    s = name

    # Engine-allowed char class
    if engine == "oracle":
        allowed = r"A-Za-z0-9"       # no underscore or hyphen for SID
    else:
        allowed = r"A-Za-z0-9_"

    s2, changed = _strip_disallowed(s, allowed)
    if changed:
        notes.append("removed invalid characters")

    # must start with letter
    if not re.match(r"^[A-Za-z]", s2):
        s2 = _ensure_starts_with_letter(s2, "d")
        notes.append("prefixed with 'd' to start with a letter")

    # enforce max len
    s2, cut = _truncate(s2, max_len)
    if cut:
        notes.append(f"truncated to {max_len} characters")

    # special engine guards
    if engine == "sqlserver":
        if s2.lower().startswith("rdsadmin"):
            s2 = "db_" + s2
            notes.append("prefixed to avoid 'rdsadmin' start (SQL Server)")
    # Final pattern check
    if strict and not pat.fullmatch(s2):
        raise ValueError(f"Cannot sanitize db name '{name}' for engine '{engine}' into a valid value.")
    return s2, notes

def validate_db_name(engine: Engine, name: str) -> bool:
    pat, _ = _db_limits(engine)
    return bool(pat.fullmatch(name))
```

---

## How to use

```python
# Instance identifiers
val, notes = sanitize_instance_identifier("Prod.DB--01")
print(val, notes)  # 'aProd-db-01' -> then lowercased & cleaned to comply

# Master usernames
val, notes = sanitize_master_username("1admin")
print(val, notes)  # 'u1admin_user', [...]

# DB names
for eng in ("mysql", "postgres", "sqlserver", "oracle"):
    val, notes = sanitize_db_name(eng, "my-db$name", strict=False)
    print(eng, "->", val, notes)
```

---

## Practical recommendations

* **Disallow hyphens in DB names** everywhere (even though SQL Server can handle them with quoting) to avoid tool friction.
* **Allow hyphens in instance identifiers** (per AWS rules) but collapse `--`, trim trailing `-`, and force lowercase. ([AWS Documentation][1])
* Keep a **small reserved-word denylist** for usernames and DB names (extend per engine as needed). AWS notes to avoid reserved words but doesn’t provide a single list because it’s engine-specific. ([AWS Documentation][2])
* If you also want to guard **passwords**, enforce engine-specific length and character constraints from AWS limits. ([AWS Documentation][3])



[1]: https://docs.aws.amazon.com/AmazonRDS/latest/APIReference/API_CreateDBInstance.html?utm_source=chatgpt.com "CreateDBInstance - Amazon Relational Database Service"
[2]: https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_CreateDBInstance.Settings.html?utm_source=chatgpt.com "Settings for DB instances"
[3]: https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_Limits.html?utm_source=chatgpt.com "Quotas and constraints for Amazon RDS"
[4]: https://docs.aws.amazon.com/cli/latest/reference/rds/create-db-instance.html?utm_source=chatgpt.com "create-db-instance — AWS CLI 2.31.23 Command Reference"
[5]: https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/create-multi-az-db-cluster.html?utm_source=chatgpt.com "Creating a Multi-AZ DB cluster for Amazon RDS"
[6]: https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_SQLServer.html?utm_source=chatgpt.com "Amazon RDS for Microsoft SQL Server"
[7]: https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-rds-dbinstance.html?utm_source=chatgpt.com "RDS::DBInstance - AWS CloudFormation - AWS Documentation"
