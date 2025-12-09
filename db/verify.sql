SHOW TABLES;

SELECT s.stu_id, s.f_name, s.l_name, p.name AS program_name
FROM student s
JOIN student_program sp ON sp.stu_id = s.stu_id AND sp.primary_flag = TRUE
JOIN program p ON p.prog_id = sp.prog_id;

SELECT tm.code, SUM(CAST(c.credits AS INT)) AS planned_credits
FROM planned_course pc
JOIN term tm ON tm.term_id = pc.term_id
LEFT JOIN section sec ON sec.section_id = pc.section_id
LEFT JOIN course c ON c.course_id = COALESCE(pc.course_id, sec.course_id)
WHERE pc.plan_id = 6001 AND pc.term_id = 1
GROUP BY tm.code;

SELECT a.section_id AS a, b.section_id AS b, a.days_of_week, a.start_time, a.end_time, b.start_time, b.end_time
FROM meeting a
JOIN meeting b
    ON a.section_id <> b.section_id
    AND a.days_of_week = b.days_of_week
    AND a.start_time < b.end_time
    AND b.start_time < a.end_time
WHERE a.section_id IN (SELECT section_id FROM planned_course WHERE plan_id = 6001)
    AND b.section_id IN (SELECT section_id FROM planned_course WHERE plan_id = 6001)
ORDER BY a.days_of_week, a.start_time;

SELECT pre.prereq_course_id, c2.subject, c2.cata_num, c2.title
FROM course_prereq pre
JOIN course c2 ON c2.course_id = pre.prereq_course_id
WHERE pre.course_id = 2002
    AND NOT EXISTS (
    SELECT 1
    FROM enrollment e
    JOIN section s ON s.section_id = e.section_id
    WHERE e.stu_id = 1001
        AND s.course_id = pre.prereq_course_id
        AND e.grade IN ('A','A-','B+','B','B-','C+','C')
    );
