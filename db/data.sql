-- Catalog years
INSERT INTO catalog_year (cy_id, start_year, end_year) VALUES
  (1, 2025, 2026);

-- Terms
INSERT INTO term (term_id, code, start_date, end_date) VALUES
  (8, 'FA2026', DATE '2026-08-26', DATE '2026-12-12');

-- Advisors

INSERT INTO advisor (adv_id, f_name, l_name, email) VALUES
    (1, 'Sana', 'Waqar', 'sqw5484@psu.edu');

-- Program 

INSERT INTO program (prog_id, catalog_year_id, name, program_type) VALUES
    (1, 1, 'Computer Science B.S.', 'Major');

-- Students

INSERT INTO student (stu_ID, login_ID, f_name, l_name, email, expected_grad_term, advisor_id, catalog_year_id)
VALUES
    (1001, 'hml5637', 'Harrison', 'Low',  'hml5637@psu.edu', 8, 1, 1),
    (1002, 'imm5385', 'Ian',      'Mertz','imm5385@psu.edu', 8, 1, 1);

-- Link students to a program
INSERT INTO student_program (sp_id, stu_id, prog_id, primary_flag, start_term) VALUES
  (1, 1001, 1, TRUE, 8),
  (2, 1002, 1, FALSE, 8);

-- Courses and section
INSERT INTO course (course_id, title, subject, cata_num, credits) VALUES
  (2002, 'Database Management Systems', 'CMPSC', '431W', '3'),
  (2003, 'Discrete Math', 'CMPSC', '360',  '3');

INSERT INTO section (section_id, class_num, capacity, campus, meet_type, term_id, course_id) VALUES
  (3002, '12346', 60, 'UP', 'IN_PERSON', 8, 2002);

-- prerequisite: Discrete Math is required for Databases
INSERT INTO course_prereq (cp_id, prereq_course_id, course_id, min_grade) VALUES
  (1, 2003, 2002, 2);

-- Requirements and eligible courses
INSERT INTO requirements (req_id, prog_id, area_id, name, min_credits, min_gpa) VALUES
  (900, 1, 'CORE', 'Major Core', 36, 2.00);

INSERT INTO major_courses (major_course_id, major_id, course_id, eligible_course) VALUES
  (8001, 1, 2002, TRUE),
  (8002, 1, 2003, TRUE);

-- Meetings for the section
INSERT INTO meeting (meeting_ID, location, section_ID, start_time, end_time, days_of_week) VALUES
  (4001, 'Willard 101', 3002, TIME '11:15', TIME '12:05', 2),
  (4002, 'Willard 101', 3002, TIME '11:15', TIME '12:05', 4);

-- Degree plan and planned course
INSERT INTO degree_plan (plan_ID, stu_ID, cy_ID, time_created, target_grad_term_ID) VALUES
  (6001, 1001, 1, CURRENT_TIMESTAMP, 8);

INSERT INTO planned_course (pc_id, term_id, plan_id, section_id, course_id, manual_courses) VALUES
  (7001, 8, 6001, 3002, NULL, NULL);

-- Enrollment and waitlist
INSERT INTO enrollment (enroll_ID, stu_ID, section_ID, grade, status, credits_earned) VALUES
  (9001, 1001, 3002, NULL, 'ENROLLED', NULL);

INSERT INTO waitlist (wait_ID, stu_ID, section_ID, position) VALUES
  (9101, 1002, 3002, 1);
