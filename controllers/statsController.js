const db = require('../config/db');
const { getDepartmentFilterForRequest } = require('../middleware/authMiddleware');

// ---------- 1. Publication Stats (Timeframe-based) ----------
exports.getPublicationStats = (req, res) => {
  const { timeframe } = req.query;

  let interval;
  if (timeframe === '6m') interval = '6 MONTH';
  else if (timeframe === '1y') interval = '1 YEAR';
  else if (timeframe === '2y') interval = '2 YEAR';
  else return res.status(400).json({ error: 'Invalid timeframe' });

  const { conditions, params: filterParams } = getDepartmentFilterForRequest(req, 'u');
  const departmentFilter = conditions.length > 0 ? `AND ${conditions.join(' AND ')}` : '';

  const query = `
    SELECT DATE_FORMAT(p.date, '%Y-%m') AS month, COUNT(*) AS count
    FROM papers p
    LEFT JOIN users u ON p.scopus_id = u.scopus_id
    WHERE p.date >= DATE_SUB(CURDATE(), INTERVAL ${interval})
      AND p.date <= CURDATE()
      ${departmentFilter}
    GROUP BY month
    ORDER BY month ASC;
  `;

  db.query(query, filterParams, (err, results) => {
    if (err) {
      console.error(err);
      return res.status(500).json({ error: 'Failed to fetch data' });
    }
    res.json(results);
  });
};

// ---------- 2. Top Faculty ----------
exports.getTopAuthor = (req, res) => {
  const { timeframe } = req.query;

  let interval;
  if (timeframe === '6m') interval = '6 MONTH';
  else if (timeframe === '1y') interval = '1 YEAR';
  else if (timeframe === '2y') interval = '2 YEAR';
  else return res.status(400).json({ error: 'Invalid timeframe' });

  const { conditions, params: filterParams } = getDepartmentFilterForRequest(req, 'u');
  const departmentWhere = conditions.length > 0 ? `AND ${conditions.join(' AND ')}` : '';

  const weightedSubquery = `
SELECT 
  u.faculty_id,
  u.faculty_name,

  COUNT(p.id) AS total_papers,

  -- TYPE BREAKDOWN
  SUM(CASE WHEN p.type = 'Journal' THEN 1 ELSE 0 END) AS journal_count,
  SUM(CASE WHEN p.type = 'Conference Proceeding' THEN 1 ELSE 0 END) AS conference_count,
  SUM(CASE WHEN p.type = 'Book' THEN 1 ELSE 0 END) AS book_count,

  -- QUARTILE BREAKDOWN
  SUM(CASE WHEN COALESCE(fqs.quartile_2024, fqs.quartile_2023, fqs.quartile_2022, p.quartile) = 'Q1' THEN 1 ELSE 0 END) AS q1_count,
  SUM(CASE WHEN COALESCE(fqs.quartile_2024, fqs.quartile_2023, fqs.quartile_2022, p.quartile) = 'Q2' THEN 1 ELSE 0 END) AS q2_count,
  SUM(CASE WHEN COALESCE(fqs.quartile_2024, fqs.quartile_2023, fqs.quartile_2022, p.quartile) = 'Q3' THEN 1 ELSE 0 END) AS q3_count,
  SUM(CASE WHEN COALESCE(fqs.quartile_2024, fqs.quartile_2023, fqs.quartile_2022, p.quartile) = 'Q4' THEN 1 ELSE 0 END) AS q4_count,

  -- IMPACT BREAKDOWN
  SUM(CASE WHEN pm.impact_factor_2025 > 7 THEN 1 ELSE 0 END) AS high_if_count,
  SUM(CASE WHEN pm.impact_factor_2025 BETWEEN 3 AND 7 THEN 1 ELSE 0 END) AS mid_if_count,

  -- FINAL SCORE
  SUM(
    CASE 
      WHEN p.type = 'Journal' THEN 3
      WHEN p.type = 'Book' THEN 2
      WHEN p.type = 'Conference Proceeding' THEN 1
      ELSE 1
    END
    +
    CASE 
      WHEN COALESCE(fqs.quartile_2024, fqs.quartile_2023, fqs.quartile_2022, p.quartile) = 'Q1' THEN 4
      WHEN COALESCE(fqs.quartile_2024, fqs.quartile_2023, fqs.quartile_2022, p.quartile) = 'Q2' THEN 3
      WHEN COALESCE(fqs.quartile_2024, fqs.quartile_2023, fqs.quartile_2022, p.quartile) = 'Q3' THEN 2
      WHEN COALESCE(fqs.quartile_2024, fqs.quartile_2023, fqs.quartile_2022, p.quartile) = 'Q4' THEN 1
      ELSE 0
    END
    +
    CASE 
      WHEN pm.impact_factor_2025 > 7 THEN 5
      WHEN pm.impact_factor_2025 BETWEEN 3 AND 7 THEN 3
      WHEN pm.impact_factor_2025 IS NOT NULL THEN 1
      ELSE 0
    END
  ) AS total_score

FROM users u
JOIN papers p ON u.scopus_id = p.scopus_id
LEFT JOIN faculty_quartile_summary fqs ON p.doi = fqs.doi
LEFT JOIN publication_metrics pm 
  ON p.publication_name COLLATE utf8mb4_general_ci 
   = pm.publication_name COLLATE utf8mb4_general_ci

WHERE p.date >= DATE_SUB(CURDATE(), INTERVAL ${interval})
  AND p.date <= CURDATE()
  ${departmentWhere}

GROUP BY u.faculty_id, u.faculty_name
  `;

  const finalQuery = `
    SELECT * FROM (
      ${weightedSubquery}
    ) t
    WHERE t.total_score = (
      SELECT MAX(t2.total_score) FROM (
        ${weightedSubquery}
      ) t2
    )
  `;

  const params = [...filterParams, ...filterParams];

  db.query(finalQuery, params, (err, results) => {
    if (err) {
      console.error("Top Author Error:", err);
      return res.status(500).json({ error: 'Failed to fetch top author' });
    }

    res.json(results);
  });
};

// ---------- 3. Quartile Stats ----------
exports.getQuartileStats = (req, res) => {
  const { year } = req.query;

  const { conditions, params: filterParams } = getDepartmentFilterForRequest(req, 'u');
  const departmentJoin = conditions.length > 0
    ? `INNER JOIN users u ON fqs.scopus_id = u.scopus_id AND ${conditions.join(' AND ')}`
    : '';

  const mapCase = (col) => `
    CASE 
      WHEN UPPER(TRIM(${col})) IN ('1','Q1') THEN 'Q1'
      WHEN UPPER(TRIM(${col})) IN ('2','Q2') THEN 'Q2'
      WHEN UPPER(TRIM(${col})) IN ('3','Q3') THEN 'Q3'
      WHEN UPPER(TRIM(${col})) IN ('4','Q4') THEN 'Q4'
      ELSE NULL
    END
  `;

  let query = '';

  if (year === '2022' || year === '2023' || year === '2024') {
    const column = `quartile_${year}`;
    query = `
      SELECT ${mapCase(column)} AS quartile, COUNT(*) AS count
      FROM faculty_quartile_summary fqs
      ${departmentJoin}
      WHERE ${column} IS NOT NULL AND ${column} != ''
      GROUP BY quartile;
    `;
  } else {
    query = `
      SELECT quartile, COUNT(*) AS count FROM (
        SELECT ${mapCase('quartile_2022')} AS quartile
        FROM faculty_quartile_summary fqs
        ${departmentJoin}
        WHERE quartile_2022 IS NOT NULL AND quartile_2022 != ''

        UNION ALL

        SELECT ${mapCase('quartile_2023')}
        FROM faculty_quartile_summary fqs
        ${departmentJoin}
        WHERE quartile_2023 IS NOT NULL AND quartile_2023 != ''

        UNION ALL

        SELECT ${mapCase('quartile_2024')}
        FROM faculty_quartile_summary fqs
        ${departmentJoin}
        WHERE quartile_2024 IS NOT NULL AND quartile_2024 != ''
      ) t
      WHERE quartile IS NOT NULL
      GROUP BY quartile;
    `;
  }

  let paramsForQuartile = [];
  if (filterParams && filterParams.length > 0) {
    const repeatCount = (year === '2022' || year === '2023' || year === '2024') ? 1 : 3;
    for (let i = 0; i < repeatCount; i++) paramsForQuartile.push(...filterParams);
  }

  db.query(query, paramsForQuartile, (err, results) => {
    if (err) {
      console.error(err);
      return res.status(500).json({ error: 'Failed to fetch quartile stats' });
    }

    const quartiles = { Q1: 0, Q2: 0, Q3: 0, Q4: 0 };
    results.forEach(r => {
      if (quartiles[r.quartile] !== undefined) {
        quartiles[r.quartile] = r.count;
      }
    });

    res.json(quartiles);
  });
};

// ---------- 4. Publication Type Stats (Journal/Conference/Book) with Year Filter ----------
exports.getPublicationTypeStats = (req, res) => {
  const { type, year } = req.query;

  const validTypes = ['Journal', 'Conference Proceeding', 'Book'];

  if (type && type !== 'all' && !validTypes.includes(type)) {
    return res.status(400).json({
      error: 'Invalid type parameter. Must be "Journal", "Conference Proceeding", "Book", or omit for all types'
    });
  }

  const { conditions, params: filterParams } = getDepartmentFilterForRequest(req, 'u');
  const departmentConditions = conditions.length > 0 ? `${conditions.join(' AND ')}` : '';

  let params = [];
  let whereConditions = [];

  if (type && type !== 'all') {
    whereConditions.push('p.type = ?');
    params.push(type);
  }

  if (year && year !== 'all') {
    whereConditions.push('YEAR(p.date) = ?');
    params.push(year);
  }

  let whereClause = '';
  if (whereConditions.length > 0) {
    whereClause = 'WHERE ' + whereConditions.join(' AND ');
    if (departmentConditions) whereClause += ' AND ' + departmentConditions;
  } else if (departmentConditions) {
    whereClause = 'WHERE ' + departmentConditions;
  }

  const query = `
    SELECT 
      p.publication_name,
      p.type,
      COUNT(DISTINCT p.doi) as count,
      pm.impact_factor_2025,
      pm.impact_factor_5year
    FROM papers p
    LEFT JOIN users u ON p.scopus_id = u.scopus_id
    LEFT JOIN publication_metrics pm ON p.publication_name COLLATE utf8mb4_general_ci = pm.publication_name COLLATE utf8mb4_general_ci
    ${whereClause}
    GROUP BY p.publication_name, p.type, pm.impact_factor_2025, pm.impact_factor_5year
    ORDER BY count DESC, p.publication_name ASC
  `;

  if (filterParams && filterParams.length > 0) {
    params.push(...filterParams);
  }

  db.query(query, params, (err, results) => {
    if (err) {
      console.error('Error fetching publication type statistics:', err);
      return res.status(500).json({ error: 'Database error' });
    }
    res.json(results);
  });
};

// ---------- 5. Impact Analytics (department-wise + overall) ----------
exports.getImpactAnalytics = (req, res) => {
  const { conditions, params: filterParams } = getDepartmentFilterForRequest(req, 'u');
  const departmentConditions = conditions.length > 0 ? `${conditions.join(' AND ')}` : '';

  const query = `
    SELECT
      COALESCE(u.department, 'Unknown') AS department,
      COUNT(DISTINCT pm.publication_name) AS journal_count,
      AVG(pm.impact_factor_2025) AS avg_if_2025,
      AVG(pm.impact_factor_5year) AS avg_if_5year,
      MAX(pm.impact_factor_2025) AS max_if_2025
    FROM papers p
    LEFT JOIN users u ON p.scopus_id = u.scopus_id
    LEFT JOIN publication_metrics pm ON p.publication_name COLLATE utf8mb4_general_ci = pm.publication_name COLLATE utf8mb4_general_ci
    WHERE p.type = 'Journal' AND pm.impact_factor_2025 IS NOT NULL
    ${departmentConditions ? 'AND ' + departmentConditions : ''}
    GROUP BY u.department
    ORDER BY avg_if_2025 DESC;
  `;

  const params = filterParams && filterParams.length ? [...filterParams] : [];

  db.query(query, params, (err, results) => {
    if (err) {
      console.error('Error fetching impact analytics:', err);
      return res.status(500).json({ error: 'Database error' });
    }

    const overall = results.reduce(
      (acc, r) => {
        acc.journal_count += Number(r.journal_count || 0);
        acc.sum_if_2025 += Number(r.avg_if_2025 || 0) * Number(r.journal_count || 0);
        acc.sum_if_5yr += Number(r.avg_if_5year || 0) * Number(r.journal_count || 0);
        if (r.max_if_2025 && r.max_if_2025 > acc.max_if_2025) acc.max_if_2025 = Number(r.max_if_2025);
        return acc;
      },
      { journal_count: 0, sum_if_2025: 0, sum_if_5yr: 0, max_if_2025: 0 }
    );

    const overallSummary = {
      avg_if_2025: overall.journal_count ? +(overall.sum_if_2025 / overall.journal_count).toFixed(2) : null,
      avg_if_5year: overall.journal_count ? +(overall.sum_if_5yr / overall.journal_count).toFixed(2) : null,
      max_if_2025: overall.max_if_2025 || null,
      total_journals: overall.journal_count
    };

    res.json({ departments: results, overall: overallSummary });
  });
};

// ---------- 6. Publication Papers (drill-down by publication name) ----------
// GET /api/publication-papers?publication_name=...&type=...&year=...&department=...
exports.getPublicationPapers = (req, res) => {
  const { publication_name, type, year } = req.query;

  if (!publication_name) {
    return res.status(400).json({ error: 'publication_name is required' });
  }

  // Use the same department filter pattern as every other function in this file
  const { conditions, params: filterParams } = getDepartmentFilterForRequest(req, 'u');
  const hasDeptFilter = conditions.length > 0;

  let query;
  let params = [publication_name];

  if (hasDeptFilter) {
    // JOIN users so the department filter can apply
    query = `
      SELECT DISTINCT
        p.id,
        p.doi,
        p.title,
        p.type,
        p.publication_name,
        p.date,
        p.quartile,
        p.author1,
        p.author2,
        p.author3,
        p.author4,
        p.author5,
        p.author6,
        p.affiliation1,
        p.affiliation2,
        p.affiliation3
      FROM papers p
      INNER JOIN users u ON u.scopus_id = p.scopus_id
      WHERE p.publication_name = ?
        AND ${conditions.join(' AND ')}
    `;
    params.push(...filterParams);
  } else {
    query = `
      SELECT
        p.id,
        p.doi,
        p.title,
        p.type,
        p.publication_name,
        p.date,
        p.quartile,
        p.author1,
        p.author2,
        p.author3,
        p.author4,
        p.author5,
        p.author6,
        p.affiliation1,
        p.affiliation2,
        p.affiliation3
      FROM papers p
      WHERE p.publication_name = ?
    `;
  }

  // Type filter
  if (type && type !== 'all') {
    query += ` AND p.type = ?`;
    params.push(type);
  }

  // Year filter
  if (year && year !== 'all') {
    const yearNum = parseInt(year);
    if (!isNaN(yearNum)) {
      query += ` AND YEAR(p.date) = ?`;
      params.push(yearNum);
    }
  }

  query += ` ORDER BY p.date DESC`;

  db.query(query, params, (err, results) => {
    if (err) {
      console.error('Publication papers fetch error:', err);
      return res.status(500).json({ error: 'Failed to fetch papers' });
    }
    res.json(results);
  });
};

// ---------- 7. Publication Metrics Summary (institution level) ----------
exports.getPublicationMetrics = (req, res) => {
  const { start_date, end_date } = req.query;

  const now = new Date();
  const currentYear = now.getFullYear();
  const reportYear = currentYear;

  const defaultStart = `${reportYear}-01-01`;
  const defaultEnd = now.toISOString().slice(0, 10);
  const start = start_date || defaultStart;
  const end = end_date || defaultEnd;

  // Previous month range (for metric 4)
  const firstOfThisMonth = new Date(now.getFullYear(), now.getMonth(), 1);
  const lastOfPrevMonth = new Date(firstOfThisMonth - 1);
  const firstOfPrevMonth = new Date(lastOfPrevMonth.getFullYear(), lastOfPrevMonth.getMonth(), 1);
  const prevMonthStart = firstOfPrevMonth.toISOString().slice(0, 10);
  const prevMonthEnd = lastOfPrevMonth.toISOString().slice(0, 10);
  const prevMonthLabel = firstOfPrevMonth.toLocaleString('default', { month: 'long', year: 'numeric' });

  const accessLevel = req.user && req.user.access_level ? Number(req.user.access_level) : 1;
  const userDept = req.user && req.user.department ? req.user.department : null;

  const runQuery = (sql, params) => new Promise((resolve, reject) => {
    db.query(sql, params || [], (err, rows) => {
      if (err) return reject(err);
      resolve(rows);
    });
  });

  // ── Helper: compute citation index (citations / total_pubs), null if no pubs
  const calcCitationIndex = (citations, totalPubs) => {
    if (!totalPubs || totalPubs === 0) return null;
    return parseFloat((citations / totalPubs).toFixed(2));
  };

  (async () => {
    try {
      // ── Overall metrics ────────────────────────────────────────────────────
      const overallQuery = `
        SELECT
          COUNT(DISTINCT p.doi)                                                         AS total_publications_all_databases,
          SUM(CASE WHEN p.type = 'Journal' THEN 1 ELSE 0 END)                          AS total_journal_papers_in_scopus,
          SUM(CASE WHEN YEAR(p.date) = ${reportYear} THEN 1 ELSE 0 END)                AS total_publications_in_year,
          SUM(CASE WHEN p.date BETWEEN ? AND ? THEN 1 ELSE 0 END)                      AS total_publications_prev_month,
          SUM(COALESCE(u.citations, 0))                                                 AS total_citations_scopus_consolidated,
          SUM(COALESCE(pm.impact_factor_2025, 0))                                      AS cumulative_impact_factor,
          NULL                                                                          AS cumulative_snip,
          NULL                                                                          AS i10_index_scopus_consolidated,
          SUM(COALESCE(u.h_index, 0))                                                   AS h_index_scopus_consolidated,
          NULL                                                                          AS h_index_wos_consolidated
        FROM users u
        LEFT JOIN papers p  ON p.scopus_id = u.scopus_id
        LEFT JOIN publication_metrics pm
          ON p.publication_name COLLATE utf8mb4_general_ci = pm.publication_name COLLATE utf8mb4_general_ci;
      `;

      const overallRows = await runQuery(overallQuery, [prevMonthStart, prevMonthEnd]);
      const overallRow = overallRows && overallRows[0] ? overallRows[0] : {};

      // ── Per-department metrics ─────────────────────────────────────────────
      const deptQuery = `
        SELECT
          COALESCE(u.department, 'Unknown')                                             AS department,
          COUNT(DISTINCT p.doi)                                                         AS total_publications_all_databases,
          SUM(CASE WHEN p.type = 'Journal' THEN 1 ELSE 0 END)                          AS total_journal_papers_in_scopus,
          SUM(CASE WHEN YEAR(p.date) = ${reportYear} THEN 1 ELSE 0 END)                AS total_publications_in_year,
          SUM(CASE WHEN p.date BETWEEN ? AND ? THEN 1 ELSE 0 END)                      AS total_publications_prev_month,
          SUM(COALESCE(u.citations, 0))                                                 AS total_citations_scopus_consolidated,
          SUM(COALESCE(pm.impact_factor_2025, 0))                                      AS cumulative_impact_factor,
          SUM(COALESCE(u.h_index, 0))                                                   AS h_index_scopus_consolidated
        FROM users u
        LEFT JOIN papers p  ON p.scopus_id = u.scopus_id
        LEFT JOIN publication_metrics pm
          ON p.publication_name COLLATE utf8mb4_general_ci = pm.publication_name COLLATE utf8mb4_general_ci
        GROUP BY u.department
        ORDER BY u.department;
      `;

      const deptRows = await runQuery(deptQuery, [prevMonthStart, prevMonthEnd]);

      // ── Shape response ─────────────────────────────────────────────────────
      const overallTotalPubs = Number(overallRow.total_publications_all_databases || 0);
      const overallTotalCites = Number(overallRow.total_citations_scopus_consolidated || 0);

      let response = {
        reporting_period_start: start,
        reporting_period_end: end,
        report_year: reportYear,
        prev_month_label: prevMonthLabel,
        overall: {
          total_publications_all_databases: overallTotalPubs,
          total_journal_papers_in_scopus: Number(overallRow.total_journal_papers_in_scopus || 0),
          total_publications_in_year: Number(overallRow.total_publications_in_year || 0),
          total_publications_prev_month: Number(overallRow.total_publications_prev_month || 0),
          total_citations_scopus_consolidated: overallTotalCites,
          // Citation index computed for overall
          citation_index_consolidated: calcCitationIndex(overallTotalCites, overallTotalPubs),
          cumulative_impact_factor: Number(overallRow.cumulative_impact_factor || 0),
          cumulative_snip: overallRow.cumulative_snip ?? null,
          i10_index_scopus_consolidated: overallRow.i10_index_scopus_consolidated ?? null,
          h_index_scopus_consolidated: Number(overallRow.h_index_scopus_consolidated || 0),
          h_index_wos_consolidated: overallRow.h_index_wos_consolidated ?? null,
        },
        departments: deptRows.map(r => {
          const deptTotalPubs = Number(r.total_publications_all_databases || 0);
          const deptTotalCites = Number(r.total_citations_scopus_consolidated || 0);
          return {
            department: r.department,
            total_publications_all_databases: deptTotalPubs,
            total_journal_papers_in_scopus: Number(r.total_journal_papers_in_scopus || 0),
            total_publications_in_year: Number(r.total_publications_in_year || 0),
            total_publications_prev_month: Number(r.total_publications_prev_month || 0),
            total_citations_scopus_consolidated: deptTotalCites,
            // Citation index computed per department
            citation_index_consolidated: calcCitationIndex(deptTotalCites, deptTotalPubs),
            cumulative_impact_factor: Number(r.cumulative_impact_factor || 0),
            h_index_scopus_consolidated: Number(r.h_index_scopus_consolidated || 0),
          };
        }),
      };

      // HoD (level 2): restrict to their department only
      if (accessLevel === 2 && userDept) {
        const deptOnly = response.departments.find(d => d.department === userDept) || null;
        response = {
          reporting_period_start: start,
          reporting_period_end: end,
          report_year: reportYear,
          prev_month_label: prevMonthLabel,
          overall: null,
          departments: deptOnly ? [deptOnly] : [],
        };
      }

      res.json(response);
    } catch (err) {
      console.error('Error computing publication metrics:', err);
      res.status(500).json({ error: 'Failed to compute metrics' });
    }
  })();
};
