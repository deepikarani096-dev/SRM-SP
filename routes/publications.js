const express = require('express');
const router = express.Router();
const { attachUser } = require('../middleware/authMiddleware');
const {
    getPublicationStats,
    getTopAuthor,
    getQuartileStats,
    getPublicationTypeStats,
    getImpactAnalytics,
    getPublicationPapers,   // NEW
    getPublicationMetrics,
} = require('../controllers/statsController');

// Existing routes
router.get('/publications', attachUser, getPublicationStats);
router.get('/top-author', attachUser, getTopAuthor);
router.get('/quartile-stats', attachUser, getQuartileStats);
router.get('/publication-stats', attachUser, getPublicationTypeStats);
router.get('/impact-analytics', attachUser, getImpactAnalytics);

// Summary metrics table used by Reports page
router.get('/publication-metrics', attachUser, getPublicationMetrics);

// NEW: drill-down papers for a clicked publication row
// GET /api/publication-papers?publication_name=...&type=...&year=...
router.get('/publication-papers', attachUser, getPublicationPapers);

module.exports = router;