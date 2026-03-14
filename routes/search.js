const express = require('express');
const router = express.Router();
const searchController = require('../controllers/searchController');
const validation = require('../middleware/validationMiddleware');
const rateLimit = require('../middleware/rateLimitMiddleware');
const { attachUser } = require('../middleware/authMiddleware');

/**
 * GET /api/search/global
 * Global search across faculty and papers with department filtering
 * Query params: q (search query), type (faculty|papers|all)
 */
router.get(
    '/global',
    attachUser,
    validation.validateQueryParams,
    searchController.globalSearch
);

/**
 * GET /api/search/advanced
 * Advanced search with filters and department filtering
 * Query params: facultyName, scopusId, startDate, endDate, minHIndex, maxHIndex, sdg, domain
 */
router.get(
    '/advanced',
    attachUser,
    validation.validateQueryParams,
    searchController.advancedSearch
);

/**
 * GET /api/search/papers
 * Search papers by criteria
 * Query params: title, doi, scopusId, startDate, endDate, minQuartile, maxQuartile
 */
router.get(
    '/papers',
    validation.validateQueryParams,
    searchController.searchPapers
);

module.exports = router;
