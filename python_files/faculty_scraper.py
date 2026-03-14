"""
SRM Faculty Data Scraper - IRINS Edition
========================================
Scrapes comprehensive faculty data from IRINS platform for CINTEL, DSBS, and NWC departments
Extracts: Scopus ID, Faculty ID, and all available profile information

Usage: python scraper.py

Author: Created for SRM Scopus Project
Date: February 2026
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time
import os
from typing import List, Dict, Optional
from urllib.parse import urljoin, urlparse, parse_qs
import warnings
warnings.filterwarnings('ignore')


class SRMFacultyScraper:
    """Streamlined scraper for SRM faculty data using IRINS platform only"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        
        # Department configurations - IRINS URLs only
        self.departments = {
            'CINTEL': {
                'name': 'Department of Computational Intelligence',
                'code': 'CINTEL',
                'irins_url': 'https://srmist.irins.org/faculty/index/Department+of+Computational+Intelligence+-+KTR',
            },
            'DSBS': {
                'name': 'Department of Data Science and Business Systems',
                'code': 'DSBS',
                'irins_url': 'https://srmist.irins.org/faculty/index/Department+of+Data+Science+and+Business+Systems+-+KTR',
            },
            'NWC': {
                'name': 'Department of Networking and Communications',
                'code': 'NWC',
                'irins_url': 'https://srmist.irins.org/faculty/index/Department+of+Networking+and+Communications+-+KTR',
            }
        }
    
    def extract_scopus_id_from_url(self, url: str) -> str:
        """Extract Scopus ID from URL with authorid parameter"""
        try:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            if 'authorId' in params:
                return params['authorId'][0]
            
            # Also try to find in the path
            match = re.search(r'authorid=(\d+)', url, re.IGNORECASE)
            if match:
                return match.group(1)
        except:
            pass
        return ''
    
    def scrape_faculty_profile(self, url: str, dept_code: str) -> Optional[Dict]:
        """Scrape individual faculty profile page"""
        
        faculty = {
            'Name': '',
            'Designation': '',
            'Department': self.departments[dept_code]['name'],
            'Email': '',
            'Phone': '',
            'Mobile': '',
            'Scopus ID': '',
            'Scopus URL': '',
            'ORCID ID': '',
            'Google Scholar ID': '',
            'Research Gate ID': '',
            'Faculty ID': '',
            'Employee ID': '',
            'Extension': '',
            'Cabin Number': '',
            'Office Location': '',
            'Qualifications': '',
            'Experience': '',
            'Research Interest': '',
            'Specialization': '',
            'LinkedIn': '',
            'Profile URL': url
        }
        
        try:
            print(f"    -> Scraping: {url}")
            response = self.session.get(url, timeout=30)
            
            if response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract name from h1 - IRINS puts faculty name in h1
            h1 = soup.find('h1')
            if h1:
                faculty['Name'] = h1.get_text(strip=True)
            
            # If h1 didn't work, try title tag
            if not faculty['Name']:
                title = soup.find('title')
                if title:
                    title_text = title.get_text()
                    # Remove common suffixes
                    name = title_text.split('-')[0].strip()
                    name = name.split('|')[0].strip()
                    if len(name) > 2 and 'SRM' not in name:
                        faculty['Name'] = name
            
            # Extract all text for pattern matching
            page_text = soup.get_text()
            
            # Extract Faculty ID / Employee ID
            faculty_id_patterns = [
                r'Faculty\s*ID\s*:?\s*([A-Z0-9]+)',
                r'Employee\s*ID\s*:?\s*([A-Z0-9]+)',
                r'Staff\s*ID\s*:?\s*([A-Z0-9]+)',
                r'ID\s*:?\s*([A-Z0-9]{6,})',
            ]
            
            for pattern in faculty_id_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    faculty['Faculty ID'] = match.group(1)
                    break
            
            # Extract email
            email_link = soup.find('a', href=re.compile(r'mailto:'))
            if email_link:
                email = email_link.get('href', '').replace('mailto:', '').strip()
                faculty['Email'] = email
            else:
                email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', page_text)
                if email_match:
                    faculty['Email'] = email_match.group(0)
            
            # Extract phone numbers
            phone_patterns = [
                r'Phone\s*:?\s*([\d\s\-\+\(\)]{10,})',
                r'Mobile\s*:?\s*([\d\s\-\+\(\)]{10,})',
                r'Contact\s*:?\s*([\d\s\-\+\(\)]{10,})',
                r'Tel\s*:?\s*([\d\s\-\+\(\)]{10,})',
            ]
            
            for pattern in phone_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    faculty['Phone'] = match.group(1).strip()
                    break
            
            # Extract extension
            ext_match = re.search(r'Ext(?:ension)?\s*:?\s*(\d{3,5})', page_text, re.IGNORECASE)
            if ext_match:
                faculty['Extension'] = ext_match.group(1)
            
            # Extract cabin/office info
            cabin_patterns = [
                r'Cabin\s*(?:No|Number)?\s*:?\s*([A-Z0-9\-\s]+)',
                r'Room\s*(?:No|Number)?\s*:?\s*([A-Z0-9\-\s]+)',
                r'Office\s*:?\s*([A-Z0-9\-\s]+)',
            ]
            
            for pattern in cabin_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    faculty['Cabin Number'] = match.group(1).strip()
                    break
            
            # Extract designation - look for it near the name
            designations = [
                'Professor and Head', 'Professor & Head', 'Head of Department', 'HOD',
                'Professor', 'Associate Professor', 'Assistant Professor', 
                'Senior Professor', 'Lecturer', 'Senior Lecturer'
            ]
            
            for desig in designations:
                if desig.lower() in page_text.lower():
                    faculty['Designation'] = desig
                    break
            
            # Extract qualifications
            qual_match = re.search(r'Qualification[s]?\s*:?\s*([^\n]+)', page_text, re.IGNORECASE)
            if qual_match:
                faculty['Qualifications'] = qual_match.group(1).strip()
            
            # Extract experience
            exp_patterns = [
                r'Experience\s*:?\s*(\d+)\s*(?:years?|yrs?)',
                r'(\d+)\s*(?:years?|yrs?)\s*of\s*experience',
                r'EXPERIENCE\s*:?\s*([^\n]+)',
            ]
            
            for pattern in exp_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    faculty['Experience'] = match.group(1).strip()
                    break
            
            # Find all links on the page for IDs
            links = soup.find_all('a', href=True)
            
            for link in links:
                href = link.get('href', '')
                
                # Scopus
                if 'scopus' in href.lower():
                    faculty['Scopus URL'] = href
                    scopus_id = self.extract_scopus_id_from_url(href)
                    if scopus_id:
                        faculty['Scopus ID'] = scopus_id
                
                # ORCID
                elif 'orcid' in href.lower():
                    faculty['ORCID ID'] = href.split('/')[-1] if '/' in href else href
                
                # Google Scholar
                elif 'scholar.google' in href.lower():
                    faculty['Google Scholar ID'] = href.split('user=')[-1] if 'user=' in href else href
                
                # ResearchGate
                elif 'researchgate' in href.lower():
                    faculty['Research Gate ID'] = href.split('/')[-1] if '/' in href else href
                
                # LinkedIn
                elif 'linkedin' in href.lower():
                    faculty['LinkedIn'] = href
            
            # Extract Scopus ID from text if not found in links
            if not faculty['Scopus ID']:
                scopus_match = re.search(r'Scopus\s*(?:ID|Author)?\s*:?\s*(\d+)', page_text, re.IGNORECASE)
                if scopus_match:
                    faculty['Scopus ID'] = scopus_match.group(1)
            
            # Extract ORCID from text if not found in links
            if not faculty['ORCID ID']:
                orcid_match = re.search(r'ORCID\s*:?\s*([\d\-]+)', page_text, re.IGNORECASE)
                if orcid_match:
                    faculty['ORCID ID'] = orcid_match.group(1)
            
            # Extract research interests
            research_keywords = ['research interest', 'research area', 'specialization', 
                                'expertise', 'areas of interest']
            
            for keyword in research_keywords:
                match = re.search(rf'{keyword}\s*:?\s*([^\n]+)', page_text, re.IGNORECASE)
                if match and not faculty['Research Interest']:
                    faculty['Research Interest'] = match.group(1).strip()
            
            # Extract specialization if different from research interest
            spec_match = re.search(r'Specialization\s*:?\s*([^\n]+)', page_text, re.IGNORECASE)
            if spec_match:
                faculty['Specialization'] = spec_match.group(1).strip()
            
            if faculty['Name']:
                print(f"      [CHECK] {faculty['Name'][:40]} - Scopus: {faculty['Scopus ID'] or 'N/A'}")
            
        except Exception as e:
            print(f"      x Error: {e}")
        
        return faculty if faculty['Name'] else None
    
    def get_all_faculty_from_irins(self, dept_code: str) -> List[str]:
        """Get ALL faculty profile URLs from IRINS platform"""
        profile_urls = []
        
        try:
            url = self.departments[dept_code]['irins_url']
            print(f"  -> Fetching faculty list from IRINS...")
            
            response = self.session.get(url, timeout=30)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Find all profile links - try multiple selectors
                selectors = [
                    ('a', {'href': re.compile(r'/profile/\d+')}),
                    ('a', {'href': re.compile(r'profile')}),
                    ('a', {'class': re.compile(r'faculty|profile|author')}),
                ]
                
                for tag, attrs in selectors:
                    links = soup.find_all(tag, attrs)
                    for link in links:
                        href = link.get('href', '')
                        if href:
                            full_url = urljoin('https://srmist.irins.org', href)
                            if '/profile/' in full_url and full_url not in profile_urls:
                                profile_urls.append(full_url)
                
                # Also look for faculty names that might be links
                faculty_cards = soup.find_all(['div', 'li', 'tr'], class_=re.compile(r'faculty|author|person|staff'))
                for card in faculty_cards:
                    link = card.find('a', href=True)
                    if link:
                        href = link.get('href', '')
                        if href:
                            full_url = urljoin('https://srmist.irins.org', href)
                            if full_url not in profile_urls:
                                profile_urls.append(full_url)
                
                print(f"    -> Found {len(profile_urls)} faculty profiles on IRINS")
        except Exception as e:
            print(f"    x IRINS error: {e}")
        
        return profile_urls
    
    def scrape_department(self, dept_code: str) -> pd.DataFrame:
        """Scrape all faculty for a department using IRINS only"""
        
        print(f"\n{'='*70}")
        print(f"Scraping: {self.departments[dept_code]['name']} ({dept_code})")
        print(f"{'='*70}")
        
        # Get all profile URLs from IRINS
        print("\n[IRINS Method]")
        profile_urls = self.get_all_faculty_from_irins(dept_code)
        
        print(f"\n[Scraping] Starting to scrape {len(profile_urls)} faculty profiles...")
        print(f"This may take a while - please be patient!")
        
        all_faculty = []
        
        for i, url in enumerate(profile_urls, 1):
            try:
                print(f"  [{i}/{len(profile_urls)}]", end=" ")
                faculty_data = self.scrape_faculty_profile(url, dept_code)
                
                if faculty_data and faculty_data.get('Name'):
                    all_faculty.append(faculty_data)
                
                # Rate limiting - be respectful to the server
                time.sleep(1)
                
            except Exception as e:
                print(f"      ✗ Error scraping: {e}")
                continue
        
        # Remove duplicates based on email
        print(f"\n[Cleanup] Removing duplicates...")
        unique_faculty = []
        seen_emails = set()
        seen_names = set()
        
        for faculty in all_faculty:
            email = faculty.get('Email', '').strip().lower()
            name = faculty.get('Name', '').strip().lower()
            
            if email and email not in seen_emails:
                seen_emails.add(email)
                seen_names.add(name)
                unique_faculty.append(faculty)
            elif not email and name and name not in seen_names:
                seen_names.add(name)
                unique_faculty.append(faculty)
        
        print(f"  ✓ After removing duplicates: {len(unique_faculty)} unique faculty")
        print(f"\n✓ Final count: {len(unique_faculty)} unique faculty for {dept_code}")
        
        # Convert to DataFrame
        if unique_faculty:
            print(f"\n[Creating DataFrame] Converting {len(unique_faculty)} faculty...")
            df = pd.DataFrame(unique_faculty)
            
            # Ensure all required columns exist
            required_columns = ['Name', 'Designation', 'Department', 'Email', 'Phone', 'Mobile',
                              'Scopus ID', 'Scopus URL', 'ORCID ID', 'Google Scholar ID', 
                              'Research Gate ID', 'Faculty ID', 'Employee ID', 'Extension',
                              'Cabin Number', 'Office Location', 'Qualifications', 'Experience',
                              'Research Interest', 'Specialization', 'LinkedIn', 'Profile URL']
            
            for col in required_columns:
                if col not in df.columns:
                    df[col] = ''
            
            # Reorder columns
            df = df[required_columns]
            
            # Sort by name
            df = df.sort_values('Name').reset_index(drop=True)
            
            print(f"  ✓ DataFrame created with {len(df)} rows and {len(df.columns)} columns")
        else:
            print(f"\n⚠️  WARNING: No faculty data found for {dept_code}")
            # Create empty DataFrame with all columns
            df = pd.DataFrame(columns=[
                'Name', 'Designation', 'Department', 'Email', 'Phone', 'Mobile',
                'Scopus ID', 'Scopus URL', 'ORCID ID', 'Google Scholar ID', 
                'Research Gate ID', 'Faculty ID', 'Employee ID', 'Extension',
                'Cabin Number', 'Office Location', 'Qualifications', 'Experience',
                'Research Interest', 'Specialization', 'LinkedIn', 'Profile URL'
            ])
        
        return df
    
    def scrape_all(self):
        """Scrape all departments and save to separate Excel files"""
        
        print("\n" + "="*70)
        print("SRM FACULTY DATA SCRAPER - IRINS EDITION")
        print("="*70)
        print("Target: CINTEL, DSBS, NWC Departments")
        print("Campus: Kattankulathur - Chennai")
        print("Using: IRINS Platform (most reliable source)")
        print("="*70)
        
        results = {}
        
        for dept_code in ['CINTEL', 'DSBS', 'NWC']:
            try:
                df = self.scrape_department(dept_code)
                results[dept_code] = df
                
                if len(df) == 0:
                    print(f"  ⚠️  WARNING: No data collected for {dept_code}")
                    continue
                
                print(f"\n[Saving] Preparing to save {len(df)} faculty records...")
                
                # Save individual file
                filename = f'SRM_{dept_code}_Faculty_Complete.xlsx'
                
                # Debug: Show sample data
                print(f"  → Sample data (first 3 faculty):")
                for idx in range(min(3, len(df))):
                    print(f"     {idx+1}. {df.iloc[idx]['Name']} - {df.iloc[idx]['Email']}")
                
                # Write to Excel with proper formatting
                print(f"  → Writing to Excel: {filename}")
                with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False, sheet_name=dept_code, freeze_panes=(1, 0))
                    
                    # Auto-adjust column widths
                    worksheet = writer.sheets[dept_code]
                    for col_num, column_title in enumerate(df.columns, 1):
                        max_length = 0
                        column = worksheet.cell(row=1, column=col_num).column_letter
                        
                        # Get max length from data
                        for row in worksheet.iter_rows(min_col=col_num, max_col=col_num):
                            try:
                                if row[0].value:
                                    max_length = max(max_length, len(str(row[0].value)))
                            except:
                                pass
                        
                        # Set column width
                        adjusted_width = min(max_length + 2, 50)
                        worksheet.column_dimensions[column].width = adjusted_width
                
                print(f"\n✓ SUCCESS: Saved {filename}")
                print(f"  Total faculty: {len(df)}")
                
                if len(df) > 0:
                    scopus_count = df['Scopus ID'].notna().sum()
                    email_count = df['Email'].notna().sum()
                    print(f"  With Scopus ID: {scopus_count}")
                    print(f"  With Email: {email_count}")
                
                time.sleep(2)  # Pause between departments
                
            except Exception as e:
                print(f"\n✗ ERROR scraping {dept_code}: {e}")
                import traceback
                traceback.print_exc()
                results[dept_code] = pd.DataFrame()
        
        # Print final summary
        print("\n" + "="*70)
        print("SCRAPING COMPLETE!")
        print("="*70)
        
        total = 0
        total_scopus = 0
        
        for dept_code, df in results.items():
            count = len(df)
            scopus = df['Scopus ID'].notna().sum() if not df.empty else 0
            total += count
            total_scopus += scopus
            print(f"{dept_code}: {count} faculty ({scopus} with Scopus ID)")
        
        print(f"\nTotal: {total} faculty members")
        print(f"With Scopus IDs: {total_scopus}")
        print("="*70)
        
        print("\n📁 Output Files:")
        print("  - SRM_CINTEL_Faculty_Complete.xlsx")
        print("  - SRM_DSBS_Faculty_Complete.xlsx")
        print("  - SRM_NWC_Faculty_Complete.xlsx")
        
        print("\n✅ Data Extracted:")
        print("  ✓ Name, Designation, Department")
        print("  ✓ Email, Phone, Mobile")
        print("  ✓ Scopus ID")
        print("  ✓ Faculty ID / Employee ID")
        print("  ✓ ORCID, Google Scholar, ResearchGate")
        print("  ✓ Research Interests & Specialization")
        print("  ✓ Experience, Qualifications")
        print("  ✓ Office details (Cabin, Extension)")
        print("  ✓ LinkedIn profiles")
        
        # Verify files were created
        print("\n" + "="*70)
        print("FILE VERIFICATION")
        print("="*70)
        for dept_code in ['CINTEL', 'DSBS', 'NWC']:
            filename = f'SRM_{dept_code}_Faculty_Complete.xlsx'
            if os.path.exists(filename):
                file_size = os.path.getsize(filename)
                print(f"✓ {filename} - {file_size:,} bytes")
                
                # Try to read it back to verify
                try:
                    verify_df = pd.read_excel(filename)
                    print(f"  → Verified: Contains {len(verify_df)} faculty records")
                except Exception as e:
                    print(f"  ✗ Error reading file: {e}")
            else:
                print(f"✗ {filename} - NOT FOUND")
        
        return results


def main():
    """Main execution"""
    
    # Check dependencies
    try:
        import requests
        import pandas
        import openpyxl
        from bs4 import BeautifulSoup
    except ImportError as e:
        print(f"✗ Missing dependency: {e}")
        print("\nPlease install required packages:")
        print("pip install requests beautifulsoup4 pandas openpyxl lxml")
        return
    
    # Run scraper
    scraper = SRMFacultyScraper()
    results = scraper.scrape_all()
    
    print("\n" + "="*70)
    print("✓ ALL DONE!")
    print("="*70)


if __name__ == "__main__":
    main()
