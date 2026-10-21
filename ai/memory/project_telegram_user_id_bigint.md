---
name: telegram-user-id-bigint
description: "Telegram user/chat ids exceed 32 bits: store them as BIGINT / 64-bit integers, in db columns and in variable declarations of fixed-width-integer languages alike"
metadata:
  type: project
---

Store a Telegram `user_id` (and chat ids) in a 64-bit signed integer: `BIGINT` in SQL, `sa.BigInteger()` in SQLAlchemy/alembic, `i64`/`int64`/`long` in variable, field and struct declarations.
The rule covers any limited-size number storage, not only db columns, e.g. `int`/`i32` in Java, C, Rust, Go or Kotlin; 32-bit types break silently or overflow.

Reference: @ai/references/https/core.telegram.org/bots/api/types/user.md says the `id` "may have more than 32 significant bits ... it has at most 52 significant bits, so a 64-bit integer or double-precision float type are safe for storing this identifier."

**Why:** ids are above 2^31 for newer accounts, so `INTEGER` columns overflow and fixed-width variables silently truncate.

**How to apply:** when adding a table, migration, model or typed field that holds a Telegram user or chat id, pick the 64-bit type from the start; when reviewing existing code, flag any 32-bit id storage.
