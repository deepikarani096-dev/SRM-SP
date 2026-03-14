from flask import Flask, render_template_string, request, jsonify
import mysql.connector
from datetime import datetime

app = Flask(__name__)

# Database config
DB_CONFIG = {
    'user': 'root',
    'password': '',
    'host': 'localhost',
    'database': 'scopuss'
}

# HTML template
HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Manual Journal Data Entry</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            background: white;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            padding: 40px;
        }
        h1 {
            color: #333;
            margin-bottom: 10px;
            font-size: 28px;
        }
        .subtitle {
            color: #666;
            margin-bottom: 30px;
            font-size: 14px;
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 15px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
        }
        .stat-number {
            font-size: 24px;
            font-weight: bold;
            color: #667eea;
        }
        .stat-label {
            font-size: 12px;
            color: #666;
            margin-top: 5px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 8px;
            color: #333;
            font-weight: 500;
            font-size: 14px;
        }
        input, select {
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 15px;
            transition: all 0.3s;
        }
        input:focus, select:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }
        .grid-2 {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
        }
        button {
            width: 100%;
            padding: 15px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s;
        }
        button:hover {
            transform: translateY(-2px);
        }
        button:active {
            transform: translateY(0);
        }
        .success {
            background: #10b981;
            color: white;
            padding: 15px;
            border-radius: 8px;
            margin-top: 20px;
            display: none;
            animation: slideIn 0.3s;
        }
        .error {
            background: #ef4444;
            color: white;
            padding: 15px;
            border-radius: 8px;
            margin-top: 20px;
            display: none;
        }
        @keyframes slideIn {
            from { opacity: 0; transform: translateY(-10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .next-journal {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            margin-top: 20px;
            border-left: 4px solid #667eea;
        }
        .next-journal strong {
            color: #667eea;
        }
        .shortcuts {
            background: #fff3cd;
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 20px;
            font-size: 13px;
            color: #856404;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Manual Journal Data Entry</h1>
        <p class="subtitle">Enter impact factor data from journalmetrics.org</p>
        
        <div class="stats">
            <div class="stat-card">
                <div class="stat-number" id="total">{{ total }}</div>
                <div class="stat-label">Total Journals</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" id="completed">{{ completed }}</div>
                <div class="stat-label">Completed</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" id="remaining">{{ remaining }}</div>
                <div class="stat-label">Remaining</div>
            </div>
        </div>

        <div class="shortcuts">
            💡 <strong>Tip:</strong> Use Tab to move between fields quickly. Press Ctrl+Enter to submit.
        </div>

        <div class="next-journal">
            <strong>Next Journal to Process:</strong><br>
            <span id="nextJournal">{{ next_journal }}</span>
        </div>

        <form id="dataForm">
            <div class="form-group">
                <label>Publication Name *</label>
                <input type="text" id="publication_name" required readonly value="{{ next_journal }}">
            </div>

            <div class="form-group">
                <label>ISSN</label>
                <input type="text" id="issn" placeholder="e.g., 2169-3536">
            </div>

            <div class="grid-2">
                <div class="form-group">
                    <label>2025 Impact Factor</label>
                    <input type="number" step="0.001" id="if_2025" placeholder="e.g., 3.6">
                </div>
                <div class="form-group">
                    <label>5-Year Impact Factor</label>
                    <input type="number" step="0.001" id="if_5year" placeholder="e.g., 3.9">
                </div>
            </div>

            <div class="grid-2">
                <div class="form-group">
                    <label>JCR Quartile</label>
                    <select id="jcr_quartile">
                        <option value="">Not Available</option>
                        <option value="Q1">Q1</option>
                        <option value="Q2">Q2</option>
                        <option value="Q3">Q3</option>
                        <option value="Q4">Q4</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>CAS Category</label>
                    <select id="cas_category">
                        <option value="">Not Available</option>
                        <option value="A1">A1</option>
                        <option value="A2">A2</option>
                        <option value="A3">A3</option>
                        <option value="B1">B1</option>
                        <option value="B2">B2</option>
                        <option value="B3">B3</option>
                        <option value="B4">B4</option>
                    </select>
                </div>
            </div>

            <button type="submit">💾 Save & Next Journal</button>
        </form>

        <button type="button" onclick="skipJournal()" style="background: #6b7280; margin-top: 10px;">
            ⏭️ Skip This Journal (No Data Available)
        </button>

        <div class="success" id="successMsg">
            ✅ Saved successfully! Loading next journal...
        </div>
        <div class="error" id="errorMsg"></div>
    </div>

    <script>
        const form = document.getElementById('dataForm');
        
        // Auto-focus first input field
        document.getElementById('issn').focus();

        // Ctrl+Enter to submit
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.key === 'Enter') {
                form.requestSubmit();
            }
        });

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const data = {
                publication_name: document.getElementById('publication_name').value,
                issn: document.getElementById('issn').value || null,
                if_2025: document.getElementById('if_2025').value || null,
                if_5year: document.getElementById('if_5year').value || null,
                jcr_quartile: document.getElementById('jcr_quartile').value || null,
                cas_category: document.getElementById('cas_category').value || null
            };

            try {
                const response = await fetch('/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });

                const result = await response.json();

                if (result.success) {
                    document.getElementById('successMsg').style.display = 'block';
                    setTimeout(() => {
                        window.location.reload();
                    }, 500);
                } else {
                    document.getElementById('errorMsg').textContent = '❌ Error: ' + result.error;
                    document.getElementById('errorMsg').style.display = 'block';
                }
            } catch (error) {
                document.getElementById('errorMsg').textContent = '❌ Network error';
                document.getElementById('errorMsg').style.display = 'block';
            }
        });

        async function skipJournal() {
            const pub_name = document.getElementById('publication_name').value;
            
            if (!confirm('Skip "' + pub_name + '"? It will be marked as not found.')) {
                return;
            }

            try {
                const response = await fetch('/skip', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ publication_name: pub_name })
                });

                const result = await response.json();

                if (result.success) {
                    document.getElementById('successMsg').textContent = '⏭️ Skipped! Loading next...';
                    document.getElementById('successMsg').style.display = 'block';
                    setTimeout(() => {
                        window.location.reload();
                    }, 500);
                } else {
                    document.getElementById('errorMsg').textContent = '❌ Error: ' + result.error;
                    document.getElementById('errorMsg').style.display = 'block';
                }
            } catch (error) {
                document.getElementById('errorMsg').textContent = '❌ Network error';
                document.getElementById('errorMsg').style.display = 'block';
            }
        }
    </script>
</body>
</html>
"""

def get_db():
    return mysql.connector.connect(**DB_CONFIG)

def create_table():
    """Create table if not exists"""
    cnx = get_db()
    cursor = cnx.cursor()
    sql = """
    CREATE TABLE IF NOT EXISTS publication_metrics (
        id INT AUTO_INCREMENT PRIMARY KEY,
        publication_name VARCHAR(500) NOT NULL UNIQUE COLLATE utf8mb4_general_ci,
        issn VARCHAR(20),
        impact_factor_2025 DECIMAL(10, 3),
        impact_factor_5year DECIMAL(10, 3),
        jcr_quartile VARCHAR(10),
        cas_category VARCHAR(10),
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        scrape_status ENUM('pending', 'success', 'failed', 'not_found') DEFAULT 'success',
        INDEX idx_publication_name (publication_name)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
    """
    cursor.execute(sql)
    cnx.commit()
    cursor.close()
    cnx.close()

def get_stats():
    """Get statistics"""
    cnx = get_db()
    cursor = cnx.cursor()
    
    # Total journals
    cursor.execute("SELECT COUNT(DISTINCT publication_name) FROM papers WHERE type='Journal'")
    total = cursor.fetchone()[0]
    
    # Completed
    cursor.execute("SELECT COUNT(*) FROM publication_metrics")
    completed = cursor.fetchone()[0]
    
    # Get last processed journal
    cursor.execute("""
        SELECT publication_name 
        FROM publication_metrics 
        ORDER BY last_updated DESC 
        LIMIT 1
    """)
    last_processed = cursor.fetchone()
    
    if last_processed:
        last_name = last_processed[0]
        
        # Get all journals in alphabetical order
        cursor.execute("""
            SELECT DISTINCT publication_name 
            FROM papers 
            WHERE type = 'Journal' 
            ORDER BY publication_name
        """)
        all_journals = [row[0] for row in cursor.fetchall()]
        
        # Find next journal after the last processed one
        try:
            last_idx = all_journals.index(last_name)
            if last_idx + 1 < len(all_journals):
                next_journal = all_journals[last_idx + 1]
            else:
                next_journal = "All Done! 🎉"
        except ValueError:
            # Last processed not in list, start from beginning
            next_journal = all_journals[0] if all_journals else "No journals found"
    else:
        # No journals processed yet, get first one
        cursor.execute("""
            SELECT DISTINCT publication_name 
            FROM papers 
            WHERE type = 'Journal' 
            ORDER BY publication_name
            LIMIT 1
        """)
        first_journal = cursor.fetchone()
        next_journal = first_journal[0] if first_journal else "No journals found"
    
    cursor.close()
    cnx.close()
    
    return {
        'total': total,
        'completed': completed,
        'remaining': total - completed,
        'next_journal': next_journal
    }

@app.route('/')
def index():
    create_table()
    stats = get_stats()
    return render_template_string(HTML, **stats)

@app.route('/save', methods=['POST'])
def save():
    try:
        data = request.json
        
        cnx = get_db()
        cursor = cnx.cursor()
        
        sql = """
        INSERT INTO publication_metrics 
        (publication_name, issn, impact_factor_2025, impact_factor_5year, 
         jcr_quartile, cas_category, scrape_status)
        VALUES (%s, %s, %s, %s, %s, %s, 'success')
        ON DUPLICATE KEY UPDATE
            issn = VALUES(issn),
            impact_factor_2025 = VALUES(impact_factor_2025),
            impact_factor_5year = VALUES(impact_factor_5year),
            jcr_quartile = VALUES(jcr_quartile),
            cas_category = VALUES(cas_category),
            last_updated = CURRENT_TIMESTAMP;
        """
        
        cursor.execute(sql, (
            data['publication_name'],
            data['issn'],
            data['if_2025'],
            data['if_5year'],
            data['jcr_quartile'],
            data['cas_category']
        ))
        
        cnx.commit()
        cursor.close()
        cnx.close()
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/skip', methods=['POST'])
def skip():
    """Mark journal as not found and skip it"""
    try:
        data = request.json
        
        cnx = get_db()
        cursor = cnx.cursor()
        
        sql = """
        INSERT INTO publication_metrics 
        (publication_name, scrape_status)
        VALUES (%s, 'not_found')
        ON DUPLICATE KEY UPDATE
            scrape_status = 'not_found',
            last_updated = CURRENT_TIMESTAMP;
        """
        
        cursor.execute(sql, (data['publication_name'],))
        
        cnx.commit()
        cursor.close()
        cnx.close()
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 MANUAL DATA ENTRY INTERFACE")
    print("="*60)
    print("\n📍 Open in browser: http://localhost:5000")
    print("\n💡 Tips:")
    print("   - Use Tab to move between fields")
    print("   - Press Ctrl+Enter to submit quickly")
    print("   - Leave fields blank if not available")
    print("\n" + "="*60 + "\n")
    
    app.run(debug=True, port=5000)