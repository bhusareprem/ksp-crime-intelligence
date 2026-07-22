import sqlite3, duckdb

conn = sqlite3.connect("data/ksp_crime.db")
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in c.fetchall()]
print("ksp_crime tables:", tables)
for t in tables:
    c.execute(f"PRAGMA table_info({t})")
    cols = [r[1] for r in c.fetchall()]
    print(f"  {t}: {cols}")
conn.close()

print()
conn2 = duckdb.connect("data/criminal.db", read_only=True)
tables2 = [r[0] for r in conn2.execute("SHOW TABLES").fetchall()]
print("criminal tables:", tables2)
for t in tables2:
    cols = [r[0] for r in conn2.execute(f"DESCRIBE {t}").fetchall()]
    print(f"  {t}: {cols}")
conn2.close()

print()
conn3 = duckdb.connect("data/cases.db", read_only=True)
tables3 = [r[0] for r in conn3.execute("SHOW TABLES").fetchall()]
print("cases tables:", tables3)
for t in tables3:
    cols = [r[0] for r in conn3.execute(f"DESCRIBE {t}").fetchall()]
    print(f"  {t}: {cols}")
conn3.close()
