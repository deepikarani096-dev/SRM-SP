const db = require('../config/db.js');
const { getDepartmentFilterForRequest } = require('../middleware/authMiddleware');

exports.getPaperDetails = (req, res) => {
    const { doi } = req.params;
    // Build department/faculty filter using centralized helper
    let deptConditionSql = '';
    let deptParams = [];
    try {
        const filter = getDepartmentFilterForRequest(req, 'u');
        if (filter && filter.conditions && filter.conditions.length) {
            deptConditionSql = ` AND ${filter.conditions.join(' AND ')}`;
            deptParams = filter.params;
        }
    } catch (err) {
        console.error('Department filter error:', err);
        return res.status(403).json({ error: 'Access denied: ' + err.message });
    }

    // Allow Admin to optionally filter by department via query param
    if (req.user && req.user.access_level === 1 && req.query && req.query.department) {
        deptConditionSql += (deptConditionSql ? ' AND ' : ' AND ') + 'u.department = ?';
        deptParams.push(req.query.department);
    }

    const query = `
        SELECT p.*
        FROM papers p
        JOIN users u ON p.scopus_id = u.scopus_id
        WHERE p.doi = ?
        ${deptConditionSql}
    `;

    const params = [doi, ...deptParams];

    db.query(query, params, (err, paperResults) => {
        if (err) return res.status(500).json({ error: 'Failed to fetch paper details' });
        if (!paperResults.length) return res.status(404).json({ error: 'Paper not found or access denied' });

        // Query insights for this paper (no extra filters needed)
        db.query('SELECT * FROM paper_insights WHERE doi = ?', [doi], (err, insightsResults) => {
            if (err) return res.status(500).json({ error: 'Failed to fetch paper insights' });

            res.json({ paper: paperResults[0], insights: insightsResults[0] || null });
        });
    });
};