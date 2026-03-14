const db = require('../config/db');
const { getDepartmentFilterForRequest } = require('../middleware/authMiddleware');

// GET /api/impact-analytics
// Returns department-wise and overall impact factor metrics (for journals)
exports.getImpactAnalytics = (req, res) => {
  try {
    const { conditions, params: filterParams } = getDepartmentFilterForRequest(req, 'u');
    const departmentWhere = conditions.length > 0 ? `AND ${conditions.join(' AND ')}` : '';

    const deptQuery = `
      SELECT
        COALESCE(u.department, 'Unknown') AS department,
        COUNT(DISTINCT pm.publication_name) AS journal_count,
        AVG(pm.impact_factor_2025) AS avg_if_2025,
        AVG(pm.impact_factor_5year) AS avg_if_5year,
        MAX(pm.impact_factor_2025) AS max_if_2025
      FROM papers p
      LEFT JOIN users u ON p.scopus_id = u.scopus_id
      LEFT JOIN publication_metrics pm ON p.publication_name COLLATE utf8mb4_general_ci = pm.publication_name COLLATE utf8mb4_general_ci
      WHERE p.type = 'Journal'
        ${departmentWhere}
      GROUP BY u.department
      ORDER BY avg_if_2025 DESC;
    `;

    const overallQuery = `
      SELECT
        AVG(pm.impact_factor_2025) AS avg_if_2025,
        AVG(pm.impact_factor_5year) AS avg_if_5year,
        COUNT(DISTINCT pm.publication_name) AS total_journals,
        MAX(pm.impact_factor_2025) AS max_if_2025
      FROM papers p
      LEFT JOIN publication_metrics pm ON p.publication_name COLLATE utf8mb4_general_ci = pm.publication_name COLLATE utf8mb4_general_ci
      LEFT JOIN users u ON p.scopus_id = u.scopus_id
      WHERE p.type = 'Journal'
        ${departmentWhere}
    `;

    const params = filterParams || [];

    db.query(deptQuery, params, (err, deptResults) => {
      if (err) {
        console.error('Error fetching impact analytics (dept):', err);
        return res.status(500).json({ error: 'Failed to fetch analytics' });
      }

      db.query(overallQuery, params, (err2, overallResults) => {
        if (err2) {
          console.error('Error fetching impact analytics (overall):', err2);
          return res.status(500).json({ error: 'Failed to fetch analytics' });
        }

        const overall = (overallResults && overallResults[0]) ? overallResults[0] : { avg_if_2025: null, avg_if_5year: null, total_journals: 0 };

        const deptMetrics = (deptResults || []).map(r => ({
          department: r.department,
          journal_count: r.journal_count || 0,
          avg_if_2025: r.avg_if_2025 !== null ? Number(r.avg_if_2025) : null,
          avg_if_5year: r.avg_if_5year !== null ? Number(r.avg_if_5year) : null,
          max_if_2025: r.max_if_2025 !== null ? Number(r.max_if_2025) : null
        }));

        res.json({ departments: deptMetrics, overall });
      });
    });
  } catch (err) {
    console.error('Unexpected error in getImpactAnalytics:', err);
    res.status(500).json({ error: 'Internal error' });
  }
};

// GET /api/impact-analytics/departments
// Returns distinct department list from users table
exports.getDepartments = (req, res) => {
  const query = `SELECT DISTINCT department FROM users WHERE department IS NOT NULL AND department != '' ORDER BY department ASC`;
  db.query(query, [], (err, results) => {
    if (err) {
      console.error('Error fetching departments:', err);
      return res.status(500).json({ error: 'Failed to fetch departments' });
    }
    const departments = results.map(r => r.department);
    res.json({ departments });
  });
};

// GET /api/impact-analytics/advanced
// Returns time series, distribution, top journals, top faculties, and summary stats
exports.getAdvancedAnalytics = (req, res) => {
  try {
    // department filter
    const { conditions, params: filterParams } = getDepartmentFilterForRequest(req, 'u');
    const departmentWhere = conditions.length > 0 ? `AND ${conditions.join(' AND ')}` : '';

    // Time series by year
    const tsQuery = `
      SELECT YEAR(p.date) AS year,
             AVG(pm.impact_factor_2025) AS avg_if_2025,
             COUNT(DISTINCT pm.publication_name) AS journals_count
      FROM papers p
      LEFT JOIN publication_metrics pm ON p.publication_name COLLATE utf8mb4_general_ci = pm.publication_name COLLATE utf8mb4_general_ci
      LEFT JOIN users u ON p.scopus_id = u.scopus_id
      WHERE p.type = 'Journal' AND pm.impact_factor_2025 IS NOT NULL
        ${departmentWhere}
      GROUP BY YEAR(p.date)
      ORDER BY year ASC;
    `;

    // Distribution buckets
    const distQuery = `
      SELECT bucket, COUNT(DISTINCT publication_name) AS count FROM (
        SELECT pm.publication_name,
          CASE
            WHEN pm.impact_factor_2025 < 1 THEN '0-1'
            WHEN pm.impact_factor_2025 < 2 THEN '1-2'
            WHEN pm.impact_factor_2025 < 3 THEN '2-3'
            WHEN pm.impact_factor_2025 < 4 THEN '3-4'
            WHEN pm.impact_factor_2025 < 5 THEN '4-5'
            ELSE '5+'
          END AS bucket
        FROM papers p
        LEFT JOIN publication_metrics pm ON p.publication_name COLLATE utf8mb4_general_ci = pm.publication_name COLLATE utf8mb4_general_ci
        LEFT JOIN users u ON p.scopus_id = u.scopus_id
        WHERE p.type = 'Journal' AND pm.impact_factor_2025 IS NOT NULL
        ${departmentWhere}
        GROUP BY pm.publication_name, pm.impact_factor_2025
      ) t
      GROUP BY bucket;
    `;

    // Top journals by avg IF
    const topJournalsQuery = `
      SELECT pm.publication_name, AVG(pm.impact_factor_2025) AS avg_if_2025, COUNT(*) AS occurrences
      FROM papers p
      LEFT JOIN publication_metrics pm ON p.publication_name COLLATE utf8mb4_general_ci = pm.publication_name COLLATE utf8mb4_general_ci
      LEFT JOIN users u ON p.scopus_id = u.scopus_id
      WHERE p.type = 'Journal' AND pm.impact_factor_2025 IS NOT NULL
        ${departmentWhere}
      GROUP BY pm.publication_name
      ORDER BY avg_if_2025 DESC
      LIMIT 15;
    `;

    // Top faculties by avg IF (only faculties with >=3 journal docs to avoid noise)
    const topFacultiesQuery = `
      SELECT u.faculty_id, u.faculty_name, AVG(pm.impact_factor_2025) AS avg_if_2025, COUNT(DISTINCT p.doi) AS docs
      FROM papers p
      JOIN users u ON p.scopus_id = u.scopus_id
      LEFT JOIN publication_metrics pm ON p.publication_name COLLATE utf8mb4_general_ci = pm.publication_name COLLATE utf8mb4_general_ci
      WHERE p.type = 'Journal' AND pm.impact_factor_2025 IS NOT NULL
        ${departmentWhere}
      GROUP BY u.faculty_id, u.faculty_name
      HAVING docs >= 3
      ORDER BY avg_if_2025 DESC
      LIMIT 20;
    `;

    // Summary stats
    const summaryQuery = `
      SELECT
        AVG(pm.impact_factor_2025) AS avg_if_2025,
        STDDEV_SAMP(pm.impact_factor_2025) AS stddev_if_2025,
        MIN(pm.impact_factor_2025) AS min_if_2025,
        MAX(pm.impact_factor_2025) AS max_if_2025,
        COUNT(DISTINCT pm.publication_name) AS total_journals
      FROM papers p
      LEFT JOIN publication_metrics pm ON p.publication_name COLLATE utf8mb4_general_ci = pm.publication_name COLLATE utf8mb4_general_ci
      LEFT JOIN users u ON p.scopus_id = u.scopus_id
      WHERE p.type = 'Journal' AND pm.impact_factor_2025 IS NOT NULL
        ${departmentWhere}
    `;

    const params = filterParams || [];

    // Run queries in sequence
    db.query(tsQuery, params, (err, tsResults) => {
      if (err) {
        console.error('Error fetching advanced (ts):', err);
        return res.status(500).json({ error: 'Failed' });
      }

      db.query(distQuery, params, (err2, distResults) => {
        if (err2) {
          console.error('Error fetching advanced (dist):', err2);
          return res.status(500).json({ error: 'Failed' });
        }

        db.query(topJournalsQuery, params, (err3, topJr) => {
          if (err3) {
            console.error('Error fetching advanced (top journals):', err3);
            return res.status(500).json({ error: 'Failed' });
          }

          db.query(topFacultiesQuery, params, (err4, topFac) => {
            if (err4) {
              console.error('Error fetching advanced (top faculties):', err4);
              return res.status(500).json({ error: 'Failed' });
            }

            db.query(summaryQuery, params, (err5, summaryRes) => {
              if (err5) {
                console.error('Error fetching advanced (summary):', err5);
                return res.status(500).json({ error: 'Failed' });
              }

              const summary = (summaryRes && summaryRes[0]) ? summaryRes[0] : null;

              res.json({
                timeSeries: tsResults || [],
                distribution: distResults || [],
                topJournals: topJr || [],
                topFaculties: topFac || [],
                summary: summary || {}
              });
            });
          });
        });
      });
    });
  } catch (err) {
    console.error('Unexpected error in getAdvancedAnalytics:', err);
    res.status(500).json({ error: 'Internal error' });
  }
};
