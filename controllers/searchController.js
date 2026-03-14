const db = require('../config/db.js');
const { dataAccessLog } = require('../middleware/loggingMiddleware');

/**
 * Global search across faculty and papers
 */
exports.globalSearch = (req, res) => {
    const { q, type } = req.query;
    
    if (!q || q.trim().length < 2) {
        return res.status(400).json({
            success: false,
            message: 'Search query must be at least 2 characters'
        });
    }
    
    const searchTerm = `%${q.trim()}%`;
    const results = {};
    
    // Log search access
    dataAccessLog(req.user?.username || 'anonymous', 'SEARCH', `query: ${q}`, req.ip);
    
    // Search faculty
    if (!type || type === 'faculty') {
        const facultyQuery = `
            SELECT id, faculty_id, faculty_name, email, scopus_id, access_level 
            FROM users 
            WHERE (faculty_name LIKE ? OR faculty_id LIKE ? OR email LIKE ?)
            AND faculty_id IS NOT NULL
            LIMIT 10
        `;
        
        db.query(facultyQuery, [searchTerm, searchTerm, searchTerm], (err, facultyResults) => {
            if (!err) {
                results.faculty = facultyResults || [];
            }
            
            // Search papers
            if (!type || type === 'papers') {
                const papersQuery = `
                    SELECT doi, title, scopus_id, publication_name, date 
                    FROM papers 
                    WHERE (title LIKE ? OR publication_name LIKE ? OR doi LIKE ?)
                    LIMIT 10
                `;
                
                db.query(papersQuery, [searchTerm, searchTerm, searchTerm], (err, paperResults) => {
                    if (!err) {
                        results.papers = paperResults || [];
                    }
                    
                    // Search SDGs
                    const sdgQuery = `
                        SELECT DISTINCT sustainable_development_goals 
                        FROM paper_insights 
                        WHERE sustainable_development_goals LIKE ?
                        LIMIT 5
                    `;
                    
                    db.query(sdgQuery, [searchTerm], (err, sdgResults) => {
                        if (!err) {
                            results.sdgs = sdgResults?.map(r => r.sustainable_development_goals) || [];
                        }
                        
                        res.json({
                            success: true,
                            query: q,
                            results,
                            total: (results.faculty?.length || 0) + (results.papers?.length || 0)
                        });
                    });
                });
            }
        });
    }
};

/**
 * Advanced search with filters
 */
exports.advancedSearch = (req, res) => {
    const { facultyName, scopusId, startDate, endDate, minHIndex, maxHIndex, sdg, domain } = req.query;
    
    let query = `
        SELECT DISTINCT 
            u.id, u.faculty_id, u.faculty_name, u.email, u.scopus_id, 
            u.h_index, u.citations, u.docs_count,
            COUNT(DISTINCT p.doi) as paper_count
        FROM users u
        LEFT JOIN papers p ON u.scopus_id = p.scopus_id
        LEFT JOIN paper_insights pi ON p.doi = pi.doi
        WHERE u.faculty_id IS NOT NULL
    `;
    
    const params = [];
    
    if (facultyName) {
        query += ` AND u.faculty_name LIKE ?`;
        params.push(`%${facultyName}%`);
    }
    
    if (scopusId) {
        query += ` AND u.scopus_id = ?`;
        params.push(scopusId);
    }
    
    if (startDate && endDate) {
        query += ` AND p.date BETWEEN ? AND ?`;
        params.push(startDate, endDate);
    }
    
    if (minHIndex) {
        query += ` AND u.h_index >= ?`;
        params.push(parseInt(minHIndex));
    }
    
    if (maxHIndex) {
        query += ` AND u.h_index <= ?`;
        params.push(parseInt(maxHIndex));
    }
    
    if (sdg) {
        query += ` AND pi.sustainable_development_goals LIKE ?`;
        params.push(`%${sdg}%`);
    }
    
    if (domain) {
        query += ` AND pi.qs_subject_field_name LIKE ?`;
        params.push(`%${domain}%`);
    }
    
    query += ` GROUP BY u.id ORDER BY u.faculty_name LIMIT 50`;
    
    db.query(query, params, (err, results) => {
        if (err) {
            return res.status(500).json({ success: false, message: 'Search error' });
        }
        
        res.json({
            success: true,
            count: results.length,
            results
        });
    });
};

/**
 * Search papers by criteria
 */
exports.searchPapers = (req, res) => {
    const { title, doi, scopusId, startDate, endDate, minQuartile, maxQuartile } = req.query;
    
    let query = `
        SELECT p.*, pi.sustainable_development_goals, pi.qs_subject_field_name 
        FROM papers p
        LEFT JOIN paper_insights pi ON p.doi = pi.doi
        WHERE 1=1
    `;
    
    const params = [];
    
    if (title) {
        query += ` AND p.title LIKE ?`;
        params.push(`%${title}%`);
    }
    
    if (doi) {
        query += ` AND p.doi = ?`;
        params.push(doi);
    }
    
    if (scopusId) {
        query += ` AND p.scopus_id = ?`;
        params.push(scopusId);
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
    
    query += ` ORDER BY p.date DESC LIMIT 100`;
    
    db.query(query, params, (err, results) => {
        if (err) {
            console.error('Paper search error:', err);
            return res.status(500).json({ success: false, message: 'Search error' });
        }
        
        res.json({
            success: true,
            count: results.length,
            results
        });
    });
};
