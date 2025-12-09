-- =========================
-- Core catalog tables
-- =========================

CREATE TABLE catalog_year (
  cy_id INT PRIMARY KEY,
  start_year INT NOT NULL,
  end_year INT NOT NULL
);

CREATE TABLE term (
  term_id INT PRIMARY KEY,
  code VARCHAR(20) NOT NULL UNIQUE,
  start_date DATE NOT NULL,
  end_date DATE NOT NULL
);

CREATE TABLE advisor (
  adv_id INT PRIMARY KEY,
  f_name VARCHAR(40) NOT NULL,
  l_name VARCHAR(40) NOT NULL,
  email VARCHAR(320) NOT NULL UNIQUE
);

CREATE TABLE program (
  prog_id INT PRIMARY KEY,
  catalog_year_id INT NOT NULL REFERENCES catalog_year(cy_id),
  name VARCHAR(100) NOT NULL,
  program_type VARCHAR(40) NOT NULL,
  UNIQUE (name, program_type, catalog_year_id)
);

CREATE TABLE student (
  stu_ID INT PRIMARY KEY,
  login_ID TEXT NOT NULL UNIQUE,
  f_name TEXT NOT NULL,
  l_name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  expected_grad_term INT REFERENCES term(term_id),
  advisor_id INT REFERENCES advisor(adv_id),
  catalog_year_id INT NOT NULL REFERENCES catalog_year(cy_id)
);

-- =========================
-- Course and offering tables
-- =========================

CREATE TABLE course (
  course_id INT PRIMARY KEY,
  title VARCHAR(70) NOT NULL,
  subject VARCHAR(20) NOT NULL,
  cata_num VARCHAR(20) NOT NULL,
  credits VARCHAR(2) NOT NULL,
  UNIQUE (subject, cata_num)
);

CREATE TABLE section (
  section_id INT PRIMARY KEY,
  class_num VARCHAR(30) NOT NULL UNIQUE,
  capacity INT NOT NULL,
  campus VARCHAR(50) NOT NULL,
  meet_type VARCHAR(30) NOT NULL,
  term_id INT NOT NULL REFERENCES term(term_id),
--   ON DELETE RESTRICT ON UPDATE CASCADE
  course_id INT NOT NULL REFERENCES course(course_id),
--   ON DELETE RESTRICT ON UPDATE CASCADE
  UNIQUE (term_id, class_num),
  CHECK (capacity > 0)
);

CREATE TABLE meeting (
  meeting_ID INT PRIMARY KEY,
  location TEXT NOT NULL,
  section_ID INT NOT NULL REFERENCES section(section_ID),
  start_time TIME NOT NULL,
  end_time TIME NOT NULL,
  days_of_week INT NOT NULL,
  CHECK (days_of_week BETWEEN 1 AND 7),
  CHECK (end_time > start_time)
);

-- =========================
-- Student/program linkage
-- =========================

CREATE TABLE enrollment (
  enroll_ID INT PRIMARY KEY,
  stu_ID INT NOT NULL REFERENCES student(stu_ID),
  section_ID INT NOT NULL REFERENCES section(section_ID),
  grade CHAR(1),
  status VARCHAR(8),
  credits_earned INT,
  UNIQUE (stu_ID, section_ID)
);

CREATE TABLE student_program (
  sp_id INT PRIMARY KEY,
  stu_id INT NOT NULL REFERENCES student(stu_ID),
  prog_id INT NOT NULL REFERENCES program(prog_id),
  primary_flag BOOLEAN NOT NULL DEFAULT FALSE,
  start_term INT REFERENCES term(term_id),
  UNIQUE (stu_id, prog_id)
);

-- =========================
-- Requirements and major courses
-- =========================

CREATE TABLE requirements (
  req_id INT PRIMARY KEY,
  prog_id INT NOT NULL REFERENCES program(prog_id),
--   ON DELETE CASCADE ON UPDATE CASCADE
  area_id VARCHAR(40),
  name VARCHAR(100) NOT NULL,
  min_credits INT NOT NULL,
  min_gpa DECIMAL(3,2) NOT NULL,
  CHECK (min_credits >= 29 AND min_credits <= 55),
  CHECK (min_gpa >= 2.00)
);

CREATE TABLE major_courses (
  major_course_id INT PRIMARY KEY,
  major_id INT NOT NULL REFERENCES program(prog_id),
--   ON DELETE CASCADE ON UPDATE CASCADE
  course_id INT NOT NULL REFERENCES course(course_id),
--   ON DELETE CASCADE ON UPDATE CASCADE
  eligible_course BOOLEAN NOT NULL DEFAULT TRUE,
  UNIQUE (major_id, course_id)
);

-- =========================
-- Degree plan and planned courses
-- =========================

CREATE TABLE degree_plan (
  plan_ID INT PRIMARY KEY,
  stu_ID INT NOT NULL REFERENCES student(stu_ID),
  cy_ID INT NOT NULL REFERENCES catalog_year(cy_ID),
  time_created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  target_grad_term_ID INT REFERENCES term(term_id),
  UNIQUE (stu_ID, cy_ID)
);

CREATE TABLE planned_course (
  pc_id INT PRIMARY KEY,
--   ON DELETE CASCADE ON UPDATE CASCADE
  term_id INT NOT NULL REFERENCES term(term_id),
  plan_id INT NOT NULL REFERENCES degree_plan(plan_ID),
  section_id INT REFERENCES section(section_id),
  course_id INT REFERENCES course(course_id),

  manual_courses TEXT,
  UNIQUE (plan_id, term_id, section_id),
  UNIQUE (plan_id, term_id, course_id)
);

-- =========================
-- Course prerequisites
-- =========================

CREATE TABLE course_prereq (
  cp_id INT PRIMARY KEY,
  prereq_course_id INT NOT NULL REFERENCES course(course_id),
  course_id INT NOT NULL REFERENCES course(course_id),
  min_grade INT,
  UNIQUE (course_id, prereq_course_id)
);

-- =========================
-- Waitlist
-- =========================

CREATE TABLE waitlist (
  wait_ID INT PRIMARY KEY,
  stu_ID INT NOT NULL REFERENCES student(stu_ID),
  section_ID INT NOT NULL REFERENCES section(section_ID),
  position INT NOT NULL,
  CHECK (position > 0),
  time_added TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (section_ID, position),
  UNIQUE (stu_ID, section_ID)
);


-- =========================
-- Indexes (to speed up lookups)
-- =========================

CREATE INDEX idx_section_term ON section(term_id);
CREATE INDEX idx_meeting_conflict ON meeting(section_ID, days_of_week, start_time, end_time);
CREATE INDEX idx_enrollment_student ON enrollment(stu_ID);
CREATE INDEX idx_waitlist_section_position ON waitlist(section_ID, position);
CREATE INDEX idx_student_name ON student(f_name, l_name);
