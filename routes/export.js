const express = require('express');
const router = express.Router();
const exportController = require('../controllers/exportController');
const rateLimit = require('../middleware/rateLimitMiddleware');
const { attachUser } = require('../middleware/authMiddleware');

/**
 * GET /api/export/faculty-csv
 * Export faculty list to CSV with department filtering
 * Query params: sdg, domain, year (optional)
 */
router.get(
    '/faculty-csv',
    attachUser,
    rateLimit.apiLimiter,
    exportController.exportFacultyCSV
);

/**
 * GET /api/export/papers-csv
 * Export papers to CSV
 * Query params: facultyId, startDate, endDate, minQuartile, maxQuartile (optional)
 */
router.get(
    '/papers-csv',
    attachUser,
    rateLimit.apiLimiter,
    exportController.exportPapersCSV
);

/**
 * GET /api/export/faculty-report/:facultyId
 * Export detailed faculty report
 * Path param: facultyId
 */
router.get(
    '/faculty-report/:facultyId',
    attachUser,
    rateLimit.apiLimiter,
    exportController.exportFacultyReport
);

module.exports = router;
