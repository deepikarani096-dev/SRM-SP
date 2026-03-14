import time
import os
import json
import sys
import pandas as pd
import re
import mysql.connector
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


def log_progress(status, message="", processed=0, total=0, progress=0, **kwargs):
    """Log progress in JSON format for the Express server."""
    progress_data = {
        "status": status,
        "message": message,
        "processed": processed,
        "total": total,
        "progress": progress,
        **kwargs
    }
    print(json.dumps(progress_data), flush=True)
    sys.stdout.flush()


def setup_database_connection(host='localhost', user='root', password='', database='scopus', port=3306):
    """Setup MySQL database connection and ensure citation_count and h_index columns exist."""
    try:
        conn = mysql.connector.connect(
            host=host,
            user=user,
            password=password,
            database=database,
            port=port
        )
        cursor = conn.cursor()
        
        # Add citation_count column if it doesn't exist
        try:
            cursor.execute("""
                ALTER TABLE users
                ADD COLUMN citation_count INT DEFAULT 0
            """)
            conn.commit()
            log_progress("DATABASE_SETUP", "Added citation_count column to database")
        except mysql.connector.errors.ProgrammingError:
            pass  # Column already exists
        
        # Add h_index column if it doesn't exist
        try:
            cursor.execute("""
                ALTER TABLE users
                ADD COLUMN h_index INT DEFAULT 0
            """)
            conn.commit()
            log_progress("DATABASE_SETUP", "Added h_index column to database")
        except mysql.connector.errors.ProgrammingError:
            pass  # Column already exists
        
        log_progress("DATABASE_CONNECTED", "Successfully connected to database")
        return conn, cursor
    
    except mysql.connector.Error as e:
        log_progress("DATABASE_ERROR", f"Database connection error: {e}")
        return None, None


def update_citation_count_in_db(cursor, conn, author_id, total_citations):
    """Update citation count in database for a specific author."""
    try:
        cursor.execute(
            "UPDATE users SET citation_count = %s WHERE scopus_id = %s",
            (total_citations, author_id)
        )
        conn.commit()
        log_progress("DATABASE_UPDATED", f"Updated database: Author {author_id} - {total_citations} citations")
        return True
    
    except mysql.connector.Error as e:
        log_progress("DATABASE_ERROR", f"Database update error for {author_id}: {e}")
        return False


def update_h_index_in_db(cursor, conn, author_id, h_index):
    """Update h_index in database for a specific author."""
    try:
        cursor.execute(
            "UPDATE users SET h_index = %s WHERE scopus_id = %s",
            (h_index, author_id)
        )
        conn.commit()
        log_progress("DATABASE_UPDATED", f"Updated database: Author {author_id} - h_index {h_index}", h_index=h_index, author_id=author_id)
        return True
    except mysql.connector.Error as e:
        log_progress("DATABASE_ERROR", f"Database update error for h_index {author_id}: {e}")
        return False


def extract_chart_data_from_svg(driver):
    """Extract document and citation data directly from the SVG elements in the chart."""
    log_progress("EXTRACTING_DATA", "Extracting data from SVG elements...")
    
    data = {
        'years': [],
        'documents': [],
        'citations': []
    }
    
    try:
        # Extract document data (bar chart)
        document_points = driver.find_elements(By.CSS_SELECTOR, ".highcharts-series-0.highcharts-column-series .highcharts-point")
        
        if document_points:
            log_progress("DATA_FOUND", f"Found {len(document_points)} document data points")
            
            for point in document_points:
                aria_label = point.get_attribute("aria-label")
                if aria_label:
                    match = re.search(r"(\d{4}), (\d+)\. Documents\.", aria_label)
                    if match:
                        year = match.group(1)
                        count = match.group(2)
                        data['years'].append(year)
                        data['documents'].append(int(count))
        
        # Extract citation data (line chart)
        citation_points = driver.find_elements(By.CSS_SELECTOR, ".highcharts-series-1.highcharts-line-series .highcharts-point")
        
        if citation_points:
            log_progress("CITATIONS_FOUND", f"Found {len(citation_points)} citation data points")
            
            citations_by_year = {}
            
            for point in citation_points:
                aria_label = point.get_attribute("aria-label")
                if aria_label:
                    match = re.search(r"(\d{4}), (\d+)\. Citations\.", aria_label)
                    if match:
                        year = match.group(1)
                        count = match.group(2)
                        citations_by_year[year] = int(count)
        
        # Combine data for all years
        if data['years']:
            unique_years = sorted(set(data['years']) | set(citations_by_year.keys()))
            
            complete_data = {
                'years': unique_years,
                'documents': [],
                'citations': []
            }
            
            doc_by_year = {year: doc for year, doc in zip(data['years'], data['documents'])}
            
            for year in unique_years:
                complete_data['documents'].append(doc_by_year.get(year, 0))
                complete_data['citations'].append(citations_by_year.get(year, 0))
            
            return complete_data
        elif citations_by_year:
            sorted_years = sorted(citations_by_year.keys())
            data['years'] = sorted_years
            data['documents'] = [0] * len(sorted_years)
            data['citations'] = [citations_by_year[year] for year in sorted_years]
            return data
        
        return data
    
    except Exception as e:
        log_progress("EXTRACTION_ERROR", f"Error extracting data from SVG: {str(e)}")
        return None


def extract_metrics_data(driver):
    """Extract h-index, document count, and citation count."""
    metrics_data = {}
    
    try:
        # Try to extract using data-testid spans (Scopus UI)
        spans = driver.find_elements(By.CSS_SELECTOR, "span[data-testid='unclickable-count']")
        if spans and len(spans) >= 3:
            # Usually: [citations, documents, h-index]
            metrics_data["citations"] = spans[0].text.strip()
            metrics_data["documents"] = spans[1].text.strip()
            metrics_data["h_index"] = spans[2].text.strip()
            log_progress("METRIC_FOUND", f"Found metrics via spans: citations={metrics_data['citations']}, documents={metrics_data['documents']}, h_index={metrics_data['h_index']}")
            return metrics_data

        # Fallback to regex if spans not found
        metric_patterns = {
            "h_index": [r"h-index: (\d+)", r"H-index: (\d+)"],
            "documents": [r"Documents: (\d+)", r"Total documents: (\d+)"],
            "citations": [r"Citations: (\d+)", r"Total citations: (\d+)"]
        }
        
        page_text = driver.find_element(By.TAG_NAME, "body").text
        
        for metric_name, patterns in metric_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, page_text)
                if match:
                    metrics_data[metric_name] = match.group(1)
                    log_progress("METRIC_FOUND", f"Found {metric_name}: {match.group(1)}")
                    break
        
        return metrics_data
    
    except Exception as e:
        log_progress("METRICS_ERROR", f"Error extracting metrics data: {str(e)}")
        return {}


def create_highcharts_dashboard(data, author_name, author_id, metrics=None):
    """Create a high-quality interactive dashboard using HighCharts HTML/JS."""
    try:
        if not data or not data.get('years'):
            print("No data available to create Highcharts dashboard")
            return False
        
        # Create the specific directory structure you want
        dashboard_dir = os.path.join('..', '..', 'Scopus', 'public', 'highcharts_dashboard')
        os.makedirs(dashboard_dir, exist_ok=True)
        
        # Convert data for JavaScript format
        years_js = json.dumps(data['years'])
        documents_js = json.dumps(data['documents'])
        citations_js = json.dumps(data['citations'])
        
        # Create metrics HTML if available
        metrics_html = ""
        if metrics:
            metrics_html = f"""
            <div class="metrics-container">
                <div class="metric-box">
                    <div class="metric-value">{metrics.get('h_index', 'N/A')}</div>
                    <div class="metric-label">H-index</div>
                </div>
                <div class="metric-box">
                    <div class="metric-value">{metrics.get('documents', 'N/A')}</div>
                    <div class="metric-label">Documents</div>
                </div>
                <div class="metric-box">
                    <div class="metric-value">{metrics.get('citations', 'N/A')}</div>
                    <div class="metric-label">Citations</div>
                </div>
            </div>
            """
        
        # Create HTML with embedded Highcharts
        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{author_name} - Scopus Metrics</title>
    <script src="https://code.highcharts.com/highcharts.js"></script>
    <script src="https://code.highcharts.com/modules/exporting.js"></script>
    <style>
        body {{ font-family: 'Helvetica Neue', Arial, sans-serif; margin: 0; padding: 20px; background-color: #f7f7f7; }}
        .dashboard-container {{ max-width: 1200px; margin: 0 auto; background-color: white; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); padding: 20px; }}
        h1 {{ color: #333; margin-top: 0; padding-bottom: 10px; border-bottom: 1px solid #eee; }}
        .chart-container {{ height: 400px; margin-bottom: 20px; }}
        .metrics-container {{ display: flex; justify-content: space-around; margin-bottom: 20px; }}
        .metric-box {{ text-align: center; background-color: #f9f9f9; border-radius: 8px; padding: 15px; width: 30%; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .metric-value {{ font-size: 36px; font-weight: bold; color: #3679e0; }}
        .metric-label {{ font-size: 14px; color: #777; margin-top: 5px; }}
    </style>
</head>
<body>
    <div class="dashboard-container">
        <h1>{author_name} - Scopus Metrics</h1>
        {metrics_html}
        <div id="chart-container" class="chart-container"></div>
    </div>
    
    <script>
        document.addEventListener('DOMContentLoaded', function() {{
            Highcharts.chart('chart-container', {{
                chart: {{ zoomType: 'xy' }},
                title: {{ text: 'Document and Citation Trends' }},
                xAxis: {{ categories: {years_js}, crosshair: true }},
                yAxis: [{{
                    title: {{ text: 'Documents', style: {{ color: '#3679e0' }} }},
                    labels: {{ style: {{ color: '#3679e0' }} }}
                }}, {{
                    title: {{ text: 'Citations', style: {{ color: '#000347' }} }},
                    labels: {{ style: {{ color: '#000347' }} }},
                    opposite: true
                }}],
                tooltip: {{ shared: true }},
                series: [{{
                    name: 'Documents', type: 'column', yAxis: 0, data: {documents_js}, color: '#3679e0'
                }}, {{
                    name: 'Citations', type: 'line', yAxis: 1, data: {citations_js}, color: '#000347'
                }}],
                credits: {{ enabled: false }}
            }});
        }});
    </script>
</body>
</html>"""
        
        # Save to your specific path structure
        filename = os.path.join(dashboard_dir, f"{author_id}_highcharts_dashboard.html")
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        log_progress("DASHBOARD_CREATED", f"Highcharts dashboard saved to: {filename}")
        return True
        
    except Exception as e:
        log_progress("DASHBOARD_ERROR", f"Error creating Highcharts dashboard: {str(e)}")
        return False


def scrape_scopus_author_metrics(author_id, db_cursor=None, db_conn=None):
    """Scrape publication and citation metrics for a Scopus author ID."""
    url = f"https://www.scopus.com/authid/detail.uri?authorId={author_id}"
    
    # Set up Chrome options
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    
    try:
        print(f"Accessing Scopus profile: {url}")
        driver.get(url)
        
        print("Waiting for page to load...")
        time.sleep(10)
        
        # Get author name
        try:
            author_name_element = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "h1, .author-profile-name"))
            )
            author_name = author_name_element.text
            print(f"Processing data for: {author_name}")
        except:
            author_name = f"Author_{author_id}"
            print("Could not retrieve author name, using ID instead")
        
        # Extract data
        chart_data = extract_chart_data_from_svg(driver)
        metrics_data = extract_metrics_data(driver)
        # Always log the extracted h-index value, even if missing
        h_index_val_log = metrics_data.get('h_index', 'N/A') if metrics_data else 'N/A'
        log_progress("H_INDEX_VALUE", f"H-index for {author_id}: {h_index_val_log}", author_id=author_id, h_index=h_index_val_log)
        
        # Calculate total citations for database update
        total_citations = 0
        if chart_data and chart_data.get('citations'):
            total_citations = sum(chart_data['citations'])
        
        # Save data
        if chart_data and (chart_data.get('documents') or chart_data.get('citations')):
            os.makedirs("scopus_data", exist_ok=True)
            
            # Save chart data
            df_data = {'Year': chart_data['years']}
            if chart_data.get('documents'):
                df_data['Documents'] = chart_data['documents']
            if chart_data.get('citations'):
                df_data['Citations'] = chart_data['citations']
            
            df = pd.DataFrame(df_data)
            filename = f"scopus_data/{author_id}_chart_data.csv"
            df.to_csv(filename, index=False)
            print(f"Chart data saved to: {filename}")
            
            # Create interactive dashboard
            create_highcharts_dashboard(chart_data, author_name, author_id, metrics_data)
        
        # Save metrics data
        if metrics_data:
            os.makedirs("scopus_data", exist_ok=True)
            
            metrics_df = pd.DataFrame({
                "Metric": [k.replace('_', ' ').title() for k in metrics_data.keys()],
                "Value": list(metrics_data.values())
            })
            
            filename = f"scopus_data/{author_id}_summary_metrics.csv"
            metrics_df.to_csv(filename, index=False)
            print(f"Summary metrics saved to: {filename}")
        
        # Update database if connection provided
        if db_cursor and db_conn:
            if total_citations > 0:
                update_citation_count_in_db(db_cursor, db_conn, author_id, total_citations)
            # Update h_index if available
            h_index_val = None
            if metrics_data and metrics_data.get('h_index'):
                try:
                    h_index_val = int(metrics_data['h_index'])
                except Exception:
                    h_index_val = None
            if h_index_val is not None:
                update_h_index_in_db(db_cursor, db_conn, author_id, h_index_val)
        
        return {
            "author_name": author_name,
            "chart_data": chart_data,
            "metrics": metrics_data,
            "total_citations": total_citations
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return None
    
    finally:
        driver.quit()


def get_scopus_ids_from_database(db_config=None):
    """Get Scopus IDs from database to process."""
    if db_config is None:
        db_config = {
            'host': 'localhost',
            'user': 'root',
            'password': '',
            'database': 'scopus',
            'port': 3306
        }
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute("SELECT scopus_id FROM users WHERE scopus_id IS NOT NULL AND scopus_id != ''")
        results = cursor.fetchall()
        scopus_ids = [str(row[0]) for row in results if row[0]]
        cursor.close()
        conn.close()
        log_progress("IDS_FETCHED", f"Retrieved {len(scopus_ids)} Scopus IDs from database")
        return scopus_ids
    except mysql.connector.Error as e:
        log_progress("DATABASE_ERROR", f"Error fetching Scopus IDs: {e}")
        return []


def process_multiple_authors(author_ids, use_database=True, db_config=None):
    """Process multiple Scopus author IDs with optional database integration."""
    all_results = []
    db_cursor = None
    db_conn = None
    total_authors = len(author_ids)
    
    log_progress("STARTED", f"Starting batch processing of {total_authors} authors", 0, total_authors, 0)
    
    # Setup database connection if requested
    if use_database:
        if db_config is None:
            db_config = {
                'host': 'localhost',
                'user': 'root',
                'password': '',  # Change this to your actual password
                'database': 'scopus',
                'port': 3306
            }
        
        db_conn, db_cursor = setup_database_connection(**db_config)
        if not db_conn:
            log_progress("DATABASE_WARNING", "Database connection failed. Continuing without database updates.")
            use_database = False
    
    try:
        for index, author_id in enumerate(author_ids):
            current_progress = int(((index) / total_authors) * 100)
            log_progress("PROCESSING", f"Processing Author ID: {author_id}", index, total_authors, current_progress, author_id=author_id)
            
            result = scrape_scopus_author_metrics(
                author_id, 
                db_cursor if use_database else None, 
                db_conn if use_database else None
            )
            if result:
                all_results.append({**result, "author_id": author_id})
                completed_progress = int(((index + 1) / total_authors) * 100)
                log_progress("AUTHOR_COMPLETE", f"Completed processing {author_id}", index + 1, total_authors, completed_progress)
            else:
                log_progress("AUTHOR_FAILED", f"Failed to process {author_id}", index + 1, total_authors)
            
            time.sleep(5)  # Delay between requests
        
        # Create summary
        if all_results:
            log_progress("CREATING_SUMMARY", "Generating summary report", total_authors, total_authors, 95)
            os.makedirs("scopus_data", exist_ok=True)
            
            summary_data = []
            for result in all_results:
                author_data = {
                    "Author Name": result.get("author_name", "Unknown"),
                    "Author ID": result.get("author_id"),
                    "H-index": result.get("metrics", {}).get("h_index", "N/A"),
                    "Total Documents": result.get("metrics", {}).get("documents", "N/A"),
                    "Total Citations": result.get("total_citations", "N/A")
                }
                summary_data.append(author_data)
            
            summary_df = pd.DataFrame(summary_data)
            filename = "scopus_data/faculty_summary.csv"
            summary_df.to_csv(filename, index=False)
            log_progress("SUMMARY_COMPLETE", f"Faculty summary saved to: {filename}", total_authors, total_authors, 100)
    
    except Exception as e:
        log_progress("PROCESS_ERROR", f"Error during batch processing: {str(e)}")
    
    finally:
        # Close database connection
        if db_cursor:
            db_cursor.close()
        if db_conn:
            db_conn.close()
            log_progress("DATABASE_CLOSED", "Database connection closed.")
    

# Main execution function for the Express server
def main():
    """Main function to run the Scopus scraper."""
    try:
        # Database configuration
        db_config = {
            'host': 'localhost',
            'user': 'root',
            'password': '',  # Update with your MySQL password
            'database': 'scopus',
            'port': 3306
        }
        
        # Get Scopus IDs from database
        scopus_ids = get_scopus_ids_from_database(db_config)
        
        if not scopus_ids:
            log_progress("NO_IDS", "No Scopus IDs found in database")
            return
        
        # Process all authors
        results = process_multiple_authors(scopus_ids, use_database=True, db_config=db_config)
        
        # Final summary
        successful_count = len(results)
        total_count = len(scopus_ids)
        
        log_progress("FINAL_COMPLETE", 
                    f"Processing complete! Successfully processed {successful_count}/{total_count} authors", 
                    total_count, total_count, 100,
                    successful=successful_count,
                    failed=total_count - successful_count)
        
    except Exception as e:
        log_progress("MAIN_ERROR", f"Critical error in main execution: {str(e)}")


# Example usage
if __name__ == "__main__":
    # Check if running from Express server or standalone
    if len(sys.argv) > 1 and sys.argv[1] == "--express":
        # Running from Express server - use database IDs
        main()
    else:
        # Running standalone - use sample IDs for testing
        scopus_ids = ["35146619400", "57226266325", "57216474980"]  # Sample IDs for testing
        
        # Database configuration
        db_config = {
            'host': 'localhost',
            'user': 'root',
            'password': '',  # Change to your MySQL password
            'database': 'scopus',
            'port': 3306
        }
        
        # Option 1: Process authors with database integration
        results = process_multiple_authors(scopus_ids, use_database=True, db_config=db_config)
        
        # Option 2: Process single author without database
        # result = scrape_scopus_author_metrics("35146619400")
        
        # Option 3: Update database from existing CSV files
        # update_existing_csv_to_database(folder_path='scopus_data', db_config=db_config)