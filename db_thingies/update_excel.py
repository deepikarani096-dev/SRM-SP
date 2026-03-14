import mysql.connector
import time
import logging
from elsapy.elsclient import ElsClient
from elsapy.elssearch import ElsSearch
from elsapy.elsdoc import AbsDoc

API_KEY = ""
SRM_AFF_ID = "60014340"

# ---- LOGGING SETUP ----
logging.basicConfig(
    filename="srm_affiliation_check.log",
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

print("Log file: srm_affiliation_check.log")

client = ElsClient(API_KEY)

# ---- MYSQL CONNECTION ----
conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="scopuss"
)

cursor = conn.cursor(dictionary=True)

cursor.execute("SELECT * FROM papers WHERE doi IS NOT NULL")
papers = cursor.fetchall()

total = len(papers)

print("Checking", total, "papers")
logging.info(f"Starting verification for {total} papers")

RESUME_DOI = "10.18280/ijsse.130509"
resume_found = False

for i, paper in enumerate(papers, start=1):

    doi = paper["doi"]

    # skip until we reach the resume DOI
    if not resume_found:
        if doi == RESUME_DOI:
            resume_found = True
            print(f"Resuming from DOI: {doi}")
        else:
            continue

    print(f"[{i}/{total}] Checking DOI: {doi}")

    try:

        time.sleep(0.3)

        # ---- Search Scopus by DOI ----
        search = ElsSearch(f"DOI({doi})", 'scopus')
        search.execute(client)

        if not search.results or len(search.results) == 0:
            logging.warning(f"Not found in Scopus: {doi}")
            continue

        result = search.results[0]

        identifier = result.get("dc:identifier")

        if not identifier:
            logging.warning(f"No Scopus identifier for DOI: {doi}")
            continue

        scopus_id = identifier.split(":")[1]

        # ---- Fetch abstract record ----
        doc = AbsDoc(scp_id=scopus_id)
        doc.read(client)

        data = doc.data

        # ---- Extract affiliations safely ----
        affiliations = data.get("affiliation", [])

        aff_ids = []

        if isinstance(affiliations, list):
            for a in affiliations:
                if isinstance(a, dict):
                    aff_ids.append(a.get("@id"))

        elif isinstance(affiliations, dict):
            aff_ids.append(affiliations.get("@id"))

        elif isinstance(affiliations, str):
            aff_ids.append(affiliations)

        # ---- Check SRM affiliation ----
        if SRM_AFF_ID not in aff_ids:

            logging.info(f"Moving non-SRM paper: {doi}")

            cursor.execute("""
            INSERT INTO papers_non_srm
            (scopus_id, doi, title, type, publication_name, date,
            author1, author2, author3, author4, author5, author6,
            affiliation1, affiliation2, affiliation3, quartile)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                paper["scopus_id"],
                paper["doi"],
                paper["title"],
                paper["type"],
                paper["publication_name"],
                paper["date"],
                paper["author1"],
                paper["author2"],
                paper["author3"],
                paper["author4"],
                paper["author5"],
                paper["author6"],
                paper["affiliation1"],
                paper["affiliation2"],
                paper["affiliation3"],
                paper["quartile"]
            ))

            cursor.execute("DELETE FROM papers WHERE id=%s", (paper["id"],))

            conn.commit()

    except Exception as e:
        logging.error(f"Error with DOI {doi}: {str(e)}")
        print("Error with DOI:", doi)
        print("Reason:", e)

logging.info("Verification finished")
print("Finished checking papers")
