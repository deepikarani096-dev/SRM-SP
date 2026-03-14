const express = require('express');
const router = express.Router();
const db = require('../config/db'); // use shared DB pool

const { attachUser, getDepartmentFilterForRequest } = require('../middleware/authMiddleware');

// SDG counts with optional department filtering (request-aware)
router.get('/sdg-count', attachUser, async (req, res) => {

    let conditions = [];
    let params = [];

    try {
        const filter = getDepartmentFilterForRequest(req, 'u');
        conditions = filter.conditions || [];
        params = filter.params || [];
    } catch (err) {
        console.error('SDG count department filter error:', err);
        return res.status(403).json({ error: 'Access denied: ' + err.message });
    }

    let query = `
        SELECT pi.sustainable_development_goals AS sdgs
        FROM paper_insights pi
        JOIN papers p ON pi.doi = p.doi
        JOIN users u ON p.scopus_id = u.scopus_id
    `;

    if (conditions.length) {
        query += ' WHERE ' + conditions.join(' AND ');
    }

    try {
        const [results] = await db.query(query, params);

        const counts = {};

        results.forEach(row => {
            if (row.sdgs) {
                const sdgs = row.sdgs
                    .split('|')
                    .map(s => s.trim())
                    .filter(s => s !== '-' && s !== '');

                sdgs.forEach(sdg => {
                    counts[sdg] = (counts[sdg] || 0) + 1;
                });
            }
        });

        res.json(counts);

    } catch (err) {
        console.error(err);
        res.status(500).json({ error: err.message });
    }
});

module.exports = router;
