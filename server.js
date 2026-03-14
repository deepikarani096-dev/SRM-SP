const express = require('express');
const cors = require('cors');
const bodyParser = require('body-parser');
const helmet = require('helmet');
const rateLimit = require('./middleware/rateLimitMiddleware');
const validation = require('./middleware/validationMiddleware');
const logging = require('./middleware/loggingMiddleware');

const app = express();

// Railway requires using its provided port
const PORT = process.env.PORT || 5001;

// Security middleware
app.use(helmet());

// CORS configuration
app.use(cors({
  origin: ['http://localhost:5173', 'http://localhost:3000', 'https://srm-sp-production.up.railway.app'],
  credentials: true
}));

// Body parser
app.use(bodyParser.json({ limit: '50mb' }));
app.use(bodyParser.urlencoded({ limit: '50mb', extended: true }));

// Logging middleware
app.use(logging.requestLogger);

// Routes
app.get('/', (req, res) => {
 res.json({ message: 'Backend is running' });
});
app.use('/api', require('./routes/auth'));
app.use('/api', require('./routes/publications'));
app.use('/api/faculty', require('./routes/faculty'));
app.use('/api', require('./routes/papers'));
app.use('/api/insights', require('./routes/insights'));
app.use('/api', require('./routes/sdg'));
app.use('/api', require('./routes/analytics'));
app.use('/api', require('./routes/homeStats'));
app.use('/admin', require('./routes/admin.routes'));
app.use('/api', require('./routes/monthlyReport'));
app.use('/api', require('./routes/paperFacultyRatio.routes'));
app.use('/api/search', require('./routes/search'));
app.use('/api/export', require('./routes/export'));
app.use('/api/password', require('./routes/password'));

// Test API
app.get('/api/test', (req, res) => {
  res.json({ message: 'API is working!' });
});

// Health check
app.get('/health', (req, res) => {
  res.json({
    status: 'healthy',
    timestamp: new Date().toISOString()
  });
});

// 404 handler
app.use((req, res) => {
  res.status(404).json({
    success: false,
    message: 'Route not found'
  });
});

// Global error handler
app.use((err, req, res, next) => {

  logging.errorLog(err, {
    path: req.path,
    method: req.method,
    ip: req.ip
  });

  if (err.status === 429) {
    return res.status(429).json({
      success: false,
      message: err.message || 'Too many requests'
    });
  }

  if (err.status === 400) {
    return res.status(400).json({
      success: false,
      message: err.message || 'Bad request'
    });
  }

  res.status(500).json({
    success: false,
    message: 'Internal server error',
    ...(process.env.NODE_ENV === 'development' && { error: err.message })
  });
});

// Start server
app.listen(PORT, () => {
  console.log(`🚀 Server running on port ${PORT}`);
  console.log(`📊 Environment: ${process.env.NODE_ENV || 'development'}`);
});
