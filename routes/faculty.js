const express = require('express');
const router = express.Router();
const {
    getAllFaculty,
    getFacultyPaperStats,
    getFacultyDetails,
    getFacultyQuartileSummary,
    getFacultyTypeCount,
    getCriteriaFilteredFaculty,
    getAuthorList,
    getAuthorPerformance,
    getScopusChart,
    getScopusChartForFaculty,
    getFacultyCountryStats,
    getFacultyCountryStatsByYear,
    exportFacultyPapersIEEE,
    getQuartileReport,
    getQuartileSummaryStats,
    getAvailableDomains,
    getFacultyPublicationTypesList
    // NOTE: getPublicationPapers is NOT here — it lives in statsController
    //       and is served at GET /api/publication-papers (via publications route)
} = require('../controllers/facultyController');
const { attachUser } = require('../middleware/authMiddleware');

router.use(attachUser);

router.use((req, res, next) => {
    console.log('Faculty route hit:', req.method, req.url);
    next();
});

// ── Named routes BEFORE parameterised ones ───────────────────────────────────
router.get('/quartile-report/data', getQuartileReport);
router.get('/quartile-report/summary-stats', getQuartileSummaryStats);
router.get('/publication-types/list', getFacultyPublicationTypesList);
router.get('/available-domains', getAvailableDomains);

router.get('/author-list', getAuthorList);

router.get('/author-performance/:scopus_id', (req, res) => {
    console.log('Author performance route hit with scopus_id:', req.params.scopus_id);
    getAuthorPerformance(req, res);
});
router.get('/:facultyId/author-performance', (req, res) => {
    console.log('Author performance route hit for facultyId:', req.params.facultyId);
    getAuthorPerformance(req, res);
});

router.get('/scopus-chart/:scopus_id', (req, res) => {
    console.log('Scopus chart route hit for scopus_id:', req.params.scopus_id);
    getScopusChart(req, res);
});
router.get('/:facultyId/scopus-chart', (req, res) => {
    console.log('Scopus chart route hit for facultyId:', req.params.facultyId);
    getScopusChartForFaculty(req, res);
});

// ── Collection routes ────────────────────────────────────────────────────────
router.get('/', getAllFaculty);
router.get('/papers', getFacultyPaperStats);
router.get('/criteria-filter', getCriteriaFilteredFaculty);

// ── Faculty-scoped sub-resource routes ──────────────────────────────────────
router.get('/:facultyId/type-count', getFacultyTypeCount);
router.get('/:facultyId/quartile-summary', getFacultyQuartileSummary);

router.get('/:facultyId/country-stats', getFacultyCountryStats);
router.get('/faculty/:facultyId/country-stats-by-year', getFacultyCountryStatsByYear);

// ── Papers export ──────────────────────────────────────────────────────────
router.get('/papers-ieee/export', exportFacultyPapersIEEE);

// ── Faculty detail — must be LAST ────────────────────────────────────────────
router.get('/:facultyId', (req, res) => {
    console.log('Faculty detail route hit with id:', req.params.facultyId);
    getFacultyDetails(req, res);
});

module.exports = router;
