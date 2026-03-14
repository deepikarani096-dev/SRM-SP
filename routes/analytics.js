const express = require('express');
const router = express.Router();
const { attachUser } = require('../middleware/authMiddleware');
const { getImpactAnalytics, getDepartments, getAdvancedAnalytics } = require('../controllers/analyticsController');

// Attach user to request to allow department RBAC filters
router.get('/impact-analytics', attachUser, getImpactAnalytics);
router.get('/impact-analytics/departments', attachUser, getDepartments);
router.get('/impact-analytics/advanced', attachUser, getAdvancedAnalytics);

module.exports = router;
