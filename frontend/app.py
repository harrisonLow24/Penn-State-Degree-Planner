from flask import Flask, request, jsonify, render_template
import duckdb
import datetime
from pathlib import Path
import re

# set to parent direc of this file
BASE = Path(__file__).resolve().parent
DB_PATH = str((BASE.parent/'db' / 'course_planner.duckdb').resolve())

app = Flask(
    __name__,
    template_folder=str(BASE),
    static_folder=str(BASE),
    static_url_path=''
)

# debugger ( for ex: http://127.0.0.1:5000/health to see existing tables)
@app.get('/health')
def health():
    try:
        tables = run_query('SHOW TABLES')
        return {'ok': True, 'db': DB_PATH, 'tables': [t['name'] for t in tables]}
    except Exception as e:
        return {'ok': False, 'error': str(e)}, 500

# update when adding new tabs
@app.get('/')
def index():
    return render_template('index.html')

@app.get('/home')
def home():
    return render_template('index.html')

@app.get('/plan')
def plan():
    return render_template('index.html')

@app.get('/history')
def history_page():
    return render_template('index.html')



# helpers to return rows as dicts
def rows_to_dicts(cur):
    cols = [d[0].lower() for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]

def run_query(sql, params=()):
    con = duckdb.connect(DB_PATH)
    try:
        cur = con.execute(sql, params)
        out = rows_to_dicts(cur)
        con.close()
        return out
    except Exception as e:
        con.close()
        raise e

def run_exec(sql, params=()):
    con = duckdb.connect(DB_PATH)
    try:
        con.execute(sql, params)
        con.close()
    except Exception as e:
        con.close()
        raise e

# sign in by login_id amd create plan if none exists
@app.get('/api/signin')
def signin():
    login_id = request.args.get('login_id', '').strip()
    if not login_id:
        return jsonify({'error': 'login_id is required'}), 400

    student = run_query("""
        SELECT s.stu_id, s.login_id, s.f_name, s.l_name, s.email,
            s.expected_grad_term, s.catalog_year_id, s.advisor_id,
            a.f_name AS adv_first, a.l_name AS adv_last
        FROM student s
        LEFT JOIN advisor a ON a.adv_id = s.advisor_id
        WHERE s.login_id = ?
    """, (login_id,))

    # create student if not exists
    if not student:
        next_sid = run_query("SELECT COALESCE(MAX(stu_id),0)+1 AS nid FROM student")[0]['nid']
        cy = run_query("SELECT cy_id FROM catalog_year ORDER BY end_year DESC LIMIT 1")
        cy_id = cy[0]['cy_id'] if cy else None
        # pick a default advisor
        adv_rows = run_query("SELECT adv_id FROM advisor ORDER BY adv_id LIMIT 1")
        adv_id = adv_rows[0]['adv_id'] if adv_rows else None

        # pick a default expected grad term
        term_rows = run_query("SELECT term_id FROM term ORDER BY start_date DESC LIMIT 1")
        expected_term = term_rows[0]['term_id'] if term_rows else None

        run_exec("""
            INSERT INTO student (stu_id, login_id, f_name, l_name, email,
                                    expected_grad_term, catalog_year_id, advisor_id)
            VALUES (?, ?, 'New', 'Student', ? || '@psu.edu', ?, ?, ?)
        """, (next_sid, login_id, login_id, expected_term, cy_id, adv_id))

        student = run_query("""
            SELECT s.stu_id, s.login_id, s.f_name, s.l_name, s.email,
                s.expected_grad_term, s.catalog_year_id, s.advisor_id,
                a.f_name AS adv_first, a.l_name AS adv_last
            FROM student s
            LEFT JOIN advisor a ON a.adv_id = s.advisor_id
            WHERE s.stu_id = ?
        """, (next_sid,))

    stu = student[0]

    plan = run_query("SELECT plan_id FROM degree_plan WHERE stu_id = ? ORDER BY plan_id LIMIT 1", (stu['stu_id'],))
    if not plan:
        next_id = run_query("SELECT COALESCE(MAX(plan_id),0)+1 AS nid FROM degree_plan")[0]['nid']
        run_exec(
            "INSERT INTO degree_plan (plan_ID, stu_ID, cy_ID, time_created, target_grad_term_ID) VALUES (?,?,?,?,?)",
            (next_id, stu['stu_id'], stu['catalog_year_id'], datetime.datetime.utcnow(), stu['expected_grad_term'])
        )
        plan_id = next_id
    else:
        plan_id = plan[0]['plan_id']

    return jsonify({'student': stu, 'plan_id': plan_id})

# get planned courses for a given plan_id
@app.get('/api/plan')
def get_plan():
    try:
        plan_id = int(request.args.get('plan_id', ''))
    except:
        return jsonify({'error': 'plan_id required'}), 400

    rows = run_query("""
        WITH rec AS (
        SELECT c.course_id
        FROM degree_plan dp
        JOIN student_program sp ON sp.stu_id = dp.stu_id AND sp.primary_flag = TRUE
        JOIN program p ON p.prog_id = sp.prog_id AND p.program_type = 'Major'
        JOIN major_courses mc ON mc.major_id = sp.prog_id AND mc.eligible_course = TRUE
        JOIN course c ON c.course_id = mc.course_id
        WHERE dp.plan_id = ?
            AND NOT EXISTS (
            SELECT 1 FROM enrollment e
            JOIN section s ON s.section_id = e.section_id
            WHERE e.stu_id = dp.stu_id
                AND s.course_id = c.course_id
                AND e.grade IN ('A','A-','B+','B','B-','C+','C')
            )
            AND NOT EXISTS (
            SELECT 1 FROM course_prereq pre
            WHERE pre.course_id = c.course_id
                AND NOT EXISTS (
                SELECT 1
                FROM enrollment e2
                JOIN section s2 ON s2.section_id = e2.section_id
                WHERE e2.stu_id = dp.stu_id
                    AND s2.course_id = pre.prereq_course_id
                    AND e2.grade IN ('A','A-','B+','B','B-','C+','C')
                )
            )
        )
        SELECT
        pc.pc_id,
        COALESCE(pc.course_id, sec.course_id) AS course_id,
        pc.term_id,
        tm.code AS term_code,
        COALESCE(c.subject || ' ' || c.cata_num, '(manual)') AS course_code,
        c.title,
        CAST(c.credits AS INT) AS credits,
        CASE WHEN rec.course_id IS NOT NULL THEN 1 ELSE 0 END AS recommended
        FROM planned_course pc
        JOIN term tm ON tm.term_id = pc.term_id
        LEFT JOIN section sec ON sec.section_id = pc.section_id
        LEFT JOIN course c ON c.course_id = COALESCE(pc.course_id, sec.course_id)
        LEFT JOIN rec ON rec.course_id = COALESCE(pc.course_id, sec.course_id)
        WHERE pc.plan_id = ?
            AND NOT EXISTS (
            SELECT 1
            FROM enrollment e3
            JOIN section s3 ON s3.section_id = e3.section_id
            WHERE e3.stu_id = (SELECT stu_id FROM degree_plan WHERE plan_id = ?)
                AND s3.course_id = COALESCE(pc.course_id, sec.course_id)
                AND e3.grade IN ('A','A-','B+','B','B-','C+','C','P')
            )

        ORDER BY tm.start_date, course_code
    """, (plan_id, plan_id, plan_id))

    total = sum([r['credits'] or 0 for r in rows])
    return jsonify({'items': rows, 'total_credits': total})

# add a course to a plan by course_id
@app.post('/api/plan/add_course')
def add_course_to_plan():
    data = request.get_json(force=True)
    try:
        plan_id = int(data.get('plan_id'))
        term_id = int(data.get('term_id'))
        course_id = int(data.get('course_id'))
    except:
        return jsonify({'error': 'plan_id, term_id, course_id required'}), 400

    exists = run_query("SELECT 1 AS x FROM course WHERE course_id = ?", (course_id,))
    if not exists:
        return jsonify({'error': 'course_id does not exist'}), 400

    # find student for this plan
    plan_row = run_query("SELECT stu_id FROM degree_plan WHERE plan_id = ?", (plan_id,))
    if not plan_row:
        return jsonify({'error': 'plan_id not found'}), 400
    stu_id = plan_row[0]['stu_id']

    # completed courses for this student (subject, cata_num)
    completed_rows = run_query("""
        SELECT DISTINCT s.course_id, c.subject, c.cata_num
        FROM enrollment e
        JOIN section s ON s.section_id = e.section_id
        JOIN course c ON c.course_id = s.course_id
        WHERE e.stu_id = ?
          AND e.grade IN ('A','A-','B+','B','B-','C+','C','P')
    """, (stu_id,))
    completed_sc = {(r['subject'], str(r['cata_num'])) for r in completed_rows}

    # planned courses for this plan (subject, cata_num)
    planned_rows = run_query("""
        SELECT COALESCE(pc.course_id, sec.course_id) AS course_id,
               c.subject, c.cata_num
        FROM planned_course pc
        LEFT JOIN section sec ON sec.section_id = pc.section_id
        LEFT JOIN course c ON c.course_id = COALESCE(pc.course_id, sec.course_id)
        WHERE pc.plan_id = ?
    """, (plan_id,))
    planned_sc = {(r['subject'], str(r['cata_num'])) for r in planned_rows if r['subject'] is not None}

    # subject/cata of the course to add
    course_row = run_query("SELECT subject, cata_num FROM course WHERE course_id = ?", (course_id,))
    if not course_row:
        return jsonify({'error': 'course_id does not exist'}), 400
    candidate_key = (course_row[0]['subject'], str(course_row[0]['cata_num']))

    # equivalence sets (treat these as the same course)
    EQUIV_SETS = [
        {('CMPSC', '121'), ('CMPSC', '131')},
        {('CMPSC', '122'), ('CMPSC', '132')},
        {('CAS',   '100A'), ('CAS',   '100B')},
        {('CMPSC', '483W'), ('CMPSC', '431W')},
    ]

    def equiv_group(key):
        for group in EQUIV_SETS:
            if key in group:
                return group
        return {key}

    def has_equiv_in_set(key, key_set):
        group = equiv_group(key)
        for k in group:
            if k in key_set:
                return True
        return False

    # block adding if an equivalent course is already completed or in plan
    if has_equiv_in_set(candidate_key, completed_sc) or has_equiv_in_set(candidate_key, planned_sc):
        return jsonify({'error': 'equivalent course already completed or in plan'}), 400

    # prereqs for this course
    prereqs = run_query("""
        SELECT pre.prereq_course_id, c.subject, c.cata_num
        FROM course_prereq pre
        JOIN course c ON c.course_id = pre.prereq_course_id
        WHERE pre.course_id = ?
    """, (course_id,))

    # explicit OR prereq sets (MATH 110 or 140)
    OR_PREREQ_SETS = [
        {('MATH', '110'), ('MATH', '140')},
    ]

    def prereqs_ok_for_course():
        if not prereqs:
            return True

        used = set()
        alt_groups = []

        # build OR groups based on OR_PREREQ_SETS
        for alt_def in OR_PREREQ_SETS:
            group_keys = set()
            for p in prereqs:
                key_sc = (p['subject'], str(p['cata_num']))
                if key_sc in alt_def:
                    group_keys.add(key_sc)
            if group_keys:
                alt_groups.append(group_keys)
                used.update(group_keys)

        # everything else is a required prereq (AND)
        required_prereqs = [
            (p['subject'], str(p['cata_num']))
            for p in prereqs
            if (p['subject'], str(p['cata_num'])) not in used
        ]

        # all required prereqs must be satisfied (respecting equivalence)
        for subj, cata in required_prereqs:
            if not has_equiv_in_set((subj, cata), completed_sc):
                return False

        # each OR group must have at least one satisfied prereq
        for group in alt_groups:
            if not any(has_equiv_in_set(key_sc, completed_sc) for key_sc in group):
                return False

        return True

    if not prereqs_ok_for_course():
        return jsonify({'error': 'prerequisites not satisfied for this course'}), 400

    next_pc = run_query("SELECT COALESCE(MAX(pc_id),0)+1 AS nid FROM planned_course")[0]['nid']
    try:
        run_exec("""
            INSERT INTO planned_course (pc_id, term_id, plan_id, section_id, course_id, manual_courses)
            VALUES (?, ?, ?, NULL, ?, NULL)
        """, (next_pc, term_id, plan_id, course_id))
    except Exception as e:
        return jsonify({'error': str(e)}), 400

    return jsonify({'ok': True, 'pc_id': next_pc})


# remove a planned course row
@app.post('/api/plan/remove')
def remove_planned():
    data = request.get_json(force=True)
    try:
        pc_id = int(data.get('pc_id'))
    except:
        return jsonify({'error': 'pc_id required'}), 400

    run_exec("DELETE FROM planned_course WHERE pc_id = ?", (pc_id,))
    return jsonify({'ok': True})

# search courses
@app.get('/api/courses/search')
def search_courses():
    q = (request.args.get('q') or '').strip()
    subject = (request.args.get('subject') or '').strip()
    level = (request.args.get('level') or '').strip()  # '100','200','300','400','500' or ''

    sql = [
        "SELECT course_id, subject, cata_num, title, credits",
        "FROM course",
        "WHERE 1=1"
    ]
    params = []

    code_match = None
    if q:
        code_match = re.match(r'^\s*([A-Za-z]{2,5})\s*([0-9]{1,3})\s*$', q)

    if code_match:
        subj_code, num_code = code_match.groups()
        sql.append("AND subject = ? AND cata_num LIKE ?")
        params.extend([subj_code.upper(), num_code + '%'])
    elif q:
        sql.append("AND (UPPER(subject) LIKE UPPER(?) OR UPPER(title) LIKE UPPER(?) OR cata_num LIKE ?)")
        params.extend([q + '%', '%' + q + '%', q + '%'])

    if subject and not code_match:
        sql.append("AND subject = ?")
        params.append(subject)

    if level and level.isdigit():
        first_digit = str(int(level) // 100) 
        sql.append("AND cata_num LIKE ?")
        params.append(first_digit + '%')

    sql.append("ORDER BY subject, cata_num LIMIT 100")
    rows = run_query("\n".join(sql), tuple(params))
    return jsonify({'items': rows})

# list missing prereqs for selectex course
@app.get('/api/prereqs_missing')
def prereqs_missing():
    try:
        stu_id = int(request.args.get('stu_id', ''))
        course_id = int(request.args.get('course_id', ''))
    except:
        return jsonify({'error': 'stu_id and course_id required'}), 400

    rows = run_query("""
        SELECT pre.prereq_course_id, c2.subject, c2.cata_num, c2.title
        FROM course_prereq pre
        JOIN course c2 ON c2.course_id = pre.prereq_course_id
        WHERE pre.course_id = ?
          AND NOT EXISTS (
            SELECT 1
            FROM enrollment e
            JOIN section s ON s.section_id = e.section_id
            WHERE e.stu_id = ?
              AND s.course_id = pre.prereq_course_id
              AND e.grade IN ('A','A-','B+','B','B-','C+','C')
          )
        ORDER BY c2.subject, c2.cata_num
    """, (course_id, stu_id))
    return jsonify({'items': rows})

# find time conflicts
@app.get('/api/time_conflicts')
def time_conflicts():
    try:
        plan_id = int(request.args.get('plan_id', ''))
    except:
        return jsonify({'error': 'plan_id required'}), 400

    rows = run_query("""
        SELECT a.section_id AS sec_a, b.section_id AS sec_b,
               a.days_of_week, a.start_time, a.end_time, b.start_time AS b_start, b.end_time AS b_end
        FROM meeting a
        JOIN meeting b
          ON a.section_id <> b.section_id
         AND a.days_of_week = b.days_of_week
         AND a.start_time < b.end_time
         AND b.start_time < a.end_time
        WHERE a.section_id IN (
          SELECT section_id FROM planned_course WHERE plan_id = ? AND section_id IS NOT NULL
        )
          AND b.section_id IN (
          SELECT section_id FROM planned_course WHERE plan_id = ? AND section_id IS NOT NULL
        )
        ORDER BY a.days_of_week, a.start_time, b.start_time
    """, (plan_id, plan_id))
    return jsonify({'items': rows})

@app.get('/api/subjects')
def subjects():
    rows = run_query("SELECT DISTINCT subject FROM course ORDER BY subject")
    return jsonify({'items': [r['subject'] for r in rows]})

# list programs
@app.get('/api/programs')
def programs():
    rows = run_query("SELECT prog_id, name, program_type, catalog_year_id FROM program ORDER BY name")
    return jsonify({'items': rows})

# list advisors
@app.get('/api/advisors')
def advisors():
    rows = run_query("""
        SELECT adv_id, f_name, l_name, email
        FROM advisor
        ORDER BY l_name, f_name
    """)
    return jsonify({'items': rows})

# get primary major for a student
@app.get('/api/student/major')
def get_student_major():
    try:
        stu_id = int(request.args.get('stu_id', ''))
    except:
        return jsonify({'error': 'stu_id required'}), 400
    rows = run_query("""
        SELECT sp.prog_id, p.name, p.program_type, p.catalog_year_id
        FROM student_program sp
        JOIN program p ON p.prog_id = sp.prog_id
        WHERE sp.stu_id = ? AND sp.primary_flag = TRUE
        LIMIT 1
    """, (stu_id,))
    return jsonify({'item': rows[0] if rows else None})

# set primary major for a student
@app.post('/api/student/major')
def set_student_major():
    data = request.get_json(force=True)
    try:
        stu_id = int(data.get('stu_id'))
        prog_id = int(data.get('prog_id'))
    except:
        return jsonify({'error': 'stu_id and prog_id required'}), 400

    # clear old primary
    run_exec("UPDATE student_program SET primary_flag = FALSE WHERE stu_id = ?", (stu_id,))

    exists = run_query("SELECT sp_id FROM student_program WHERE stu_id = ? AND prog_id = ?", (stu_id, prog_id))
    if exists:
        run_exec("UPDATE student_program SET primary_flag = TRUE WHERE sp_id = ?", (exists[0]['sp_id'],))
    else:
        next_sp = run_query("SELECT COALESCE(MAX(sp_id),0)+1 AS nid FROM student_program")[0]['nid']
        run_exec("""
            INSERT INTO student_program (sp_id, stu_id, prog_id, primary_flag, start_term)
            VALUES (?, ?, ?, TRUE, NULL)
        """, (next_sp, stu_id, prog_id))

    return jsonify({'ok': True})

# list completed courses for a student
@app.get('/api/history')
def history():
    try:
        stu_id = int(request.args.get('stu_id', ''))
    except:
        return jsonify({'error': 'stu_id required'}), 400

    rows = run_query("""
        SELECT c.course_id, c.subject, c.cata_num, c.title, e.grade, 
                     CAST(c.credits AS INT) AS credits, tm.code as term_code,
                     e.enroll_id AS enroll_id, s.class_num
        FROM enrollment e
        JOIN section s ON s.section_id = e.section_id
        LEFT JOIN term tm ON tm.term_id = s.term_id
        JOIN course c ON c.course_id = s.course_id
        WHERE e.stu_id = ?
            AND e.grade IS NOT NULL
        ORDER BY tm.start_date NULLS LAST, c.subject, c.cata_num
    """, (stu_id,))
    return jsonify({'items': rows})

# mark a course as completed
@app.post('/api/history/add_course')
def history_add_course():
    data = request.get_json(force=True)
    try:
        stu_id = int(data.get('stu_id'))
        course_id = int(data.get('course_id'))
        grade = (data.get('grade') or 'A').strip().upper()
    except:
        return jsonify({'error': 'stu_id, course_id required'}), 400

    # ensure section exists for course
    sec = run_query("SELECT section_id FROM section WHERE class_num = ? LIMIT 1", (f'HIST-{course_id}',))
    if sec:
        section_id = sec[0]['section_id']
    else:
        next_sec = run_query("SELECT COALESCE(MAX(section_id),0)+1 AS nid FROM section")[0]['nid']
        run_exec("""
            INSERT INTO section (section_id, class_num, capacity, campus, meet_type, term_id, course_id)
            VALUES (?, ?, 999, 'HISTORY', 'HISTORY', 8, ?)
        """, (next_sec, f'HIST-{course_id}', course_id))
        section_id = next_sec
    
    # insert or update enrollment
    has = run_query("SELECT enroll_ID FROM enrollment WHERE stu_ID = ? AND section_ID = ?", (stu_id, section_id))
    if has:
        run_exec("UPDATE enrollment SET grade = ?, status = 'COMPLETE' WHERE enroll_ID = ?", (grade, has[0]['enroll_id']))
    else:
        next_enr = run_query("SELECT COALESCE(MAX(enroll_ID),0)+1 AS nid FROM enrollment")[0]['nid']
        run_exec("""
            INSERT INTO enrollment (enroll_ID, stu_ID, section_ID, grade, status, credits_earned)
            VALUES (?, ?, ?, ?, 'COMPLETE', NULL)
        """, (next_enr, stu_id, section_id, grade))

    return jsonify({'ok': True})

@app.post('/api/history/update_grade')
def history_update_grade():
    data = request.get_json(force=True)
    try:
        stu_id = int(data.get('stu_id'))
        enroll_id = int(data.get('enroll_id'))
        grade = (data.get('grade') or '').strip().upper()
    except:
        return jsonify({'error': 'stu_id, enroll_id, grade required'}), 400

    allowed = {'A','A-','B+','B','B-','C+','C','C-','D','F','P','NP'}
    if grade not in allowed:
        return jsonify({'error': 'invalid grade'}), 400

    run_exec("UPDATE enrollment SET grade = ? WHERE enroll_ID = ? AND stu_ID = ?", (grade, enroll_id, stu_id))
    return jsonify({'ok': True})

@app.post('/api/history/remove')
def history_remove():
    data = request.get_json(force=True)
    try:
        stu_id = int(data.get('stu_id'))
        enroll_id = int(data.get('enroll_id'))
    except:
        return jsonify({'error': 'stu_id and enroll_id required'}), 400

    # capture section before delete
    sec = run_query("SELECT section_id FROM enrollment WHERE enroll_ID = ? AND stu_ID = ?", (enroll_id, stu_id))
    if not sec:
        return jsonify({'ok': True})
    section_id = sec[0]['section_id']

    run_exec("DELETE FROM enrollment WHERE enroll_ID = ? AND stu_ID = ?", (enroll_id, stu_id))

    # clean up synthetic section if orphaned
    left = run_query("SELECT COUNT(*) AS n FROM enrollment WHERE section_id = ?", (section_id,))
    if left and int(left[0]['n']) == 0:
        run_exec("DELETE FROM section WHERE section_id = ?", (section_id,))

    return jsonify({'ok': True})

# course recommendations based on major and completed courses
@app.get('/api/recommendations')
def recommendations():
    try:
        stu_id = int(request.args.get('stu_id', ''))
        plan_id = int(request.args.get('plan_id', ''))
    except:
        return jsonify({'error': 'stu_id and plan_id required'}), 400

    # primary major
    major = run_query("SELECT prog_id FROM student_program WHERE stu_id = ? AND primary_flag = TRUE LIMIT 1", (stu_id,))
    if not major:
        return jsonify({'items': []})
    prog_id = major[0]['prog_id']

    # completed credits to estimate semester standing
    credits_rows = run_query("""
        SELECT COALESCE(SUM(CAST(c.credits AS INT)), 0) AS total_credits
        FROM enrollment e
        JOIN section s ON s.section_id = e.section_id
        JOIN course c ON c.course_id = s.course_id
        WHERE e.stu_id = ?
          AND e.grade IN ('A','A-','B+','B','B-','C+','C','P')
    """, (stu_id,))
    total_credits = credits_rows[0]['total_credits'] if credits_rows else 0
    try:
        total_credits = int(total_credits)
    except:
        total_credits = 0

    sem_standing = (total_credits // 15) + 1
    if sem_standing < 1:
        sem_standing = 1

    rows = run_query("""
        SELECT c.course_id, c.subject, c.cata_num, c.title, CAST(c.credits AS INT) AS credits
        FROM major_courses mc
        JOIN program p ON p.prog_id = mc.major_id AND p.program_type = 'Major'
        JOIN course c ON c.course_id = mc.course_id
        WHERE mc.major_id = ?
          AND mc.eligible_course = TRUE
          AND NOT EXISTS (
            SELECT 1 FROM enrollment e
            JOIN section s ON s.section_id = e.section_id
            WHERE e.stu_id = ?
              AND s.course_id = c.course_id
              AND e.grade IN ('A','A-','B+','B','B-','C+','C','P')
          )
          AND NOT EXISTS (
            SELECT 1 FROM planned_course pc
            LEFT JOIN section sec ON sec.section_id = pc.section_id
            WHERE pc.plan_id = ?
              AND COALESCE(pc.course_id, sec.course_id) = c.course_id
          )
        ORDER BY c.subject, c.cata_num
        LIMIT 50
    """, (prog_id, stu_id, plan_id))

    if not rows:
        return jsonify({'items': []})

    # completed courses (subject, cata_num) for prereqs and equivalence
    taken_rows = run_query("""
        SELECT DISTINCT s.course_id, c.subject, c.cata_num
        FROM enrollment e
        JOIN section s ON s.section_id = e.section_id
        JOIN course c ON c.course_id = s.course_id
        WHERE e.stu_id = ?
          AND e.grade IN ('A','A-','B+','B','B-','C+','C','P')
    """, (stu_id,))
    completed_sc = {(r['subject'], str(r['cata_num'])) for r in taken_rows}

    # planned courses (subject, cata_num) for this plan
    plan_courses = run_query("""
        SELECT COALESCE(pc.course_id, sec.course_id) AS course_id,
               c.subject, c.cata_num
        FROM planned_course pc
        LEFT JOIN section sec ON sec.section_id = pc.section_id
        LEFT JOIN course c ON c.course_id = COALESCE(pc.course_id, sec.course_id)
        WHERE pc.plan_id = ?
    """, (plan_id,))
    planned_sc = {(r['subject'], str(r['cata_num'])) for r in plan_courses if r['subject'] is not None}

    # equivalence sets (treat these as the same course)
    EQUIV_SETS = [
        {('CMPSC', '121'), ('CMPSC', '131')},
        {('CMPSC', '122'), ('CMPSC', '132')},
        {('CAS',   '100A'), ('CAS',   '100B')},
        {('CMPSC', '483W'), ('CMPSC', '431W')},
    ]

    def equiv_group(key):
        for group in EQUIV_SETS:
            if key in group:
                return group
        return {key}

    def has_equiv_in_set(key, key_set):
        group = equiv_group(key)
        for k in group:
            if k in key_set:
                return True
        return False

    blocked_sc = completed_sc.union(planned_sc)

    # prereqs for all candidate courses
    prereq_map = {}
    course_ids = [r['course_id'] for r in rows]
    if course_ids:
        placeholders = ",".join(["?"] * len(course_ids))
        pre_rows = run_query(f"""
            SELECT pre.course_id, pre.prereq_course_id, c.subject, c.cata_num
            FROM course_prereq pre
            JOIN course c ON c.course_id = pre.prereq_course_id
            WHERE pre.course_id IN ({placeholders})
        """, tuple(course_ids))
        for pr in pre_rows:
            cid = pr['course_id']
            prereq_map.setdefault(cid, []).append(pr)

    # explicit OR prereq sets (MATH 110 or 140)
    OR_PREREQ_SETS = [
        {('MATH', '110'), ('MATH', '140')},
    ]

    def prereqs_ok(row):
        plist = prereq_map.get(row['course_id'], [])
        if not plist:
            return True

        used = set()
        alt_groups = []

        # build OR groups based on OR_PREREQ_SETS
        for alt_def in OR_PREREQ_SETS:
            group_keys = set()
            for p in plist:
                key_sc = (p['subject'], str(p['cata_num']))
                if key_sc in alt_def:
                    group_keys.add(key_sc)
            if group_keys:
                alt_groups.append(group_keys)
                used.update(group_keys)

        # everything else is a required prereq (AND)
        required_prereqs = [
            (p['subject'], str(p['cata_num']))
            for p in plist
            if (p['subject'], str(p['cata_num'])) not in used
        ]

        # all required prereqs must be satisfied (respecting equivalence)
        for subj, cata in required_prereqs:
            if not has_equiv_in_set((subj, cata), completed_sc):
                return False

        # each OR group must have at least one satisfied prereq
        for group in alt_groups:
            if not any(has_equiv_in_set(key_sc, completed_sc) for key_sc in group):
                return False

        return True

    # order of courses for reccs
    flowsheet_order = [
        ('CMPSC', '121'),
        ('CMPSC', '131'),
        ('MATH', '140'),
        ('ENGL', '15'),
        # first year spring
        ('CMPSC', '122'),
        ('CMPSC', '132'),
        ('MATH', '141'),
        ('PHYS', '211'),
        # second year fall
        ('CMPSC', '221'),
        ('MATH', '230'),
        ('MATH', '220'),
        ('PHYS', '212'),
        ('CAS', '100A'),
        ('CAS', '100B'),
        # second year spring
        ('CMPSC', '360'),
        ('CMPEN', '270'),
        ('CMPSC', '311'),
        # third year fall
        ('CMPSC', '465'),
        ('CMPEN', '331'),
        ('STAT', '318'),
        ('CMPSC', '461'),
        # third year spring
        ('CMPSC', '464'),
        ('CMPSC', '473'),
        ('STAT', '319'),
        ('ENGL', '202C'),
        # fourth year
        ('CMPSC', '483W'),
        ('CMPSC', '431W'),
    ]

    # semester index for each flowsheet course (1 = first fall, 2 = first spring, etc.)
    flowsheet_semester = {
        ('CMPSC', '121'): 1,
        ('CMPSC', '131'): 1,
        ('MATH',  '140'): 1,
        ('ENGL',  '15'):  1,
        ('CMPSC', '122'): 2,
        ('CMPSC', '132'): 2,
        ('MATH',  '141'): 2,
        ('PHYS',  '211'): 2,
        ('CMPSC', '221'): 3,
        ('MATH',  '230'): 3,
        ('MATH',  '220'): 3,
        ('PHYS',  '212'): 3,
        ('CAS',   '100A'): 3,
        ('CAS',   '100B'): 3,
        ('CMPSC', '360'): 4,
        ('CMPEN', '270'): 4,
        ('CMPSC', '311'): 4,
        ('CMPSC', '465'): 5,
        ('CMPEN', '331'): 5,
        ('STAT',  '318'): 5,
        ('CMPSC', '461'): 5,
        ('CMPSC', '464'): 6,
        ('CMPSC', '473'): 6,
        ('STAT',  '319'): 6,
        ('ENGL',  '202C'): 6,
        ('CMPSC', '483W'): 7,
        ('CMPSC', '431W'): 7,
    }

    max_sem_to_show = sem_standing + 1
    if max_sem_to_show < 1:
        max_sem_to_show = 1

    def course_sem(row):
        key = (row['subject'], str(row['cata_num']))
        if key in flowsheet_semester:
            return flowsheet_semester[key]
        m = re.search(r'\d+', str(row['cata_num']))
        if m:
            num = int(m.group(0))
            if num < 200:
                return 1
            elif num < 300:
                return 3
            elif num < 400:
                return 5
            else:
                return 7
        return 8

    # only current or upcoming semester courses, with prereqs satisfied,
    # and no equivalent already completed or planned
    filtered = []
    for r in rows:
        key_sc = (r['subject'], str(r['cata_num']))
        if course_sem(r) > max_sem_to_show:
            continue
        if not prereqs_ok(r):
            continue
        if has_equiv_in_set(key_sc, blocked_sc):
            continue
        filtered.append(r)
    rows = filtered

    # map (subject, cata_num) to an index
    priority = {k: i for i, k in enumerate(flowsheet_order)}

    def sort_key(row):
        key = (row['subject'], str(row['cata_num']))
        if key in priority:
            return (priority[key], 0, 0)
        m = re.search(r'\d+', str(row['cata_num']))  # fallback
        num = int(m.group(0)) if m else 999
        return (len(priority) + num, row['subject'], str(row['cata_num']))

    rows.sort(key=sort_key)  # reorder based on flowsheet

    return jsonify({'items': rows})

# list available sections for courses in plan
@app.get('/api/schedule')
def available_schedule():
    try:
        plan_id = int(request.args.get('plan_id', ''))
    except:
        return jsonify({'error': 'plan_id required'}), 400

    rows = run_query("""
        SELECT
            s.section_id,
            c.subject || ' ' || c.cata_num AS course_code,
            c.title,
            m.days_of_week,
            CAST(m.start_time AS VARCHAR) AS start_time,
            CAST(m.end_time AS VARCHAR) AS end_time,
            m.location
        FROM planned_course pc
        JOIN course c ON c.course_id = pc.course_id
        JOIN section s ON s.course_id = c.course_id
        JOIN meeting m ON m.section_id = s.section_id
        WHERE pc.plan_id = ?
        AND s.class_num != '12346'
        ORDER BY c.subject, c.cata_num, m.days_of_week, m.start_time
    """, (plan_id,))
    return jsonify({'items': rows})

@app.get('/api/final_schedule')
def final_schedule():
    try:
        stu_id = int(request.args.get('stu_id', ''))
    except:
        return jsonify({'error': 'stu_id required'}), 400

    rows = run_query("""
        SELECT
            s.section_id,
            c.subject || ' ' || c.cata_num AS course_code,
            c.title,
            m.days_of_week,
            CAST(m.start_time AS VARCHAR) AS start_time,
            CAST(m.end_time AS VARCHAR) AS end_time,
            m.location
        FROM enrollment e
        JOIN section s ON s.section_id = e.section_id
        JOIN course c ON c.course_id = s.course_id
        JOIN meeting m ON m.section_id = s.section_id
        WHERE e.stu_id = ?
        AND e.status = 'ENROLLED'
        ORDER BY c.subject, c.cata_num, m.days_of_week, m.start_time
    """, (stu_id,))
    return jsonify({'items': rows})

@app.post('/api/final_schedule/remove')
def final_schedule_remove():
    data = request.get_json(force=True)
    try:
        stu_id = int(data.get('stu_id'))
        section_id = int(data.get('section_id'))
    except:
        return jsonify({'error': 'stu_id and section_id required'}), 400

    run_exec(
        "DELETE FROM enrollment WHERE stu_id = ? AND section_id = ? AND status = 'ENROLLED'",
        (stu_id, section_id)
    )
    return jsonify({'ok': True})

# enroll student in a chosen section
@app.post('/api/enroll')
def enroll_student():
    data = request.get_json(force=True)
    try:
        stu_id = int(data.get('stu_id'))
        section_id = int(data.get('section_id'))
    except:
        return jsonify({'error': 'stu_id and section_id required'}), 400

    # right selection
    sec = run_query("SELECT course_id FROM section WHERE section_id = ?", (section_id,))
    if not sec:
        return jsonify({'error': 'section not found'}), 400

    next_enr = run_query("SELECT COALESCE(MAX(enroll_id),0)+1 AS nid FROM enrollment")[0]['nid']
    run_exec("""
        INSERT INTO enrollment (enroll_id, stu_id, section_id, status, grade, credits_earned)
        VALUES (?, ?, ?, 'ENROLLED', NULL, NULL)
    """, (next_enr, stu_id, section_id))
    return jsonify({'ok': True, 'enroll_id': next_enr})


if __name__ == '__main__':
    app.run(debug=True)