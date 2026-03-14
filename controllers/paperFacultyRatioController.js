const db = require('../config/db');

const getPaperFacultyRatio = (req, res) => {
    try {
        const { year, department } = req.query;
        const selectedYear = year ? parseInt(year, 10) : new Date().getFullYear();
        const startDate = `${selectedYear}-01-01`;
        const endDate = `${selectedYear}-12-31`;

        let deptClause = '';
        const deptParams = [];
        if (department && department !== 'all') {
            deptClause = 'AND u.department = ?';
            deptParams.push(department);
        }

        const facultyQuery = `
            SELECT u.id, u.faculty_id, u.faculty_name, u.scopus_id, u.department
            FROM users u
            WHERE u.scopus_id IS NOT NULL AND u.scopus_id != 0
            ${deptClause}
            ORDER BY u.faculty_name ASC
        `;

        db.query(facultyQuery, deptParams, (err, facultyRows) => {
            if (err) {
                console.error('Error fetching faculty:', err);
                return res.status(500).json({ success: false, message: 'Internal server error', error: err.message });
            }

            if (facultyRows.length === 0) {
                return res.json({ year: selectedYear, startDate, endDate, totalFaculty: 0, totalPapers: 0, ratio: 0, faculty: [] });
            }

            const scopusIds = facultyRows.map(f => f.scopus_id);
            const placeholders = scopusIds.map(() => '?').join(',');

            const papersQuery = `
                SELECT p.id, p.scopus_id, p.doi, p.title, p.type, p.publication_name,
                       p.date, p.author1, p.author2, p.author3, p.author4, p.author5,
                       p.author6, p.affiliation1, p.affiliation2, p.affiliation3, p.quartile
                FROM papers p
                WHERE p.scopus_id IN (${placeholders})
                AND p.date BETWEEN ? AND ?
                ORDER BY p.date DESC
            `;

            db.query(papersQuery, [...scopusIds, startDate, endDate], (err, paperRows) => {
                if (err) {
                    console.error('Error fetching papers:', err);
                    return res.status(500).json({ success: false, message: 'Internal server error', error: err.message });
                }

                const papersByAuthor = {};
                paperRows.forEach(paper => {
                    const sid = String(paper.scopus_id);
                    if (!papersByAuthor[sid]) papersByAuthor[sid] = [];
                    papersByAuthor[sid].push(paper);
                });

                const facultyData = facultyRows.map(faculty => {
                    const sid = String(faculty.scopus_id);
                    const papers = papersByAuthor[sid] || [];
                    return {
                        faculty_id: faculty.faculty_id,
                        faculty_name: faculty.faculty_name,
                        scopus_id: faculty.scopus_id,
                        department: faculty.department,
                        paper_count: papers.length,
                        papers: papers,
                    };
                });

                const totalFaculty = facultyData.length;
                const totalPapers = paperRows.length;
                const ratio = totalFaculty > 0 ? parseFloat((totalPapers / totalFaculty).toFixed(2)) : 0;

                return res.json({ year: selectedYear, startDate, endDate, totalFaculty, totalPapers, ratio, faculty: facultyData });
            });
        });
    } catch (error) {
        console.error('Error in getPaperFacultyRatio:', error);
        return res.status(500).json({ success: false, message: 'Internal server error', error: error.message });
    }
};

const getDepartments = (req, res) => {
    try {
        const query = `
            SELECT DISTINCT department FROM users
            WHERE department IS NOT NULL AND department != ''
            ORDER BY department ASC
        `;
        db.query(query, (err, rows) => {
            if (err) {
                console.error('Error fetching departments:', err);
                return res.status(500).json({ success: false, message: 'Internal server error' });
            }
            return res.json(rows.map(r => r.department));
        });
    } catch (error) {
        console.error('Error in getDepartments:', error);
        return res.status(500).json({ success: false, message: 'Internal server error' });
    }
};

module.exports = { getPaperFacultyRatio, getDepartments };
