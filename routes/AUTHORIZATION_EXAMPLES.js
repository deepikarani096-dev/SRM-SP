// Example API Route Integrations with Authorization

const express = require('express');
const router = express.Router();
const authMiddleware = require('../middleware/authMiddleware');
const db = require('../config/db');

// ============================================
// EXAMPLE 1: Admin-Only Routes
// ============================================

// Only admins can access admin panel data
router.get('/admin/dashboard', 
  authMiddleware.adminOnly, 
  (req, res) => {
    const query = 'SELECT * FROM admin_metrics';
    db.query(query, (err, results) => {
      if (err) return res.status(500).json({ error: 'Database error' });
      res.json(results);
    });
  }
);

// ============================================
// EXAMPLE 2: Faculty-Only Routes
// ============================================

// All faculty (level 2 and 3) can access
router.get('/faculty/my-data', 
  authMiddleware.facultyOnly, 
  (req, res) => {
    const userId = req.headers['user-id'];
    const query = 'SELECT * FROM users WHERE id = ?';
    db.query(query, [userId], (err, results) => {
      if (err) return res.status(500).json({ error: 'Database error' });
      res.json(results[0]);
    });
  }
);

// ============================================
// EXAMPLE 3: Specific Access Levels
// ============================================

// Admin and full-access faculty only (can access all faculty data)
router.get('/analytics/all-faculty', 
  authMiddleware.checkAccessLevel([1, 2]), 
  (req, res) => {
    const query = 'SELECT * FROM faculty_stats';
    db.query(query, (err, results) => {
      if (err) return res.status(500).json({ error: 'Database error' });
      res.json(results);
    });
  }
);

// ============================================
// EXAMPLE 4: Ownership Verification
// ============================================

// User can only access their own or can be unrestricted
router.get('/faculty/:facultyId/details', 
  authMiddleware.verifyOwnership((req) => req.params.facultyId), 
  (req, res) => {
    const { facultyId } = req.params;
    const query = 'SELECT * FROM users WHERE faculty_id = ?';
    db.query(query, [facultyId], (err, results) => {
      if (err) return res.status(500).json({ error: 'Database error' });
      res.json(results[0]);
    });
  }
);

// ============================================
// EXAMPLE 5: Custom Authorization Logic
// ============================================

router.get('/faculty/:facultyId/papers', 
  (req, res, next) => {
    const accessLevel = parseInt(req.headers['access-level'] || 0);
    const userFacultyId = req.headers['faculty-id'];
    const requestedFacultyId = req.params.facultyId;

    // Admin can access any
    if (accessLevel === 1) return next();
    
    // Full-access faculty can access any
    if (accessLevel === 2) return next();
    
    // Restricted faculty can only access own
    if (accessLevel === 3 && userFacultyId === requestedFacultyId) return next();
    
    return res.status(403).json({ 
      error: 'You can only access your own faculty data' 
    });
  },
  (req, res) => {
    const { facultyId } = req.params;
    const query = 'SELECT * FROM papers WHERE faculty_id = ?';
    db.query(query, [facultyId], (err, results) => {
      if (err) return res.status(500).json({ error: 'Database error' });
      res.json(results);
    });
  }
);

// ============================================
// EXAMPLE 6: Logging Access Attempts (Security)
// ============================================

router.get('/sensitive-data', 
  (req, res, next) => {
    const username = req.headers['username'];
    const accessLevel = req.headers['access-level'];
    
    // Log access attempt
    console.log(`[SECURITY] Access attempt - User: ${username}, Level: ${accessLevel}, Route: /sensitive-data`);
    
    // Continue to middleware
    authMiddleware.adminOnly(req, res, next);
  },
  (req, res) => {
    // Only admins reach here
    res.json({ data: 'Sensitive information' });
  }
);

// ============================================
// EXAMPLE 7: Multiple Authorization Checks
// ============================================

router.post('/faculty/:facultyId/publish-report', 
  (req, res, next) => {
    const accessLevel = parseInt(req.headers['access-level'] || 0);
    
    // Only admin and full-access faculty can publish
    if (accessLevel === 1 || accessLevel === 2) {
      return next();
    }
    
    return res.status(403).json({ 
      error: 'Only admins and full-access faculty can publish reports' 
    });
  },
  (req, res) => {
    const { facultyId } = req.params;
    
    // Create and publish report
    const query = 'UPDATE reports SET published = 1 WHERE faculty_id = ?';
    db.query(query, [facultyId], (err) => {
      if (err) return res.status(500).json({ error: 'Database error' });
      res.json({ success: true, message: 'Report published' });
    });
  }
);

// ============================================
// EXAMPLE 8: Conditional Data Filtering
// ============================================

router.get('/authors', (req, res) => {
  const accessLevel = parseInt(req.headers['access-level'] || 0);
  const userFacultyId = req.headers['faculty-id'];

  let query = 'SELECT id, faculty_id, faculty_name, email, docs_count, citations FROM users';
  let params = [];

  // Level 3 (restricted faculty) only sees their own data
  if (accessLevel === 3) {
    query += ' WHERE faculty_id = ?';
    params.push(userFacultyId);
  }

  db.query(query, params, (err, results) => {
    if (err) return res.status(500).json({ error: 'Database error' });
    res.json(results);
  });
});

// ============================================
// EXAMPLE 9: Frontend API Call with Headers
// ============================================

/*
// In React component:
import { useAuth } from '../contexts/AuthContext';

function MyComponent() {
  const { user } = useAuth();

  const fetchData = async () => {
    const response = await fetch('http://localhost:5001/api/faculty/all', {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        'access-level': user?.accessLevel.toString(),
        'faculty-id': user?.facultyId || '',
        'username': user?.username || '',
      },
    });
    
    const data = await response.json();
    console.log(data);
  };

  return <button onClick={fetchData}>Fetch Data</button>;
}
*/

// ============================================
// EXAMPLE 10: Error Handling
// ============================================

router.get('/protected-resource', 
  authMiddleware.checkAccessLevel([1, 2]),
  (req, res) => {
    try {
      const query = 'SELECT * FROM protected_data';
      db.query(query, (err, results) => {
        if (err) {
          console.error('Database error:', err);
          return res.status(500).json({ 
            error: 'Database error',
            message: err.message 
          });
        }
        
        res.json({
          success: true,
          data: results
        });
      });
    } catch (error) {
      console.error('Unexpected error:', error);
      res.status(500).json({ 
        error: 'Internal server error',
        message: error.message 
      });
    }
  }
);

module.exports = router;

/*
============================================
INTEGRATION CHECKLIST
============================================

1. Replace existing routes with protected versions
2. Add access-level header to all client requests
3. Update frontend API calls to include auth headers
4. Test each access level scenario
5. Monitor logs for unauthorized access attempts
6. Consider adding audit logging
7. Review and update database user access_level values
8. Test restricted faculty can only see own data
9. Verify admin has full access
10. Test edge cases and error scenarios

============================================
SECURITY BEST PRACTICES
============================================

✓ Always validate access level on backend
✓ Never trust client-side authorization alone
✓ Use HTTPS in production
✓ Log all access attempts
✓ Implement rate limiting
✓ Use JWT tokens (future enhancement)
✓ Hash passwords in database
✓ Add session timeout
✓ Implement CSRF protection
✓ Regular security audits

============================================
*/
