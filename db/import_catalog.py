# import catalog CSVs into database
import csv
from pathlib import Path
import duckdb
from datetime import datetime

BASE = Path(__file__).resolve().parent

DAY_MAP = {
    'M': 1,
    'T': 2,
    'W': 3,
    'R': 4,
    'F': 5,
    'S': 6,
    'U': 7,
}
DB = str((BASE.parent/'db' / 'course_planner.duckdb').resolve())
CAT = BASE / 'catalog'
con = duckdb.connect(DB)

def fetch_dict(sql, params=()):
    cur = con.execute(sql, params)
    cols = [d[0].lower() for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]

def exec_sql(sql, params=()):
    con.execute(sql, params)


def next_id(table, col):
    row = fetch_dict(f"SELECT COALESCE(MAX({col}),0)+1 AS nid FROM {table}")[0]
    return int(row['nid'])

def ensure_catalog_year(start_year, end_year):
    row = fetch_dict(
        "SELECT cy_id FROM catalog_year WHERE start_year = ? AND end_year = ?",
        (start_year, end_year)
    )
    if row:
        return int(row[0]['cy_id'])
    cy_id = next_id('catalog_year','cy_id')
    exec_sql(
        "INSERT INTO catalog_year (cy_id, start_year, end_year) VALUES (?,?,?)",
        (cy_id, start_year, end_year)
    )
    return cy_id

def upsert_program(name, program_type, cy_id):
    row = fetch_dict(
        "SELECT prog_id FROM program WHERE name = ? AND program_type = ? AND catalog_year_id = ?",
        (name, program_type, cy_id)
    )
    if row:
        return int(row[0]['prog_id'])
    prog_id = next_id('program','prog_id')
    exec_sql(
        "INSERT INTO program (prog_id, catalog_year_id, name, program_type) VALUES (?,?,?,?)",
        (prog_id, cy_id, name, program_type)
    )
    return prog_id

def upsert_course(subject, cata_num, title, credits_str):
    row = fetch_dict(
        "SELECT course_id FROM course WHERE subject = ? AND cata_num = ?",
        (subject, cata_num)
    )
    if row:
        course_id = int(row[0]['course_id'])
        # optional title sync
        exec_sql("UPDATE course SET title = ?, credits = ? WHERE course_id = ?",
                 (title, str(credits_str), course_id))
        return course_id
    course_id = next_id('course','course_id')
    exec_sql(
        "INSERT INTO course (course_id, title, subject, cata_num, credits) VALUES (?,?,?,?,?)",
        (course_id, title, subject, cata_num, str(credits_str))
    )
    return course_id

def ensure_major_course(prog_id, course_id, eligible):
    row = fetch_dict(
        "SELECT 1 FROM major_courses WHERE major_id = ? AND course_id = ?",
        (prog_id, course_id)
    )
    if row:
        return
    mc_id = next_id('major_courses','major_course_id')
    exec_sql(
        "INSERT INTO major_courses (major_course_id, major_id, course_id, eligible_course) VALUES (?,?,?,?)",
        (mc_id, prog_id, course_id, bool(str(eligible).upper() == 'TRUE'))
    )

def ensure_prereq(course_id, prereq_course_id, min_grade):
    row = fetch_dict(
        "SELECT 1 FROM course_prereq WHERE course_id = ? AND prereq_course_id = ?",
        (course_id, prereq_course_id)
    )
    if row:
        return
    cp_id = next_id('course_prereq','cp_id')
    exec_sql(
        "INSERT INTO course_prereq (cp_id, prereq_course_id, course_id, min_grade) VALUES (?,?,?,?)",
        (cp_id, prereq_course_id, course_id, int(min_grade) if str(min_grade).isdigit() else None)
    )

def load_courses():
    path = CAT / 'courses.csv'
    if not path.exists():
        print('skip courses.csv (not found)')
        return {}
    print('loading courses.csv')
    map_key_to_id = {}
    with path.open(newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            subj = row['subject'].strip()
            num = row['cata_num'].strip()
            title = row['title'].strip()
            credits = row['credits'].strip()
            cid = upsert_course(subj, num, title, credits)
            map_key_to_id[(subj, num)] = cid
    return map_key_to_id

def load_programs():
    path = CAT / 'programs.csv'
    if not path.exists():
        print('skip programs.csv (not found)')
        return {}
    print('loading programs.csv')
    prog_key_to_id = {}
    with path.open(newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            name = row['name'].strip()
            ptype = row['program_type'].strip()
            sy = int(row['start_year'])
            ey = int(row['end_year'])
            cy = ensure_catalog_year(sy, ey)
            pid = upsert_program(name, ptype, cy)
            prog_key_to_id[(name, ptype, sy)] = pid
    return prog_key_to_id

def load_major_courses(course_map, program_map):
    path = CAT / 'major_courses.csv'
    if not path.exists():
        print('skip major_courses.csv (not found)')
        return
    print('loading major_courses.csv')
    with path.open(newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            pname = row['program_name'].strip()
            ptype = row['program_type'].strip()
            sy = int(row['start_year'])
            subj = row['subject'].strip()
            num = row['cata_num'].strip()
            elig = row['eligible_course'].strip()
            prog_id = program_map.get((pname, ptype, sy))
            course_id = course_map.get((subj, num))
            if prog_id and course_id:
                ensure_major_course(prog_id, course_id, elig)
            else:
                print(f'skip major_courses row, missing ids: {(pname, ptype, sy)} -> {prog_id}, {(subj, num)} -> {course_id}')

def load_prereqs(course_map):
    path = CAT / 'prereqs.csv'
    if not path.exists():
        print('skip prereqs.csv (not found)')
        return
    print('loading prereqs.csv')
    with path.open(newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            subj = row['subject'].strip()
            num = row['cata_num'].strip()
            psubj = row['prereq_subject'].strip()
            pnum = row['prereq_cata_num'].strip()
            mg = row['min_grade'].strip()
            cid = course_map.get((subj, num))
            pid = course_map.get((psubj, pnum))
            if cid and pid:
                ensure_prereq(cid, pid, mg)
            else:
                print(f'skip prereq row, missing ids: {(subj, num)} or {(psubj, pnum)}')

def load_schedule(course_map):
    """
    Load section + meeting times from catalog/schedule.csv.

    Each row describes one section; we generate one meeting row per day letter
    in days_pattern (e.g., 'MWF' -> three meeting rows).
    """
    path = CAT / 'schedule.csv'
    if not path.exists():
        print('skip schedule.csv (not found)')
        return
    print('loading schedule.csv')

    term_id = 8

    # starting IDs
    sec_row = fetch_dict("SELECT COALESCE(MAX(section_id),0) AS max_id FROM section")[0]
    meet_row = fetch_dict("SELECT COALESCE(MAX(meeting_id),0) AS max_id FROM meeting")[0]
    next_section_id = int(sec_row['max_id']) + 1
    next_meeting_id = int(meet_row['max_id']) + 1

    with path.open(newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            subj         = row['subject'].strip()
            num          = row['cata_num'].strip()
            section_code = row['section_code'].strip()
            days_pattern = row['days_pattern'].strip().upper()
            start_time   = row['start_time'].strip()  
            end_time     = row['end_time'].strip()     
            location     = row['location'].strip()

            # find course_id from the course_map
            course_id = course_map.get((subj, num))
            if not course_id:
                print(f"skip schedule row, no course found for {subj} {num}")
                continue

            # insert section
            section_id = next_section_id
            next_section_id += 1

            exec_sql("""
                INSERT INTO section (section_id, class_num, capacity, campus, meet_type, term_id, course_id)
                VALUES (?, ?, 60, 'UP', 'IN_PERSON', ?, ?)
            """, (section_id, section_code, term_id, course_id))

            print(f" inserted section {section_code} ({section_id}) for {subj} {num}")

            # insert one meeting per day 
            for ch in days_pattern:
                day_num = DAY_MAP.get(ch)
                if not day_num:
                    print(f"  !! unknown day '{ch}' in pattern '{days_pattern}', skipping")
                    continue

                meeting_id = next_meeting_id
                next_meeting_id += 1

                exec_sql("""
                    INSERT INTO meeting (meeting_id, location, section_id, start_time, end_time, days_of_week)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (meeting_id, location, section_id, start_time, end_time, day_num))


                print(f"  added meeting {ch} {start_time}-{end_time} at {location} (meeting_id={meeting_id})")

if __name__ == '__main__':
    print('DB:', DB)
    CAT.mkdir(exist_ok=True)

    # transactional batches in case of errors
    in_txn = False
    try:
        exec_sql("BEGIN")
        in_txn = True

        program_map = load_programs()
        course_map = load_courses()
        load_major_courses(course_map, program_map)
        load_prereqs(course_map)
        load_schedule(course_map)

        exec_sql("COMMIT")
        in_txn = False
        print('Import complete')
    except Exception:
        if in_txn:
            try:
                exec_sql("ROLLBACK")
            except duckdb.Error:
                pass
        raise
    finally:
        con.close()