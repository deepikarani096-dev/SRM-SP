import time
import os
import json
import pandas as pd
import matplotlib.pyplot as plt
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
import re

def extract_chart_data_from_svg(driver):
    """Extract document and citation data directly from the SVG elements in the chart."""
    print("Extracting data from SVG elements...")
    
    data = {
        'years': [],
        'documents': [],
        'citations': []
    }
    
    try:
        # First try to find document data (the bar chart)
        document_points = driver.find_elements(By.CSS_SELECTOR, ".highcharts-series-0.highcharts-column-series .highcharts-point")
        
        if document_points:
            print(f"Found {len(document_points)} document data points")
            
            for point in document_points:
                # Extract the year and document count from the aria-label attribute
                aria_label = point.get_attribute("aria-label")
                if aria_label:
                    # The format is typically "YYYY, N. Documents."
                    match = re.search(r"(\d{4}), (\d+)\. Documents\.", aria_label)
                    if match:
                        year = match.group(1)
                        count = match.group(2)
                        data['years'].append(year)
                        data['documents'].append(int(count))
                        print(f"Year: {year}, Documents: {count}")
        
        # Then try to find citation data (the line chart with markers)
        citation_points = driver.find_elements(By.CSS_SELECTOR, ".highcharts-series-1.highcharts-line-series .highcharts-point")
        
        if citation_points:
            print(f"Found {len(citation_points)} citation data points")
            
            citations_by_year = {}
            
            for point in citation_points:
                # Extract the year and citation count from the aria-label attribute
                aria_label = point.get_attribute("aria-label")
                if aria_label:
                    # The format is typically "YYYY, N. Citations."
                    match = re.search(r"(\d{4}), (\d+)\. Citations\.", aria_label)
                    if match:
                        year = match.group(1)
                        count = match.group(2)
                        citations_by_year[year] = int(count)
                        print(f"Year: {year}, Citations: {count}")
            
            # Add citation data in the same order as document years, or add all citation years if no document data
            if data['years']:
                # Fill in citation data for the years we have document data
                data['citations'] = [citations_by_year.get(year, 0) for year in data['years']]
            else:
                # If we have no document data, just use the citation years
                sorted_years = sorted(citations_by_year.keys())
                data['years'] = sorted_years
                data['citations'] = [citations_by_year[year] for year in sorted_years]
        
        return data
    
    except Exception as e:
        print(f"Error extracting data from SVG: {str(e)}")
        return None

def take_chart_screenshot(driver, author_id):
    """Take a screenshot of the chart container."""
    try:
        # Try to find the chart container
        chart_container_selectors = [
            ".highcharts-container",
            "#documentResultsHighchart",
            "svg.highcharts-root"
        ]
        
        for selector in chart_container_selectors:
            try:
                chart_container = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                
                # Create output directory if it doesn't exist
                if not os.path.exists("scopus_charts"):
                    os.makedirs("scopus_charts")
                
                # Take screenshot of the chart
                filename = f"scopus_charts/{author_id}_metrics_chart.png"
                chart_container.screenshot(filename)
                print(f"Chart screenshot saved to: {filename}")
                return True
            except:
                continue
        
        print("Could not find chart container for screenshot")
        return False
    
    except Exception as e:
        print(f"Error taking chart screenshot: {str(e)}")
        return False

def extract_metrics_data(driver):
    """Try to extract h-index, document count, and citation count."""
    metrics_data = {}
    
    try:
        # Look for metrics in different ways
        metric_patterns = {
            "h_index": [
                r"h-index: (\d+)",
                r"H-index: (\d+)"
            ],
            "documents": [
                r"Documents: (\d+)",
                r"Total documents: (\d+)"
            ],
            "citations": [
                r"Citations: (\d+)",
                r"Total citations: (\d+)"
            ]
        }
        
        # Get all text from the page
        page_text = driver.find_element(By.TAG_NAME, "body").text
        
        # Try to find metrics using regex patterns
        for metric_name, patterns in metric_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, page_text)
                if match:
                    metrics_data[metric_name] = match.group(1)
                    print(f"Found {metric_name}: {match.group(1)}")
                    break
        
        return metrics_data
    
    except Exception as e:
        print(f"Error extracting metrics data: {str(e)}")
        return {}

def create_metrics_chart(data, author_name, author_id):
    """Create a chart similar to Scopus from the extracted data."""
    try:
        if not data or not data.get('years'):
            print("No data available to create chart")
            return False
        
        # Create output directory if it doesn't exist
        if not os.path.exists("scopus_charts"):
            os.makedirs("scopus_charts")
        
        # Create a figure with two y-axes
        fig, ax1 = plt.subplots(figsize=(10, 6))
        ax2 = ax1.twinx()
        
        # Plot documents as bars on the left axis
        if data.get('documents'):
            ax1.bar(data['years'], data['documents'], color='#3679e0', alpha=0.7, label='Documents')
            ax1.set_ylabel('Documents', color='#3679e0')
            ax1.tick_params(axis='y', labelcolor='#3679e0')
            max_docs = max(data['documents']) if data['documents'] else 0
            ax1.set_ylim(0, max_docs * 1.2)  # Add some headroom
        
        # Plot citations as a line on the right axis
        if data.get('citations'):
            ax2.plot(data['years'], data['citations'], color='#000347', marker='o', linewidth=2, label='Citations')
            ax2.set_ylabel('Citations', color='#000347')
            ax2.tick_params(axis='y', labelcolor='#000347')
            max_cites = max(data['citations']) if data['citations'] else 0
            ax2.set_ylim(0, max_cites * 1.2)  # Add some headroom
        
        # Set title and labels
        plt.title(f"{author_name} - Document & Citation Trends")
        ax1.set_xlabel('Year')
        
        # Rotate x-axis labels for better readability
        plt.xticks(rotation=45)
        
        # Add a legend
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
        
        # Adjust layout and save
        plt.tight_layout()
        filename = f"scopus_charts/{author_id}_metrics_chart_generated.png"
        plt.savefig(filename)
        print(f"Generated chart saved to: {filename}")
        plt.close()
        
        return True
        
    except Exception as e:
        print(f"Error creating chart: {str(e)}")
        return False

def scrape_scopus_author_metrics(author_id):
    """Scrape publication and citation metrics for a Scopus author ID."""
    url = f"https://www.scopus.com/authid/detail.uri?authorId={author_id}"
    
    # Set up Chrome options
    chrome_options = Options()
    # Comment out headless for debugging - keep it visible when troubleshooting
    # chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    
    # Add User-Agent to make the request look more like a real browser
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    
    # Initialize the Chrome driver
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    
    try:
        # Load the page
        print(f"Accessing Scopus profile: {url}")
        driver.get(url)
        
        # Wait for the page to load
        print("Waiting for page to load...")
        time.sleep(10)  # Give it more time to load
        
        # Try to get author name
        try:
            author_name_element = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "h1, .author-profile-name"))
            )
            author_name = author_name_element.text
            print(f"Processing data for: {author_name}")
        except:
            author_name = f"Author_{author_id}"
            print("Could not retrieve author name, using ID instead")
        
        # Extract chart data from SVG elements
        chart_data = extract_chart_data_from_svg(driver)
        
        # Take a screenshot of the chart as backup
        take_chart_screenshot(driver, author_id)
        
        # Extract metrics data
        metrics_data = extract_metrics_data(driver)
        
        # Save the data we extracted
        if chart_data and (chart_data.get('documents') or chart_data.get('citations')):
            # Create output directory if it doesn't exist
            if not os.path.exists("scopus_data"):
                os.makedirs("scopus_data")
            
            # Create a DataFrame
            df_data = {'Year': chart_data['years']}
            
            if chart_data.get('documents'):
                df_data['Documents'] = chart_data['documents']
            
            if chart_data.get('citations'):
                df_data['Citations'] = chart_data['citations']
            
            df = pd.DataFrame(df_data)
            
            # Save to CSV
            filename = f"scopus_data/{author_id}_chart_data.csv"
            df.to_csv(filename, index=False)
            print(f"Chart data saved to: {filename}")
            
            # Create our own visualization
            create_metrics_chart(chart_data, author_name, author_id)
        
        # Save metrics data
        if metrics_data:
            # Create output directory if it doesn't exist
            if not os.path.exists("scopus_data"):
                os.makedirs("scopus_data")
            
            # Create a DataFrame
            metrics_df = pd.DataFrame({
                "Metric": [k.replace('_', ' ').title() for k in metrics_data.keys()],
                "Value": list(metrics_data.values())
            })
            
            # Save to CSV
            filename = f"scopus_data/{author_id}_summary_metrics.csv"
            metrics_df.to_csv(filename, index=False)
            print(f"Summary metrics saved to: {filename}")
        
        return {
            "author_name": author_name,
            "chart_data": chart_data,
            "metrics": metrics_data
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
    
    finally:
        # Close the browser
        driver.quit()

def process_faculty_list(file_path=None, author_ids=None):
    """Process a list of Scopus author IDs."""
    # If a file is provided, read author IDs from it
    if file_path and os.path.exists(file_path):
        with open(file_path, 'r') as f:
            author_ids = [line.strip() for line in f if line.strip()]
    
    # If author_ids were provided directly or read from a file
    if author_ids:
        all_results = []
        
        for author_id in author_ids:
            print(f"\n{'='*50}")
            print(f"Processing Author ID: {author_id}")
            print(f"{'='*50}\n")
            
            result = scrape_scopus_author_metrics(author_id)
            if result:
                all_results.append(result)
            
            # Add a delay between requests to avoid being blocked
            time.sleep(5)
        
        # Create a summary of all authors processed
        if all_results:
            # Create output directory if it doesn't exist
            if not os.path.exists("scopus_data"):
                os.makedirs("scopus_data")
            
            # Create a summary DataFrame
            summary_data = []
            for result in all_results:
                author_data = {
                    "Author Name": result.get("author_name", "Unknown"),
                    "Author ID": author_ids[all_results.index(result)],
                    "H-index": result.get("metrics", {}).get("h_index", "N/A"),
                    "Total Documents": result.get("metrics", {}).get("documents", "N/A"),
                    "Total Citations": result.get("metrics", {}).get("citations", "N/A")
                }
                summary_data.append(author_data)
            
            summary_df = pd.DataFrame(summary_data)
            
            # Save to CSV
            filename = "scopus_data/faculty_summary.csv"
            summary_df.to_csv(filename, index=False)
            print(f"\nFaculty summary saved to: {filename}")
    else:
        print("No author IDs provided. Please specify either a file path or a list of author IDs.")

# Example usage
if __name__ == "__main__":
    # Example 1: Process a single author
    scrape_scopus_author_metrics("56809436800")
    
    # Example 2: Process a list of authors
    # author_ids = [
    #     "56809436800",
    #     "57189363049",  # Add more IDs here
    # ]
    # process_faculty_list(author_ids=author_ids)
    
    # Example 3: Process authors from a file
    # process_faculty_list(file_path="faculty_scopus_ids.txt")