const express = require('express');
const router = express.Router();
const db = require('../config/db');
const { attachUser, getDepartmentFilterForRequest } = require('../middleware/authMiddleware');

// Apply attachUser middleware to all insights routes
router.use(attachUser);

// Route: GET /api/insights/countries (with department + year filtering)
router.get('/countries', (req, res) => {
    const { year } = req.query;

    let deptCondition = "";
    let deptParams = [];
    try {
        if (req.user && req.user.access_level) {
            const filter = getDepartmentFilterForRequest(req, 'u');
            if (filter.conditions.length > 0) {
                deptCondition = ` AND ${filter.conditions.join(" AND ")}`;
                deptParams = filter.params;
            }
        }
    } catch (err) {
        console.error('Department filter error:', err);
        return res.status(403).json({ error: 'Access denied: ' + err.message });
    }

    let yearCondition = "";
    let yearParams = [];
    if (year && year !== 'all') {
        yearCondition = " AND YEAR(p.date) = ?";
        yearParams = [year];
    }

    const query = `
        SELECT pi.country_list FROM paper_insights pi
        JOIN papers p ON pi.doi = p.doi
        JOIN users u ON p.scopus_id = u.scopus_id
        WHERE pi.country_list IS NOT NULL
        ${deptCondition}
        ${yearCondition}
    `;

    db.query(query, [...deptParams, ...yearParams], (err, rows) => {
        if (err) {
            console.error('Error fetching country data:', err);
            return res.status(500).json({ error: 'Failed to fetch country data' });
        }

        if (!rows || rows.length === 0) return res.json([]);

        const countryCounts = {};
        rows.forEach(row => {
            const list = row.country_list;
            if (list) {
                list.split(/[|,;]/).map(c => c.trim()).filter(Boolean).forEach(country => {
                    countryCounts[country] = (countryCounts[country] || 0) + 1;
                });
            }
        });

        const formatted = Object.entries(countryCounts)
            .map(([country, count]) => ({ country, count }))
            .sort((a, b) => b.count - a.count);

        res.json(formatted);
    });
});

// Route: GET /api/insights/sdg-counts (with department + year filtering)
router.get('/sdg-counts', (req, res) => {
    const { year } = req.query;

    let deptCondition = "";
    let deptParams = [];
    try {
        if (req.user && req.user.access_level) {
            const filter = getDepartmentFilterForRequest(req, 'u');
            if (filter.conditions.length > 0) {
                deptCondition = ` AND ${filter.conditions.join(" AND ")}`;
                deptParams = filter.params;
            }
        }
    } catch (err) {
        console.error('Department filter error:', err);
        return res.status(403).json({ error: 'Access denied: ' + err.message });
    }

    let yearCondition = "";
    let yearParams = [];
    if (year && year !== 'all') {
        yearCondition = " AND YEAR(p.date) = ?";
        yearParams = [year];
    }

    const query = `
        SELECT pi.sustainable_development_goals FROM paper_insights pi
        JOIN papers p ON pi.doi = p.doi
        JOIN users u ON p.scopus_id = u.scopus_id
        WHERE pi.sustainable_development_goals IS NOT NULL
        ${deptCondition}
        ${yearCondition}
    `;

    db.query(query, [...deptParams, ...yearParams], (err, rows) => {
        if (err) {
            console.error('Error fetching SDG data:', err);
            return res.status(500).json({ error: 'Failed to fetch SDG data' });
        }

        if (!rows || rows.length === 0) return res.json({});

        const sdgCounts = {};

        rows.forEach(row => {
            const field = row.sustainable_development_goals;
            if (!field) return;

            // Split by common delimiters
            const parts = field.split(/[|,;]/).map(s => s.trim()).filter(Boolean);

            parts.forEach(part => {
                // Try to extract a number from strings like:
                // "3", "SDG 3", "SDG3", "SDG 3 - Good Health", "3 - Good Health"
                const match = part.match(/(\d+)/);
                if (!match) return; // skip if no number found

                const num = parseInt(match[1]);
                if (num < 1 || num > 17) return; // skip out-of-range numbers

                const label = `SDG ${num}`;
                sdgCounts[label] = (sdgCounts[label] || 0) + 1;
            });
        });

        res.json(sdgCounts);
    });
});

module.exports = router;