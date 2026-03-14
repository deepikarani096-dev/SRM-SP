const express = require('express');
const router = express.Router();
const mysql = require('mysql2');
const dotenv = require('dotenv');
dotenv.config();

const db = mysql.createConnection({
    host: 'localhost',
    user: 'root',
    password: '', // change if needed
    database: 'scopuss',
    port: process.env.port || 3307 // default port
});

const { attachUser, getDepartmentFilterForRequest } = require('../middleware/authMiddleware');

// SDG counts with optional department filtering (request-aware)
router.get('/sdg-count', attachUser, (req, res) => {
    // Build department filter conditions using central helper
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

    // Join paper_insights -> papers -> users so we can filter by department
    let query = `
        SELECT pi.sustainable_development_goals AS sdgs
        FROM paper_insights pi
        JOIN papers p ON pi.doi = p.doi
        JOIN users u ON p.scopus_id = u.scopus_id
    `;

    if (conditions.length) {
        query += ' WHERE ' + conditions.join(' AND ');
    }

    db.query(query, params, (err, results) => {
        if (err) return res.status(500).json({ error: err.message });

        const counts = {};

        results.forEach(row => {
            if (row.sdgs) {
                const sdgs = row.sdgs
                    .split('|')
                        .map((s) => s.trim())
                        .filter((s) => s !== '-' && s !== '');

                sdgs.forEach((sdg) => {
                    counts[sdg] = (counts[sdg] || 0) + 1;
                });
            }
        });

        res.json(counts);
    });
});

module.exports = router;
