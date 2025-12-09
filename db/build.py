import duckdb
import pathlib

BASE = pathlib.Path(__file__).resolve().parent

db_path = BASE / 'course_planner.duckdb'

if db_path.exists():
    db_path.unlink()

schema_sql = (BASE / 'schema.sql').read_text(encoding='utf-8')
seeds_sql  = (BASE / 'data.sql').read_text(encoding='utf-8')
verify_sql = (BASE / 'verify.sql').read_text(encoding='utf-8')

con = duckdb.connect(str(db_path))
con.execute(schema_sql)
con.execute(seeds_sql)

print('Tables:')
for row in con.execute('SHOW TABLES').fetchall():
    print(row)

print('\nVerify results:')
for row in con.execute(verify_sql).fetchall():
    print(row)

con.close()
print('\nCreated', db_path)


