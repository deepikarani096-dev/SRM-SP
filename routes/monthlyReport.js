const express = require('express');
const router = express.Router();
const monthlyReportController = require('../controllers/monthlyReportController');
const { attachUser } = require('../middleware/authMiddleware');

// Routes for monthly reports (attachUser to enforce RBAC)
router.get('/monthly-report', attachUser, monthlyReportController.getAllMonthlyReports);
router.get('/monthly-report-with-papers', attachUser, monthlyReportController.getAllMonthlyReportsWithPapers);

module.exports = router;