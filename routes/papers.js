const express = require('express');
const router = express.Router();
const {
    getPaperDetails
} = require('../controllers/paperController');
const { attachUser } = require('../middleware/authMiddleware');

router.get('/paper/:doi', attachUser, getPaperDetails);

module.exports = router;
