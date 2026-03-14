const db = require('../config/db.js');
const { Parser } = require('json2csv');
const { dataAccessLog } = require('../middleware/loggingMiddleware');
const { getDepartmentFilterForRequest } = require('../middleware/authMiddleware');

/**
 * Export faculty list to CSV
 */
exports.exportFacultyCSV = (req, res) => {
    const { sdg, domain, year } = req.query;

    // Get department filter conditions
    let deptConditions = [];
    let deptParams = [];
        try {
            if (req.user && req.user.access_level) {
                const filter = getDepartmentFilterForRequest(req, 'u');
                deptConditions = filter.conditions;
                deptParams = filter.params;
            }
        } catch (err) {
      console.error('Department filter error:', err);
      return res.status(403).json({ success: false, message: 'Access denied: ' + err.message });
    }
    
    const filters = [];
    const params = [];
    
    if (sdg) {
        filters.push(`REPLACE(LOWER(pi.sustainable_development_goals), ' ', '') LIKE ?`);
        params.push(`%${sdg.toLowerCase().replace(/\s+/g, '')}%`);
    }
    
    if (domain) {
        filters.push(`REPLACE(LOWER(pi.qs_subject_field_name), ' ', '') LIKE ?`);
        params.push(`%${domain.toLowerCase().replace(/\s+/g, '')}%`);
    }
    
    if (year) {
        filters.push(`YEAR(p.date) = ?`);
        params.push(parseInt(year));
    }
    
    const whereClause = filters.length ? `AND ${filters.join(" AND ")}` : "";
    const deptWhereClause = deptConditions.length ? `AND ${deptConditions.join(" AND ")}` : "";
    
    const query = `
        SELECT
            u.faculty_id,
            u.faculty_name,
            u.department,
            u.email,
            u.scopus_id,
            u.docs_count,
            u.citations,
            u.h_index,
            GROUP_CONCAT(DISTINCT pi.sustainable_development_goals SEPARATOR '|') AS sdgs,
            COUNT(DISTINCT p.doi) AS filtered_docs
        FROM users u
        LEFT JOIN papers p ON u.scopus_id = p.scopus_id
        LEFT JOIN paper_insights pi ON p.doi = pi.doi
        WHERE u.faculty_id IS NOT NULL
        ${deptWhereClause}
        ${whereClause}
        GROUP BY u.faculty_id, u.faculty_name, u.department, u.email, u.scopus_id, u.docs_count, u.citations, u.h_index
        ORDER BY u.faculty_name
    `;
    
    const allParams = [...deptParams, ...params];
    
    db.query(query, allParams, (err, results) => {
        if (err) {
            return res.status(500).json({ success: false, message: 'Export error' });
        }
        
        if (results.length === 0) {
            return res.status(404).json({ success: false, message: 'No data to export' });
        }
        
        dataAccessLog(req.user?.username || 'anonymous', 'EXPORT', 'faculty_csv', req.ip);
        
        try {
            const csv = new Parser({
                fields: ['faculty_id', 'faculty_name', 'department', 'email', 'scopus_id', 'docs_count', 'citations', 'h_index', 'sdgs', 'filtered_docs'],
                excelStrings: true
            }).parse(results);
            
            res.header('Content-Type', 'text/csv');
            res.header('Content-Disposition', `attachment; filename="faculty_list_${Date.now()}.csv"`);
            res.send(csv);
        } catch (err) {
            console.error('CSV generation error:', err);
            res.status(500).json({ success: false, message: 'CSV generation error' });
        }
    });
};

/**
 * Export paper list to CSV
 */
exports.exportPapersCSV = (req, res) => {
    const { facultyId, startDate, endDate, minQuartile, maxQuartile } = req.query;
    
    let query = `
        SELECT 
            p.doi,
            p.title,
            p.scopus_id,
            p.publication_name,
            p.date,
            p.type,
            p.quartile,
            pi.sustainable_development_goals,
            pi.qs_subject_field_name
        FROM papers p
        LEFT JOIN paper_insights pi ON p.doi = pi.doi
        WHERE 1=1
    `;
    
    const params = [];
    
    if (facultyId) {
        query += ` AND p.scopus_id IN (
            SELECT scopus_id FROM users WHERE faculty_id = ?
        )`;
        params.push(facultyId);
    }
    
    if (startDate && endDate) {
        query += ` AND p.date BETWEEN ? AND ?`;
        params.push(startDate, endDate);
    }
    
    if (minQuartile) {
        query += ` AND CAST(p.quartile AS UNSIGNED) >= ?`;
        params.push(parseInt(minQuartile));
    }
    
    if (maxQuartile) {
        query += ` AND CAST(p.quartile AS UNSIGNED) <= ?`;
        params.push(parseInt(maxQuartile));
    }
    
    query += ` ORDER BY p.date DESC LIMIT 5000`;
    
    db.query(query, params, (err, results) => {
        if (err) {
            return res.status(500).json({ success: false, message: 'Export error' });
        }
        
        if (results.length === 0) {
            return res.status(404).json({ success: false, message: 'No data to export' });
        }
        
        dataAccessLog(req.user?.username || 'anonymous', 'EXPORT', 'papers_csv', req.ip);
        
        try {
            const csv = new Parser({
                fields: ['doi', 'title', 'scopus_id', 'publication_name', 'date', 'type', 'quartile', 'sustainable_development_goals', 'qs_subject_field_name'],
                excelStrings: true
            }).parse(results);
            
            res.header('Content-Type', 'text/csv');
            res.header('Content-Disposition', `attachment; filename="papers_export_${Date.now()}.csv"`);
            res.send(csv);
        } catch (err) {
            console.error('CSV generation error:', err);
            res.status(500).json({ success: false, message: 'CSV generation error' });
        }
    });
};

/**
 * Export faculty detailed report
 */
exports.exportFacultyReport = (req, res) => {
    const { facultyId } = req.params;
    
    const facultyQuery = `
        SELECT * FROM users WHERE faculty_id = ? LIMIT 1
    `;
    
    db.query(facultyQuery, [facultyId], (err, facultyResults) => {
        if (err || facultyResults.length === 0) {
            return res.status(500).json({ success: false, message: 'Faculty not found' });
        }
        
        const faculty = facultyResults[0];
        
        const papersQuery = `
            SELECT p.*, pi.sustainable_development_goals, pi.qs_subject_field_name
            FROM papers p
            LEFT JOIN paper_insights pi ON p.doi = pi.doi
            WHERE p.scopus_id = ?
            ORDER BY p.date DESC
        `;
        
        db.query(papersQuery, [faculty.scopus_id], (err, papers) => {
            if (err) {
                return res.status(500).json({ success: false, message: 'Export error' });
            }
            
            dataAccessLog(req.user?.username || 'anonymous', 'EXPORT', `faculty_report_${facultyId}`, req.ip);
            
            try {
                const csv = new Parser({
                    fields: ['doi', 'title', 'scopus_id', 'publication_name', 'date', 'type', 'quartile', 'sustainable_development_goals', 'qs_subject_field_name'],
                    excelStrings: true
                }).parse(papers);
                
                res.header('Content-Type', 'text/csv');
                res.header('Content-Disposition', `attachment; filename="faculty_report_${facultyId}_${Date.now()}.csv"`);
                res.send(csv);
            } catch (err) {
                console.error('CSV generation error:', err);
                res.status(500).json({ success: false, message: 'CSV generation error' });
            }
        });
    });
};
